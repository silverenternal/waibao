"""v10.0 T5026 — Prompt eval runner tests."""
from __future__ import annotations

import pytest

from services.platform.prompt_eval import (
    EvalRunner,
    GoldenCase,
    score_contains,
    score_exact,
    score_fuzzy,
    score_json,
)
from services.platform.prompt_v2 import PromptService


def _gen(template, variables):
    # naive render so the test generate() mirrors the service render
    out = template
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------
def test_score_exact_case_insensitive_whitespace():
    assert score_exact("  hello ", "hello") == 1.0
    assert score_exact("hello", "world") == 0.0


def test_score_contains():
    assert score_contains("the quick brown fox", "BROWN") == 1.0
    assert score_contains("hello", "world") == 0.0


def test_score_fuzzy_threshold():
    assert score_fuzzy("hello world", "hello world", threshold=0.8) == 1.0
    # slightly off — ratio < 0.8 returns the raw ratio, not 1.0
    assert score_fuzzy("xyz", "abc", threshold=0.8) < 0.8


def test_score_json_key_subset():
    payload = '{"name": "alice", "age": 30}'
    assert score_json(payload, '{"name": "alice"}') == 1.0
    assert score_json(payload, '{"name": "bob"}') == 0.0
    assert score_json("not json", "{}") == 0.0


# ---------------------------------------------------------------------------
# Runner — basic eval
# ---------------------------------------------------------------------------
def test_eval_all_pass():
    runner = EvalRunner(default_scorer="contains")
    template = "Hello {{name}}, welcome!"
    cases = [
        GoldenCase(name="a", variables={"name": "Alice"}, expected="Hello Alice"),
        GoldenCase(name="b", variables={"name": "Bob"}, expected="Hello Bob"),
    ]
    report = runner.eval_template(template, cases, _gen, min_pass_rate=0.5)
    assert report.total == 2
    assert report.passed == 2
    assert report.pass_rate == 1.0
    assert report.success is True


def test_eval_partial_failure_lowers_pass_rate():
    runner = EvalRunner(default_scorer="exact")
    template = "{{x}}"
    cases = [
        GoldenCase(name="ok", variables={"x": "1"}, expected="1"),
        GoldenCase(name="bad", variables={"x": "2"}, expected="1"),
    ]
    report = runner.eval_template(template, cases, _gen, min_pass_rate=0.9)
    assert report.passed == 1
    assert report.failed == 1
    assert report.success is False


def test_eval_min_pass_rate_gate():
    runner = EvalRunner(default_scorer="exact")
    template = "{{x}}"
    cases = [GoldenCase(name=str(i), variables={"x": str(i)}, expected="0") for i in range(4)]
    # 1/4 pass at threshold 0.5 — should be marked failure
    report = runner.eval_template(template, cases, _gen, min_pass_rate=0.5)
    assert report.success is False


def test_eval_case_error_is_captured_not_raised():
    runner = EvalRunner(default_scorer="exact")

    def broken(template, variables):
        raise RuntimeError("boom")

    cases = [GoldenCase(name="x", variables={}, expected="anything")]
    report = runner.eval_template("t", cases, broken, min_pass_rate=0.0)
    assert report.cases[0].error is not None
    assert report.cases[0].passed is False
    assert "RuntimeError" in report.cases[0].error


def test_eval_weighted_score():
    runner = EvalRunner(default_scorer="exact")
    template = "{{x}}"
    cases = [
        GoldenCase(name="heavy_pass", variables={"x": "1"}, expected="1", weight=3.0),
        GoldenCase(name="light_fail", variables={"x": "2"}, expected="1", weight=1.0),
    ]
    report = runner.eval_template(template, cases, _gen, min_pass_rate=0.0)
    assert report.weighted_score == 0.75  # 3*1 / (3+1)


def test_eval_latency_percentiles():
    runner = EvalRunner(default_scorer="exact")
    template = "{{x}}"
    cases = [GoldenCase(name=str(i), variables={"x": str(i)}, expected=str(i)) for i in range(10)]
    report = runner.eval_template(template, cases, _gen, min_pass_rate=0.0)
    assert report.p50_latency_ms >= 0.0
    assert report.p95_latency_ms >= report.p50_latency_ms


def test_eval_cli_exit_code(capsys):
    runner = EvalRunner(default_scorer="exact")
    report = runner.eval_template("{{x}}",
                                  [GoldenCase("a", {"x": "1"}, "1")], _gen,
                                  min_pass_rate=0.5)
    code = runner.run_cli(report)
    assert code == 0
    captured = capsys.readouterr().out
    assert '"success": true' in captured or '"success": true' in captured.replace("\n", "")


# ---------------------------------------------------------------------------
# Runner — eval a registered version
# ---------------------------------------------------------------------------
def test_eval_prompt_registered_version():
    service = PromptService()
    service.create_version(
        tenant_id="t1", name="greet", agent="default",
        content="Hi {{name}}", version=1,
    )
    service.activate_version("t1", "greet", "default", 1, traffic_pct=100)
    runner = EvalRunner(default_scorer="contains")
    cases = [GoldenCase("a", {"name": "Sam"}, "Hi Sam")]
    report = runner.eval_prompt_version(service, "t1", "greet", "default", 1,
                                        cases, _gen, min_pass_rate=0.5)
    assert report.prompt_version == 1
    assert report.passed == 1


def test_eval_prompt_unknown_version_raises():
    service = PromptService()
    runner = EvalRunner()
    with pytest.raises(ValueError):
        runner.eval_prompt_version(service, "t1", "nope", "default", 99, [],
                                   _gen, min_pass_rate=0.5)
