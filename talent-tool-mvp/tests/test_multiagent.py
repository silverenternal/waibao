"""T2703: Multi-Agent orchestration tests (CrewAI vendor-in).

40+ tests covering:
  * roles + role registry
  * consensus strategies (majority / unanimous / weighted / quorum)
  * collaboration patterns (sequential / parallel / hierarchical / debate)
  * orchestrator end-to-end for the 4 core scenarios
  * EventBus + Memory side effects
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.multiagent import (
    AgentRoleRegistry,
    CollaborationPattern,
    ConsensusStrategy,
    Orchestrator,
    OrchestrationTask,
    ROLE_PRESETS,
    Role,
    RoleKind,
    ScenarioKind,
    aggregate,
    build_pattern,
    get_orchestrator,
    register_default_roles,
    reset_orchestrator,
)
from services.multiagent.consensus import (
    ConsensusVote,
    aggregate_majority,
    aggregate_quorum,
    aggregate_unanimous,
    aggregate_weighted,
)
from services.multiagent.orchestrator import (
    Crew,
    CrewProcess,
    Agent,
    Task,
    default_executor,
)
from services.multiagent.patterns import PatternPlan


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_orchestrator()
    yield
    reset_orchestrator()


# =====================================================================
# Role / registry tests
# =====================================================================

def test_role_kind_enum_values():
    assert RoleKind.PM.value == "pm"
    assert RoleKind.RESEARCHER.value == "researcher"
    assert RoleKind.WRITER.value == "writer"
    assert RoleKind.REVIEWER.value == "reviewer"
    assert RoleKind.EXECUTOR.value == "executor"
    assert RoleKind.TECH_SCORER.value == "tech_scorer"
    assert RoleKind.CULTURE_SCORER.value == "culture_scorer"
    assert RoleKind.DOMAIN_SCORER.value == "domain_scorer"
    assert RoleKind.BIAS_REVIEWER.value == "bias_reviewer"


def test_role_presets_cover_all_kinds():
    for kind in RoleKind:
        assert kind in ROLE_PRESETS
        role = ROLE_PRESETS[kind]
        assert role.title
        assert role.goal
        assert role.backstory


def test_role_to_dict():
    role = ROLE_PRESETS[RoleKind.PM]
    d = role.to_dict()
    assert d["kind"] == "pm"
    assert d["title"] == "Product Manager"
    assert d["allow_delegation"] is True


def test_registry_register_and_get():
    reg = AgentRoleRegistry()
    reg.register("a1", ROLE_PRESETS[RoleKind.WRITER])
    assert "a1" in reg
    assert reg.get("a1").role.kind == RoleKind.WRITER


def test_registry_register_with_weight():
    reg = AgentRoleRegistry()
    reg.register("a1", ROLE_PRESETS[RoleKind.WRITER], weight=2.5)
    assert reg.get("a1").weight == 2.5


def test_registry_rejects_non_positive_weight():
    reg = AgentRoleRegistry()
    with pytest.raises(ValueError):
        reg.register("a", ROLE_PRESETS[RoleKind.WRITER], weight=0.0)


def test_registry_unregister():
    reg = AgentRoleRegistry()
    reg.register("a1", ROLE_PRESETS[RoleKind.WRITER])
    assert reg.unregister("a1") is True
    assert reg.unregister("a1") is False
    assert "a1" not in reg


def test_registry_list_filtered_by_role_kind():
    reg = AgentRoleRegistry()
    reg.register("w1", ROLE_PRESETS[RoleKind.WRITER])
    reg.register("w2", ROLE_PRESETS[RoleKind.WRITER])
    reg.register("r1", ROLE_PRESETS[RoleKind.REVIEWER])
    writers = reg.list(role_kind=RoleKind.WRITER)
    assert len(writers) == 2
    assert all(a.role.kind == RoleKind.WRITER for a in writers)


def test_registry_list_filtered_by_tenant():
    reg = AgentRoleRegistry()
    reg.register("a1", ROLE_PRESETS[RoleKind.WRITER], tenant_id="t1")
    reg.register("a2", ROLE_PRESETS[RoleKind.WRITER], tenant_id="t2")
    reg.register("a3", ROLE_PRESETS[RoleKind.WRITER])  # global
    only_t1 = reg.list(tenant_id="t1")
    assert {a.agent_id for a in only_t1} == {"a1", "a3"}


def test_register_default_roles_populates_all():
    reg = register_default_roles()
    assert len(reg) == len(RoleKind)


def test_register_default_roles_idempotent():
    reg = register_default_roles()
    register_default_roles(reg)
    assert len(reg) == len(RoleKind)


# =====================================================================
# Consensus strategy tests
# =====================================================================

def _votes(*pairs) -> list:
    return [ConsensusVote(agent_id=f"a{i}", decision=d,
                          confidence=c, weight=w)
            for i, (d, c, w) in enumerate(pairs)]


def test_majority_simple():
    votes = _votes(("yes", 0.9, 1.0), ("yes", 0.8, 1.0), ("no", 0.7, 1.0))
    res = aggregate_majority(votes)
    assert res.decision == "yes"
    assert res.reached is True
    assert res.strategy == ConsensusStrategy.MAJORITY


def test_majority_no_decision_when_split():
    votes = _votes(("yes", 0.9, 1.0), ("no", 0.9, 1.0))
    res = aggregate_majority(votes)
    assert res.reached is False


def test_majority_empty():
    res = aggregate_majority([])
    assert res.reached is False
    assert res.decision is None


def test_unanimous_all_agree():
    votes = _votes(("x", 0.9, 1.0), ("x", 0.9, 1.0))
    res = aggregate_unanimous(votes)
    assert res.reached is True
    assert res.decision == "x"


def test_unanimous_disagree():
    votes = _votes(("x", 0.9, 1.0), ("y", 0.9, 1.0))
    res = aggregate_unanimous(votes)
    assert res.reached is False
    assert res.decision is None


def test_unanimous_empty():
    res = aggregate_unanimous([])
    assert res.reached is False


def test_weighted_uses_confidence_and_weight():
    votes = _votes(("a", 0.5, 1.0), ("b", 0.99, 5.0))
    res = aggregate_weighted(votes)
    # b: 0.99 * 5 = 4.95 ; a: 0.5 * 1 = 0.5
    assert res.decision == "b"


def test_weighted_handles_numeric_decisions():
    votes = _votes((80.0, 0.9, 1.0), (90.0, 0.9, 2.0))
    res = aggregate_weighted(votes)
    # 90*2 = 1.8 vs 80*1 = 0.9
    assert res.decision == 90.0


def test_quorum_requires_minimum_votes():
    votes = _votes(("x", 0.9, 1.0))
    res = aggregate_quorum(votes, quorum=2)
    assert res.reached is False
    assert "quorum not met" in res.notes


def test_quorum_met_then_majority():
    votes = _votes(("x", 0.9, 1.0), ("x", 0.8, 1.0))
    res = aggregate_quorum(votes, quorum=2)
    assert res.reached is True
    assert res.decision == "x"


def test_aggregate_dispatch():
    votes = _votes(("x", 0.9, 1.0), ("x", 0.9, 1.0))
    for strat in ConsensusStrategy:
        res = aggregate(strat, votes, quorum=2)
        assert res.strategy == strat


def test_aggregate_unknown_strategy_raises():
    with pytest.raises(ValueError):
        aggregate("bogus", [])


# =====================================================================
# Pattern builder tests
# =====================================================================

def test_pattern_resume_scoring_parallel_weighted():
    plan = build_pattern(ScenarioKind.RESUME_SCORING)
    assert plan.pattern == CollaborationPattern.PARALLEL
    assert plan.consensus == ConsensusStrategy.WEIGHTED
    kinds = [s.role.kind for s in plan.steps]
    assert set(kinds) == {RoleKind.TECH_SCORER, RoleKind.CULTURE_SCORER, RoleKind.DOMAIN_SCORER}


def test_pattern_bias_review_debate_unanimous():
    plan = build_pattern(ScenarioKind.BIAS_REVIEW)
    assert plan.pattern == CollaborationPattern.DEBATE
    assert plan.consensus == ConsensusStrategy.UNANIMOUS


def test_pattern_offer_negotiation_sequential():
    plan = build_pattern(ScenarioKind.OFFER_NEGOTIATION)
    assert plan.pattern == CollaborationPattern.SEQUENTIAL
    kinds = [s.role.kind for s in plan.steps]
    assert kinds[0] == RoleKind.RESEARCHER
    assert kinds[-1] == RoleKind.REVIEWER


def test_pattern_strategy_decode_hierarchical():
    plan = build_pattern(ScenarioKind.STRATEGY_DECODE)
    assert plan.pattern == CollaborationPattern.HIERARCHICAL
    kinds = [s.role.kind for s in plan.steps]
    assert RoleKind.PM in kinds


def test_pattern_max_rounds_override():
    plan = build_pattern(ScenarioKind.BIAS_REVIEW, max_rounds=7)
    assert plan.max_rounds == 7


def test_pattern_unknown_scenario_raises():
    with pytest.raises(ValueError):
        build_pattern("nope")


def test_pattern_to_dict():
    plan = build_pattern(ScenarioKind.RESUME_SCORING)
    d = plan.to_dict()
    assert d["scenario"] == "resume_scoring"
    assert d["pattern"] == "parallel"
    assert len(d["steps"]) == 3


# =====================================================================
# Orchestrator / scenario tests
# =====================================================================

def _orchestrator_with_capture():
    events: list = []
    memory: list = []

    def emit(name, payload):
        events.append((name, payload))

    def write(payload):
        memory.append(payload)

    orch = Orchestrator(event_emitter=emit, memory_writer=write)
    return orch, events, memory


def test_orchestrator_resume_scoring_reaches_consensus():
    orch, events, memory = _orchestrator_with_capture()
    task = OrchestrationTask(scenario=ScenarioKind.RESUME_SCORING, goal="score resume")
    res = orch.orchestrate(task)
    assert res.status == "completed"
    assert res.consensus.reached is True
    assert isinstance(res.consensus.decision, float)
    # all 3 screeners ran
    assert set(res.outputs.keys()) >= {
        "tech_scorer", "culture_scorer", "domain_scorer",
    }
    # event was emitted
    assert any(e[0] == "multiagent.task.completed" for e in events)
    # memory was written
    assert len(memory) == 1


def test_orchestrator_bias_review_runs_writer_and_reviewer():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(
        scenario=ScenarioKind.BIAS_REVIEW,
        goal="review job ad",
        context={"draft": "young energetic developer"},
    )
    res = orch.orchestrate(task)
    assert "writer" in res.outputs
    assert "bias_reviewer" in res.outputs
    assert res.pattern.pattern == CollaborationPattern.DEBATE


def test_orchestrator_offer_negotiation_sequential():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(
        scenario=ScenarioKind.OFFER_NEGOTIATION, goal="draft offer"
    )
    res = orch.orchestrate(task)
    assert res.pattern.pattern == CollaborationPattern.SEQUENTIAL
    # final task's output is captured in consensus.decision
    assert res.consensus.decision is not None


def test_orchestrator_strategy_decode_hierarchical():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(
        scenario=ScenarioKind.STRATEGY_DECODE, goal="decode strategic plan"
    )
    res = orch.orchestrate(task)
    assert res.pattern.pattern == CollaborationPattern.HIERARCHICAL
    # PM ran first; later agents received its output
    pm_out = res.outputs.get("pm")
    assert pm_out is not None


def test_orchestrator_run_id_unique():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(scenario=ScenarioKind.RESUME_SCORING, goal="x")
    r1 = orch.orchestrate(task)
    r2 = orch.orchestrate(task)
    assert r1.run_id != r2.run_id


def test_orchestrator_pattern_override():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING,
        goal="x",
        pattern=CollaborationPattern.SEQUENTIAL,
    )
    res = orch.orchestrate(task)
    assert res.pattern.pattern == CollaborationPattern.SEQUENTIAL


def test_orchestrator_consensus_override():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING,
        goal="x",
        consensus=ConsensusStrategy.UNANIMOUS,
    )
    res = orch.orchestrate(task)
    assert res.consensus.strategy == ConsensusStrategy.UNANIMOUS


def test_orchestrator_aorchestrate_runs_in_executor():
    orch, _, _ = _orchestrator_with_capture()
    task = OrchestrationTask(scenario=ScenarioKind.RESUME_SCORING, goal="x")
    res = asyncio.run(orch.aorchestrate(task))
    assert res.status == "completed"


def test_orchestrator_max_rounds_caps_runs():
    orch, _, _ = _orchestrator_with_capture()
    # bias review (debate) loops when reviewer rejects; cap at 2
    task = OrchestrationTask(
        scenario=ScenarioKind.BIAS_REVIEW,
        goal="x",
        max_rounds=2,
    )
    res = orch.orchestrate(task)
    assert res.rounds <= 2


def test_orchestrator_handles_executor_exception():
    def bad_exec(agent, task, ctx):
        raise RuntimeError("kaboom")

    orch = Orchestrator(executor=bad_exec)
    res = orch.orchestrate(OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING, goal="x"
    ))
    assert res.status == "failed"
    assert "kaboom" in (res.error or "")


def test_orchestrator_emit_failure_does_not_crash():
    def bad_emit(name, payload):
        raise RuntimeError("bus down")

    orch = Orchestrator(event_emitter=bad_emit)
    res = orch.orchestrate(OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING, goal="x"
    ))
    assert res.status == "completed"


def test_orchestrator_memory_write_failure_does_not_crash():
    def bad_mem(payload):
        raise RuntimeError("store down")

    orch = Orchestrator(memory_writer=bad_mem)
    res = orch.orchestrate(OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING, goal="x"
    ))
    assert res.status == "completed"


def test_get_orchestrator_singleton():
    o1 = get_orchestrator()
    o2 = get_orchestrator()
    assert o1 is o2


def test_reset_orchestrator_clears():
    o1 = get_orchestrator()
    reset_orchestrator()
    o2 = get_orchestrator()
    assert o1 is not o2


def test_orchestrator_list_scenarios():
    orch, _, _ = _orchestrator_with_capture()
    assert len(orch.list_scenarios()) == 4


# =====================================================================
# CrewAI vendor-in shims
# =====================================================================

def test_crew_process_enum():
    assert CrewProcess.SEQUENTIAL.value == "sequential"
    assert CrewProcess.HIERARCHICAL.value == "hierarchical"


def test_agent_to_dict():
    a = Agent(role="x", goal="y", backstory="z", tools=["t1"])
    d = a.to_dict()
    assert d["role"] == "x" and "t1" in d["tools"]


def test_task_to_dict():
    a = Agent(role="x", goal="y", backstory="z")
    t = Task(description="do it", agent=a, expected_output="res")
    d = t.to_dict()
    assert d["description"] == "do it"
    assert d["has_context"] is False


def test_crew_to_dict():
    a = Agent(role="x", goal="y", backstory="z")
    t = Task(description="d", agent=a)
    crew = Crew(agents=[a], tasks=[t], process=CrewProcess.SEQUENTIAL)
    d = crew.to_dict()
    assert d["process"] == "sequential"
    assert len(d["agents"]) == 1
    assert len(d["tasks"]) == 1


def test_default_executor_returns_dict():
    a = Agent(role="r", goal="g", backstory="b")
    t = Task(description="describe the candidate", agent=a)
    out = default_executor(a, t, {"input": "alice"})
    assert isinstance(out, dict)
    assert "decision" in out
    assert "confidence" in out


def test_default_executor_score_includes_keywords():
    a = Agent(role="r", goal="g", backstory="b")
    t = Task(description="score this fit", agent=a)
    high = default_executor(a, t, {"note": "strong expert lead"})
    low = default_executor(a, t, {"note": "weak junior intern"})
    assert high["decision"] > low["decision"]


# =====================================================================
# Scenario result shape
# =====================================================================

def test_orchestration_task_to_dict():
    task = OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING,
        goal="x",
        pattern=CollaborationPattern.SEQUENTIAL,
        consensus=ConsensusStrategy.MAJORITY,
    )
    d = task.to_dict()
    assert d["scenario"] == "resume_scoring"
    assert d["pattern"] == "sequential"
    assert d["consensus"] == "majority"


def test_orchestration_result_to_dict():
    orch, _, _ = _orchestrator_with_capture()
    res = orch.orchestrate(OrchestrationTask(
        scenario=ScenarioKind.RESUME_SCORING, goal="x"
    ))
    d = res.to_dict()
    assert d["task"]["scenario"] == "resume_scoring"
    assert d["status"] in ("completed", "failed", "no_consensus")
    assert "consensus" in d
    assert "crew" in d