"""v10.0 T5026 — Prompt v2 eval runner.

Runs a prompt version against a **golden set** of input→expected examples and
returns a deterministic score card. The runner is deliberately LLM-agnostic:
callers inject a ``generate`` callable (the function under test) and a list of
:class:`GoldenCase`. The runner calls ``generate(prompt, variables)`` for each
case, compares the output to the expected answer with a configurable
similarity metric, and aggregates pass/fail + latency.

CI-friendly by design:

* Exits with a non-zero status when ``min_pass_rate`` is not met
  (:func:`EvalRunner.run_cli`), so it can be wired straight into a CI job.
* Pure-python metric scorers (exact / contains / substring-fuzzy / json-schema)
  with no network calls, so a 1000-case eval runs in milliseconds.
* Output is a JSON-serialisable :class:`EvalReport`.

Integrates with the existing :class:`~services.platform.prompt_v2.PromptService`
so a caller can eval an in-registry version directly:

    runner = EvalRunner()
    report = runner.eval_prompt_version(service, tenant_id, name, agent,
                                        version, cases, generate)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("waibao.platform.prompt_eval")


# ---------------------------------------------------------------------------
# Golden cases + scorers
# ---------------------------------------------------------------------------
@dataclass
class GoldenCase:
    """A single input→expected example for prompt evaluation."""

    name: str
    variables: Dict[str, Any]
    expected: str
    weight: float = 1.0
    tags: List[str] = field(default_factory=list)
    # Optional override of the scorer: "exact" | "contains" | "fuzzy" | "json"
    scorer: Optional[str] = None
    # Threshold for fuzzy match (0..1) — defaults to 0.8
    threshold: float = 0.8

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "variables": self.variables,
            "expected": self.expected,
            "weight": self.weight,
            "tags": list(self.tags),
            "scorer": self.scorer,
            "threshold": self.threshold,
        }


def score_exact(output: str, expected: str, **_: Any) -> float:
    return 1.0 if output.strip() == expected.strip() else 0.0


def score_contains(output: str, expected: str, **_: Any) -> float:
    return 1.0 if expected.strip().lower() in output.lower() else 0.0


def score_fuzzy(output: str, expected: str, threshold: float = 0.8, **_: Any) -> float:
    """Normalized Levenshtein similarity, gated by ``threshold``."""
    import difflib

    ratio = difflib.SequenceMatcher(None, output.lower(), expected.lower()).ratio()
    return 1.0 if ratio >= threshold else ratio


def score_json(output: str, expected: str, **_: Any) -> float:
    """Pass iff ``output`` parses as JSON and contains the keys/values of
    ``expected`` (a JSON object string)."""
    try:
        got = json.loads(output)
        want = json.loads(expected)
    except Exception:  # noqa: BLE001
        return 0.0
    if not isinstance(got, dict) or not isinstance(want, dict):
        return 1.0 if got == want else 0.0
    for key, value in want.items():
        if key not in got or got[key] != value:
            return 0.0
    return 1.0


SCORERS: Dict[str, Callable[..., float]] = {
    "exact": score_exact,
    "contains": score_contains,
    "fuzzy": score_fuzzy,
    "json": score_json,
}


def _resolve_scorer(case: GoldenCase, default: str) -> Callable[..., float]:
    name = case.scorer or default
    return SCORERS.get(name, score_fuzzy)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class CaseResult:
    name: str
    passed: bool
    score: float
    weight: float
    latency_ms: float
    output: str
    expected: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "weight": self.weight,
            "latency_ms": round(self.latency_ms, 2),
            "output": self.output,
            "expected": self.expected,
            "error": self.error,
        }


@dataclass
class EvalReport:
    prompt_version: Optional[int]
    scorer: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    weighted_score: float
    p50_latency_ms: float
    p95_latency_ms: float
    cases: List[CaseResult]
    min_pass_rate: float
    success: bool
    ran_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_version": self.prompt_version,
            "scorer": self.scorer,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "weighted_score": round(self.weighted_score, 4),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "cases": [c.to_dict() for c in self.cases],
            "min_pass_rate": self.min_pass_rate,
            "success": self.success,
            "ran_at": self.ran_at,
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class EvalRunner:
    """Run a golden-set evaluation against a prompt version or raw template."""

    def __init__(self, *, default_scorer: str = "fuzzy") -> None:
        self.default_scorer = default_scorer

    def eval_template(
        self,
        template: str,
        cases: List[GoldenCase],
        generate: Callable[[str, Dict[str, Any]], str],
        *,
        min_pass_rate: float = 0.8,
        version: Optional[int] = None,
    ) -> EvalReport:
        """Eval a raw prompt ``template``."""
        return self._run(template, cases, generate, min_pass_rate, version)

    def eval_prompt_version(
        self,
        service: Any,
        tenant_id: str,
        name: str,
        agent: str,
        version: int,
        cases: List[GoldenCase],
        generate: Callable[[str, Dict[str, Any]], str],
        *,
        min_pass_rate: float = 0.8,
    ) -> EvalReport:
        """Fetch a registered prompt version and eval it."""
        versions = service.list_versions(tenant_id, name, agent)
        prompt = next((v for v in versions if v.version == version), None)
        if prompt is None:
            raise ValueError(
                f"prompt {name!r} v{version} not found for tenant {tenant_id!r}"
            )
        return self._run(prompt.content, cases, generate, min_pass_rate, version)

    # ---- internals ------------------------------------------------------
    def _run(
        self,
        template: str,
        cases: List[GoldenCase],
        generate: Callable[[str, Dict[str, Any]], str],
        min_pass_rate: float,
        version: Optional[int],
    ) -> EvalReport:
        results: List[CaseResult] = []
        weighted_total = 0.0
        weight_sum = 0.0
        for case in cases:
            scorer = _resolve_scorer(case, self.default_scorer)
            start = time.perf_counter()
            error: Optional[str] = None
            output = ""
            try:
                output = generate(template, case.variables) or ""
            except Exception as exc:  # noqa: BLE001 — capture per-case failure
                error = f"{type(exc).__name__}: {exc}"
            latency_ms = (time.perf_counter() - start) * 1000.0
            score = 0.0 if error else scorer(output, case.expected,
                                              threshold=case.threshold)
            passed = error is None and score >= case.threshold
            results.append(CaseResult(
                name=case.name, passed=passed, score=score,
                weight=case.weight, latency_ms=latency_ms,
                output=output, expected=case.expected, error=error,
            ))
            weighted_total += score * case.weight
            weight_sum += case.weight

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        pass_rate = passed / total if total else 0.0
        weighted_score = weighted_total / weight_sum if weight_sum else 0.0
        latencies = sorted(r.latency_ms for r in results)
        success = pass_rate >= min_pass_rate
        return EvalReport(
            prompt_version=version,
            scorer=self.default_scorer,
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=pass_rate,
            weighted_score=weighted_score,
            p50_latency_ms=_percentile(latencies, 50),
            p95_latency_ms=_percentile(latencies, 95),
            cases=results,
            min_pass_rate=min_pass_rate,
            success=success,
        )

    # ---- CI entrypoint --------------------------------------------------
    def run_cli(self, report: EvalReport) -> int:
        """Print the report as JSON and return a POSIX exit code (0/1)."""
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.success else 1


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


__all__ = [
    "GoldenCase",
    "CaseResult",
    "EvalReport",
    "EvalRunner",
    "SCORERS",
    "score_exact",
    "score_contains",
    "score_fuzzy",
    "score_json",
]
