"""T2704: LLM-as-Judge evaluator tests."""
from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.platform.evaluator import (
    EvalCase,
    EvalRun,
    JudgeVerdict,
    PromptComparison,
    PromptEvaluator,
    compare_prompts,
    default_runner,
    gold_standard_suite,
    judge_output,
)
from services.platform.prompt_v2 import PromptStatus, PromptVersion


TENANT = "22222222-2222-2222-2222-222222222222"


# =====================================================================
# Judge heuristics
# =====================================================================

def test_judge_flags_bias_terms():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "We want a young energetic native english speaker.")
    assert v.bias < 1.0
    assert "bias-terms" in v.rationale


def test_judge_clean_text_passes_bias():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "We value collaboration, ownership, and learning.")
    assert v.bias == 1.0


def test_judge_flags_ssn():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "your ssn is 123-45-6789 do not share")
    assert v.safety < 1.0


def test_judge_flags_email():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "Email alice@example.com for more info")
    assert v.safety < 1.0


def test_judge_clean_text_passes_safety():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "Please contact the recruiter via the platform.")
    assert v.safety == 1.0


def test_judge_short_text_low_fluency():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "ok")
    assert v.fluency < 0.5


def test_judge_long_text_moderate_fluency():
    case = EvalCase(input="x", expected="ok")
    long = " ".join(["word"] * 200)
    v = judge_output(case, long)
    assert v.fluency > 0.4


def test_judge_all_caps_low_fluency():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "WE WANT ONLY THE BEST ENGINEERS TO JOIN US NOW")
    assert v.fluency < 0.9


def test_judge_accuracy_via_token_overlap():
    case = EvalCase(input="x", expected="system design kafka ownership")
    v = judge_output(case, "system design with kafka, ownership expected")
    assert v.accuracy > 0.7


def test_judge_accuracy_default_when_no_expected():
    case = EvalCase(input="x", expected=None)
    v = judge_output(case, "some output")
    assert v.accuracy == 0.85


def test_judge_overall_is_average_of_4_dims():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "ok" * 10)
    assert v.overall == pytest.approx((v.accuracy + v.fluency + v.safety + v.bias) / 4, abs=1e-6)


def test_judge_verdict_to_dict():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "ok" * 10)
    d = v.to_dict()
    for k in ("case_id", "accuracy", "fluency", "safety", "bias", "overall", "rationale", "model"):
        assert k in d


def test_judge_model_field_default():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "ok" * 10)
    assert v.model == "gpt-4o"


def test_judge_accepts_custom_model():
    case = EvalCase(input="x", expected="ok")
    v = judge_output(case, "ok" * 10, model="gpt-4o-mini")
    assert v.model == "gpt-4o-mini"


# =====================================================================
# Gold-standard suite
# =====================================================================

def test_gold_standard_suite_size():
    suite = gold_standard_suite(100)
    assert len(suite) == 100


def test_gold_standard_suite_default_size():
    suite = gold_standard_suite()
    assert len(suite) == 100


def test_gold_standard_suite_unique_ids():
    suite = gold_standard_suite(50)
    ids = [c.id for c in suite]
    assert len(set(ids)) == 50


def test_gold_standard_suite_has_expected():
    suite = gold_standard_suite(10)
    assert all(c.expected for c in suite)


def test_gold_standard_suite_metadata_topic():
    suite = gold_standard_suite(20)
    assert all(c.metadata.get("topic") for c in suite)


# =====================================================================
# Runner
# =====================================================================

def test_default_runner_substitutes_variables():
    p = PromptVersion(content="input: {{input}}, expected: {{expected}}")
    case = EvalCase(input="hello", expected="world")
    out = default_runner(p, case)
    assert "input: hello" in out
    assert "expected: world" in out


# =====================================================================
# PromptEvaluator
# =====================================================================

def _prompt(content: str = "You are a recruiter. Discuss with candidate.") -> PromptVersion:
    return PromptVersion(tenant_id=TENANT, name="p", content=content,
                         version=1, status=PromptStatus.ACTIVE, traffic_pct=100)


def test_evaluator_run_returns_eval_run():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), [EvalCase(input="x", expected="x")])
    assert isinstance(res, EvalRun)
    assert res.case_count == 1
    assert len(res.verdicts) == 1


def test_evaluator_summary_has_four_dims():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), gold_standard_suite(10))
    for dim in ("accuracy", "fluency", "safety", "bias", "overall"):
        assert dim in res.summary


