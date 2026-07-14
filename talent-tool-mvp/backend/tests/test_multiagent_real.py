"""T5022 — Multi-Agent real LLM executor + 4 scenarios + metrics tests."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.multiagent.executor import (  # noqa: E402
    FakeLLMClient,
    LLMExecutor,
    OpenAIChatClient,
    build_scoped_orchestrator,
)
from services.multiagent.metrics import (  # noqa: E402
    AgentMetric,
    RunMetric,
    estimate_cost,
    get_metrics_recorder,
    reset_metrics_recorder,
)
from services.multiagent.orchestrator import (  # noqa: E402
    Agent,
    OrchestrationTask,
    Orchestrator,
    Task,
)
from services.multiagent.patterns import ScenarioKind  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_metrics_recorder()
    yield
    reset_metrics_recorder()


# ---------------------------------------------------------------------------
# Executor unit tests
# ---------------------------------------------------------------------------

def test_executor_parses_llm_json_and_records_metrics():
    class FixedLLM(FakeLLMClient):
        def chat(self, messages):
            self.last_usage = {"prompt_tokens": 120, "completion_tokens": 35}
            return json.dumps({"decision": 88, "confidence": 0.9, "rationale": "strong fit"})

    ex = LLMExecutor(llm=FixedLLM(), scenario="resume_scoring")
    agent = Agent(role="Tech Screener", goal="score", backstory="eng")
    task = Task(description="Score technical fit", agent=agent)
    out = ex(agent, task, {"goal": "evaluate candidate", "scenario": "resume_scoring"})

    assert out["decision"] == 88
    assert out["confidence"] == pytest.approx(0.9)
    assert out["rationale"] == "strong fit"
    assert out["backend"] == "llm"
    rec = get_metrics_recorder()
    metrics = rec.agent_metrics("resume_scoring")
    assert len(metrics) == 1
    m = metrics[0]
    assert m.success is True
    assert m.prompt_tokens == 120
    assert m.completion_tokens == 35
    assert m.cost_usd > 0


def test_executor_falls_back_on_llm_failure():
    class BoomLLM(FakeLLMClient):
        def chat(self, messages):
            raise RuntimeError("network down")

    ex = LLMExecutor(llm=BoomLLM(), scenario="bias_review")
    agent = Agent(role="Bias Reviewer", goal="review", backstory="legal")
    task = Task(description="Review for bias", agent=agent)
    out = ex(agent, task, {"goal": "review text", "scenario": "bias_review"})
    assert out["backend"] == "fallback"
    assert out["decision"] is not None
    rec = get_metrics_recorder()
    m = rec.agent_metrics("bias_review")[0]
    assert m.success is False
    assert "network down" in (m.error or "")


def test_executor_handles_unparseable_output():
    class JunkLLM(FakeLLMClient):
        def chat(self, messages):
            self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
            return "the candidate is great"

    ex = LLMExecutor(llm=JunkLLM(), scenario="strategy_decode")
    agent = Agent(role="Reviewer", goal="qa", backstory="staff")
    task = Task(description="Aggregate final QA score", agent=agent)
    out = ex(agent, task, {"goal": "decode strategy", "scenario": "strategy_decode"})
    # decision synthesised deterministically as a number (contains 'score')
    assert out["decision"] is not None
    assert 0.0 <= out["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 4 scenarios end-to-end (with the fake LLM driving real consensus)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", [
    ScenarioKind.RESUME_SCORING,
    ScenarioKind.BIAS_REVIEW,
    ScenarioKind.OFFER_NEGOTIATION,
    ScenarioKind.STRATEGY_DECODE,
])
def test_all_four_scenarios_complete_with_real_executor(scenario):
    orch = build_scoped_orchestrator(
        FakeLLMClient(), scenario=scenario.value, use_crewai=False,
    )
    task = OrchestrationTask(
        scenario=scenario,
        goal="score a strong senior candidate with expert skills",
        context={"candidate": "Jane Doe", "target_score": 90},
    )
    result = orch.orchestrate(task)
    assert result.status in {"completed", "no_consensus"}
    # every agent in the plan produced an output
    assert len(result.outputs) >= 2
    # metrics were recorded for every agent
    rec = get_metrics_recorder()
    assert len(rec.agent_metrics(scenario.value)) >= 2


def test_resume_scoring_produces_numeric_consensus():
    orch = build_scoped_orchestrator(
        FakeLLMClient(), scenario="resume_scoring", use_crewai=False,
    )
    result = orch.orchestrate(OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING,
        goal="score candidate senior expert lead",
    ))
    assert result.consensus is not None
    # weighted vote over numeric scores
    assert isinstance(result.consensus.decision, (int, float))


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

def test_estimate_cost_uses_model_pricing():
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)


def test_metrics_aggregate_reports_percentiles_and_totals():
    rec = get_metrics_recorder()
    for i in range(5):
        rec.record_agent(AgentMetric(
            agent_id=f"a{i}", scenario="x",
            latency_s=float(i), prompt_tokens=100, completion_tokens=50,
            cost_usd=0.01,
        ))
    rec.record_run(RunMetric(
        run_id="r1", scenario="x", status="completed", rounds=1,
        latency_s=1.0, agent_count=5, success_count=5,
    ))
    agg = rec.aggregate("x")
    assert agg["agents_invoked"] == 5
    assert agg["success_rate"] == 1.0
    assert agg["p50_latency_s"] == pytest.approx(2.0)
    assert agg["p95_latency_s"] >= agg["p50_latency_s"]
    assert agg["total_tokens"] == 5 * 150


def test_openai_client_requires_sdk_or_raises():
    # Constructing OpenAIChatClient without a key/SDK should raise a
    # RuntimeError, never silently return a working client.
    with pytest.raises(RuntimeError):
        OpenAIChatClient(api_key=None)
