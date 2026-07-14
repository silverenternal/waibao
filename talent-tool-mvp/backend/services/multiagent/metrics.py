"""Multi-agent run metrics — T5022 latency / token / cost / success.

Collects per-agent and per-run telemetry from an orchestration:

* **latency**  — wall-clock seconds per agent task + total run.
* **tokens**   — prompt + completion tokens (when the LLM reports them).
* **cost**     — USD cost derived from a per-model price table.
* **success**  — per-agent ok/fail + run-level status.

The recorder is dependency-free; it is fed by the executor and the
orchestrator. A snapshot can be exported as a flat dict for Prometheus /
OpenTelemetry / the analytics warehouse.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("waibao.multiagent.metrics")


# ---------------------------------------------------------------------------
# Cost table (USD per 1M tokens) — extend as new models are adopted.
# ---------------------------------------------------------------------------

_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "default": {"input": 1.00, "output": 3.00},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    tier = _PRICING.get(model, _PRICING["default"])
    return (
        prompt_tokens / 1_000_000.0 * tier["input"]
        + completion_tokens / 1_000_000.0 * tier["output"]
    )


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class AgentMetric:
    agent_id: str
    scenario: str
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    success: bool = True
    error: str | None = None
    model: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "scenario": self.scenario,
            "latency_s": round(self.latency_s, 6),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "success": self.success,
            "error": self.error,
            "model": self.model,
            "timestamp": self.timestamp,
        }


@dataclass
class RunMetric:
    run_id: str
    scenario: str
    status: str
    rounds: int
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    agent_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "status": self.status,
            "rounds": self.rounds,
            "latency_s": round(self.latency_s, 6),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "agent_count": self.agent_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Recorder (thread-safe singleton)
# ---------------------------------------------------------------------------

class MetricsRecorder:
    """Thread-safe collector for agent + run metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: list[AgentMetric] = []
        self._runs: list[RunMetric] = []

    # ------------------------------------------------------------------
    def record_agent(self, metric: AgentMetric) -> None:
        with self._lock:
            self._agents.append(metric)

    def record_run(self, metric: RunMetric) -> None:
        with self._lock:
            self._runs.append(metric)

    # ------------------------------------------------------------------
    def agent_metrics(self, scenario: str | None = None) -> list[AgentMetric]:
        with self._lock:
            rows = list(self._agents)
        if scenario:
            rows = [r for r in rows if r.scenario == scenario]
        return rows

    def run_metrics(self, scenario: str | None = None) -> list[RunMetric]:
        with self._lock:
            rows = list(self._runs)
        if scenario:
            rows = [r for r in rows if r.scenario == scenario]
        return rows

    # ------------------------------------------------------------------
    def aggregate(self, scenario: str | None = None) -> dict[str, Any]:
        """Roll up totals for a scenario (or everything)."""
        agents = self.agent_metrics(scenario)
        runs = self.run_metrics(scenario)
        n_runs = len(runs)
        n_agents = len(agents)
        successful_runs = sum(1 for r in runs if r.status == "completed")
        return {
            "scenario": scenario or "all",
            "runs": n_runs,
            "agents_invoked": n_agents,
            "success_rate": (successful_runs / n_runs) if n_runs else 0.0,
            "p50_latency_s": _percentile([a.latency_s for a in agents], 50),
            "p95_latency_s": _percentile([a.latency_s for a in agents], 95),
            "p99_latency_s": _percentile([a.latency_s for a in agents], 99),
            "total_tokens": sum(a.prompt_tokens + a.completion_tokens for a in agents),
            "total_cost_usd": round(sum(a.cost_usd for a in agents), 6),
        }

    def reset(self) -> None:
        with self._lock:
            self._agents.clear()
            self._runs.clear()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_RECORDER: MetricsRecorder | None = None


def get_metrics_recorder() -> MetricsRecorder:
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = MetricsRecorder()
    return _RECORDER


def reset_metrics_recorder() -> None:
    global _RECORDER
    _RECORDER = None