def test_evaluator_summary_overall_in_range():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), gold_standard_suite(20))
    assert 0.0 <= res.summary["overall"] <= 1.0


def test_evaluator_empty_suite_returns_zero_summary():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), [])
    assert res.summary["overall"] == 0.0


def test_evaluator_evaluate_suite_default_n():
    ev = PromptEvaluator()
    res = ev.evaluate_suite(_prompt())
    assert res.case_count == 100


def test_evaluator_finished_at_set():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), [EvalCase(input="x", expected="x")])
    assert res.finished_at is not None
    assert res.finished_at >= res.started_at


def test_evaluator_uses_custom_runner():
    seen = {}

    def runner(p, c):
        seen[c.id] = True
        return "ok"

    ev = PromptEvaluator(runner=runner)
    res = ev.evaluate(_prompt(), [EvalCase(id="c1", input="x", expected="x")])
    assert seen.get("c1") is True


def test_evaluator_uses_custom_judge():
    def judge(case, output, *, model="gpt-4o"):
        return JudgeVerdict(case_id=case.id, accuracy=0.5, fluency=0.5,
                            safety=0.5, bias=0.5, overall=0.5, model=model)

    ev = PromptEvaluator(judge=judge)
    res = ev.evaluate(_prompt(), [EvalCase(input="x", expected="x")])
    assert res.summary["overall"] == 0.5


def test_evaluator_judge_model_field():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), [EvalCase(input="x", expected="x")],
                      judge_model="claude-opus-4")
    assert res.judge_model == "claude-opus-4"


def test_evaluator_to_dict():
    ev = PromptEvaluator()
    res = ev.evaluate(_prompt(), [EvalCase(input="x", expected="x")])
    d = res.to_dict()
    assert "summary" in d
    assert "verdicts" in d
    assert d["case_count"] == 1


# =====================================================================
# Comparison
# =====================================================================

def test_compare_prompts_right_wins_when_higher():
    left = EvalRun(summary={"accuracy": 0.5, "fluency": 0.5,
                            "safety": 0.5, "bias": 0.5, "overall": 0.5})
    right = EvalRun(summary={"accuracy": 0.7, "fluency": 0.7,
                             "safety": 0.7, "bias": 0.7, "overall": 0.7})
    cmp = compare_prompts(left, right)
    assert cmp.winner == "right"
    assert cmp.delta["overall"] == pytest.approx(0.2)


def test_compare_prompts_left_wins_when_higher():
    left = EvalRun(summary={"accuracy": 0.8, "fluency": 0.8,
                            "safety": 0.8, "bias": 0.8, "overall": 0.8})
    right = EvalRun(summary={"accuracy": 0.5, "fluency": 0.5,
                             "safety": 0.5, "bias": 0.5, "overall": 0.5})
    cmp = compare_prompts(left, right)
    assert cmp.winner == "left"


def test_compare_prompts_tie_when_close():
    left = EvalRun(summary={"accuracy": 0.5, "fluency": 0.5,
                            "safety": 0.5, "bias": 0.5, "overall": 0.5})
    right = EvalRun(summary={"accuracy": 0.5001, "fluency": 0.5,
                             "safety": 0.5, "bias": 0.5, "overall": 0.5001})
    cmp = compare_prompts(left, right)
    assert cmp.winner == "tie"


def test_compare_prompts_to_dict():
    left = EvalRun(summary={"accuracy": 0.5, "fluency": 0.5,
                            "safety": 0.5, "bias": 0.5, "overall": 0.5})
    right = EvalRun(summary={"accuracy": 0.6, "fluency": 0.5,
                             "safety": 0.5, "bias": 0.5, "overall": 0.55})
    cmp = compare_prompts(left, right)
    d = cmp.to_dict()
    assert d["winner"] == "right"
    assert "delta" in d


# =====================================================================
# Integration: prompt -> evaluator
# =====================================================================

def test_end_to_end_prompt_evaluation():
    from services.platform.prompt_v2 import PromptService

    svc = PromptService()
    v = svc.create_version(
        tenant_id=TENANT, name="intro",
        content="Hello {{input}}, expect {{expected}}.",
        status=PromptStatus.ACTIVE, traffic_pct=100,
    )
    ev = PromptEvaluator()
    res = ev.evaluate_suite(v, n=10)
    assert res.case_count == 10
    assert 0 <= res.summary["overall"] <= 1