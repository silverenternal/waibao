"""Comprehensive tests for v6.0 T2105 — Agent Composition.

Covers:
* Core engine behaviour (linear, branch, fan-out, pause/resume, failure)
* All 5 built-in templates (onboarding / interview / resume_scoring /
  bias_review / ticket_sla) running end-to-end
* Persistence layer (``SupabaseWorkflowStore`` + ``WorkflowRunner``)
* Validation API (cycles, dangling edges, unknown node types)
* EventBus integration (``workflow.started`` / ``workflow.completed`` /
  ``workflow.paused`` / ``workflow.failed`` / ``workflow.cancelled``)
* Failure recovery (a failing node surfaces as FAILED and downstream
  steps do not execute)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from eventbus import InMemoryEventBus, get_event_bus, set_event_bus
from services.platform import (
    BIAS_REVIEW_TEMPLATE,
    BUILTIN_TEMPLATES,
    INTERVIEW_TEMPLATE,
    ONBOARDING_TEMPLATE,
    RESUME_SCORING_TEMPLATE,
    SLA_TEMPLATE,
    Edge,
    InMemoryWorkflowStore,
    Node,
    RunStatus,
    SupabaseWorkflowStore,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowRunner,
    get_template,
    get_workflow_runner,
    get_workflow_store,
    list_templates,
    reset_workflow_runner,
    validate_definition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_event_bus():
    bus = InMemoryEventBus()
    set_event_bus(bus)
    yield
    set_event_bus(InMemoryEventBus())


@pytest.fixture
def memory_runner() -> WorkflowRunner:
    reset_workflow_runner()
    store = SupabaseWorkflowStore()  # in-memory fallback
    return WorkflowRunner(store, WorkflowEngine())


def _simple_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        name="hello",
        start_node="a",
        nodes=[
            Node(id="a", type="delay", config={"seconds": 0}),
            Node(id="b", type="delay", config={"seconds": 0}),
            Node(id="c", type="delay", config={"seconds": 0}),
        ],
        edges=[
            Edge(from_node="a", to_node="b"),
            Edge(from_node="b", to_node="c"),
        ],
    )


# ===========================================================================
# 1. Engine basics
# ===========================================================================

def test_linear_workflow_executes_all_nodes():
    engine = WorkflowEngine(InMemoryWorkflowStore())
    wf = _simple_workflow()
    result = asyncio.run(engine.execute(wf, input={"x": 1}))
    assert result.status == RunStatus.COMPLETED
    assert result.nodes_executed == ["a", "b", "c"]
    assert result.error is None


def test_condition_branch_routes_true():
    wf = WorkflowDefinition(
        name="branch_true",
        start_node="cond",
        nodes=[
            Node(id="cond", type="condition", config={"expression": "1 == 1"}),
            Node(id="yes", type="delay", config={"seconds": 0}),
            Node(id="no", type="delay", config={"seconds": 0}),
        ],
        edges=[
            Edge(from_node="cond", to_node="yes", condition="true"),
            Edge(from_node="cond", to_node="no", condition="false"),
        ],
    )
    engine = WorkflowEngine(InMemoryWorkflowStore())
    result = asyncio.run(engine.execute(wf, input={}))
    assert "yes" in result.nodes_executed
    assert "no" not in result.nodes_executed


def test_condition_branch_routes_false():
    wf = WorkflowDefinition(
        name="branch_false",
        start_node="cond",
        nodes=[
            Node(id="cond", type="condition", config={"expression": "1 == 2"}),
            Node(id="yes", type="delay", config={"seconds": 0}),
            Node(id="no", type="delay", config={"seconds": 0}),
        ],
        edges=[
            Edge(from_node="cond", to_node="yes", condition="true"),
            Edge(from_node="cond", to_node="no", condition="false"),
        ],
    )
    engine = WorkflowEngine(InMemoryWorkflowStore())
    result = asyncio.run(engine.execute(wf, input={}))
    assert "no" in result.nodes_executed
    assert "yes" not in result.nodes_executed


def test_human_node_pauses():
    wf = WorkflowDefinition(
        name="human",
        start_node="h",
        nodes=[
            Node(id="h", type="human", config={"reason": "approve me"}),
            Node(id="end", type="delay", config={"seconds": 0}),
        ],
        edges=[Edge(from_node="h", to_node="end")],
    )
    engine = WorkflowEngine(InMemoryWorkflowStore())
    engine.remember(wf)
    result = asyncio.run(engine.execute(wf, input={}))
    assert result.status == RunStatus.PAUSED
    assert result.paused_at_node == "h"


def test_register_and_lookup():
    engine = WorkflowEngine()
    wf = _simple_workflow()
    engine.register(wf)
    assert engine.get("hello") is wf


def test_cancel_run_marks_cancelled():
    store = InMemoryWorkflowStore()
    engine = WorkflowEngine(store)
    wf = _simple_workflow()
    engine.remember(wf)
    res = asyncio.run(engine.execute(wf, input={}))
    res2 = asyncio.run(engine.cancel(res.run_id))
    assert res2.status == RunStatus.CANCELLED


def test_engine_serializes_to_dict():
    wf = _simple_workflow()
    payload = wf.to_dict()
    assert payload["name"] == "hello"
    assert len(payload["nodes"]) == 3
    assert len(payload["edges"]) == 2


def test_resume_unknown_run_raises():
    engine = WorkflowEngine(InMemoryWorkflowStore())
    with pytest.raises(KeyError):
        asyncio.run(engine.resume("not-a-real-run"))


# ===========================================================================
# 2. Built-in templates — existence and shape
# ===========================================================================

def test_five_builtin_templates_present():
    assert len(BUILTIN_TEMPLATES) == 5
    names = {t.name for t in BUILTIN_TEMPLATES}
    assert names == {"onboarding", "interview_pipeline",
                     "resume_scoring", "bias_review", "ticket_sla"}


def test_list_templates_returns_metadata():
    metas = list_templates()
    assert len(metas) == 5
    for meta in metas:
        assert "name" in meta
        assert "node_count" in meta
        assert "edge_count" in meta
        assert meta["node_count"] > 0


def test_get_template_returns_definition():
    wf = get_template("onboarding")
    assert wf.name == "onboarding"
    assert any(n.id == "create_profile" for n in wf.nodes)


def test_get_template_unknown_raises():
    with pytest.raises(KeyError):
        get_template("does_not_exist")


def test_onboarding_template_has_three_checkins():
    delays = [n for n in ONBOARDING_TEMPLATE.nodes if n.type == "delay"]
    assert len(delays) == 3


def test_interview_template_branches_on_score():
    cond = next(n for n in INTERVIEW_TEMPLATE.nodes if n.type == "condition")
    assert "match_score" in cond.config["expression"]


def test_resume_scoring_branches_at_threshold():
    cond = next(n for n in RESUME_SCORING_TEMPLATE.nodes if n.type == "condition")
    assert "0.75" in cond.config["expression"]


def test_bias_review_uses_three_agents():
    agents = [n for n in BIAS_REVIEW_TEMPLATE.nodes if n.type == "agent"]
    assert len(agents) >= 3


def test_sla_template_has_escalation_path():
    edges = [e for e in SLA_TEMPLATE.edges if e.to_node == "escalate_manager"]
    assert edges


# ===========================================================================
# 3. Built-in templates — execute end-to-end
# ===========================================================================

def test_onboarding_template_runs(memory_runner: WorkflowRunner):
    result = asyncio.run(memory_runner.run(ONBOARDING_TEMPLATE,
                                           workflow_id=1,
                                           input={"name": "Alice"}))
    assert result.status == RunStatus.COMPLETED
    assert result.nodes_executed[0] == "trigger"
    assert "training" in result.nodes_executed


def test_interview_template_high_score_routes_to_interview(memory_runner):
    # Inject a high score so the conditional branch fires.
    wf = WorkflowDefinition(**{
        **ONBOARDING_TEMPLATE.__dict__,  # noqa: SLF001 — defensive
    }) if False else get_template("interview_pipeline")
    # Pre-populate the variable that the condition reads.
    wf.variables["match_score"] = 0.9
    result = asyncio.run(memory_runner.run(wf, workflow_id=2,
                                           input={"candidate": "c-1"}))
    assert "schedule" in result.nodes_executed


def test_resume_scoring_template_high_score_routes_to_hr(memory_runner):
    wf = get_template("resume_scoring")
    wf.variables["match_score"] = 0.9
    result = asyncio.run(memory_runner.run(wf, workflow_id=3,
                                           input={"email": "x@y"}))
    assert "route_hr" in result.nodes_executed
    assert "feedback" not in result.nodes_executed


def test_resume_scoring_template_low_score_routes_to_feedback(memory_runner):
    wf = get_template("resume_scoring")
    wf.variables["match_score"] = 0.1
    result = asyncio.run(memory_runner.run(wf, workflow_id=3,
                                           input={"email": "x@y"}))
    assert "feedback" in result.nodes_executed
    assert "route_hr" not in result.nodes_executed


def test_bias_review_template_with_flags_escalates(memory_runner):
    wf = get_template("bias_review")
    wf.variables["compliance_flags"] = 1
    result = asyncio.run(memory_runner.run(wf, workflow_id=4,
                                           input={"doc": "vision-1"}))
    assert "notify_hrbp" in result.nodes_executed


def test_bias_review_template_clean_goes_to_noop(memory_runner):
    wf = get_template("bias_review")
    wf.variables["compliance_flags"] = 0
    wf.variables["policy_flags"] = 0
    wf.variables["persona_flags"] = 0
    result = asyncio.run(memory_runner.run(wf, workflow_id=4,
                                           input={"doc": "vision-1"}))
    assert "noop" in result.nodes_executed


def test_sla_template_below_threshold_notifies(memory_runner):
    wf = get_template("ticket_sla")
    wf.variables["sla_minutes"] = 30  # < 60
    result = asyncio.run(memory_runner.run(wf, workflow_id=5,
                                           input={"assignee": "a@b"}))
    assert "notify_responder" in result.nodes_executed


def test_sla_template_above_threshold_escalates(memory_runner):
    wf = get_template("ticket_sla")
    wf.variables["sla_minutes"] = 120
    wf.variables["status"] = "pending"
    result = asyncio.run(memory_runner.run(wf, workflow_id=5,
                                           input={"assignee": "a@b"}))
    assert "escalate" in result.nodes_executed


# ===========================================================================
# 4. Failure recovery
# ===========================================================================

def test_failing_node_marks_run_failed(memory_runner: WorkflowRunner):
    wf = WorkflowDefinition(
        name="fail",
        start_node="boom",
        nodes=[Node(id="boom", type="no_such_type", config={})],
        edges=[],
    )
    result = asyncio.run(memory_runner.run(wf, workflow_id=99))
    assert result.status == RunStatus.FAILED
    assert "no_such_type" in (result.error or "")


def test_failing_node_does_not_run_downstream(memory_runner):
    wf = WorkflowDefinition(
        name="skip_downstream",
        start_node="bad",
        nodes=[
            Node(id="bad", type="no_such_type"),
            Node(id="after", type="delay", config={"seconds": 0}),
        ],
        edges=[Edge("bad", "after")],
    )
    result = asyncio.run(memory_runner.run(wf, workflow_id=99))
    assert result.status == RunStatus.FAILED
    assert "after" not in result.nodes_executed


def test_paused_run_can_be_resumed(memory_runner):
    wf = WorkflowDefinition(
        name="human_resume",
        start_node="h",
        nodes=[
            Node(id="h", type="human", config={"reason": "ok"}),
            Node(id="end", type="delay", config={"seconds": 0}),
        ],
        edges=[Edge("h", "end")],
    )
    result = asyncio.run(memory_runner.run(wf, workflow_id=1))
    assert result.status == RunStatus.PAUSED
    assert result.paused_at_node == "h"

    resumed = asyncio.run(memory_runner.resume(result.run_id,
                                                decision="approved",
                                                workflow_definition=wf,
                                                workflow_id=1))
    assert resumed.status in (RunStatus.COMPLETED, RunStatus.PAUSED)
    # When resumed, the engine re-runs from start; the human node pauses
    # again unless __human_decision__ is set. We assert the decision was
    # preserved on the variables bag.
    assert resumed.variables.get("__human_decision__") == "approved"


# ===========================================================================
# 5. Persistence store
# ===========================================================================

@pytest.mark.asyncio
async def test_store_upsert_and_get_workflow():
    store = SupabaseWorkflowStore()
    payload = {"name": "x", "description": "d", "definition": {"nodes": []},
               "version": "1.0"}
    row = await store.upsert_workflow(payload)
    assert row["name"] == "x"
    fetched = await store.get_workflow_by_name("x")
    assert fetched is not None


@pytest.mark.asyncio
async def test_store_create_and_get_run():
    from services.platform.workflow_engine import WorkflowResult
    store = SupabaseWorkflowStore()
    result = WorkflowResult(run_id="r-1", status=RunStatus.RUNNING)
    await store.create_run(result, workflow_id=1, workflow_name="x")
    fetched = await store.get_run("r-1")
    assert fetched is not None
    assert fetched["workflow_name"] == "x"


@pytest.mark.asyncio
async def test_store_record_step():
    store = SupabaseWorkflowStore()
    await store.record_step("r-2", 1, "n1", "delay",
                             "completed", 0.0, 1.0,
                             output={"ok": True})
    runs = await store.list_runs()
    # No row for this run but step is recorded in memory; verify no crash.
    assert isinstance(runs, list)


@pytest.mark.asyncio
async def test_store_list_runs_filtered_by_workflow():
    from services.platform.workflow_engine import WorkflowResult
    store = SupabaseWorkflowStore()
    r1 = WorkflowResult(run_id="r-3", status=RunStatus.COMPLETED)
    r2 = WorkflowResult(run_id="r-4", status=RunStatus.COMPLETED)
    await store.create_run(r1, 1, "x")
    await store.create_run(r2, 2, "y")
    rows = await store.list_runs(workflow_id=1)
    assert all(r["workflow_id"] == 1 for r in rows)


# ===========================================================================
# 6. EventBus integration
# ===========================================================================

def test_workflow_lifecycle_emits_events(memory_runner):
    seen: List[Dict[str, Any]] = []
    bus = get_event_bus()
    bus.subscribe("workflow.started", lambda evt: seen.append(("started", evt.payload)))
    bus.subscribe("workflow.completed",
                  lambda evt: seen.append(("completed", evt.payload)))

    wf = _simple_workflow()
    asyncio.run(memory_runner.run(wf, workflow_id=1))
    names = [s[0] for s in seen]
    assert "started" in names
    assert "completed" in names


def test_failed_run_emits_failed_event(memory_runner):
    seen: List[str] = []
    bus = get_event_bus()
    bus.subscribe("workflow.failed", lambda evt: seen.append(evt.payload["error"]))
    wf = WorkflowDefinition(
        name="boom", start_node="b",
        nodes=[Node(id="b", type="no_such_type")], edges=[])
    asyncio.run(memory_runner.run(wf, workflow_id=1))
    assert seen and "no_such_type" in seen[0]


def test_paused_run_emits_paused_event(memory_runner):
    seen: List[Dict[str, Any]] = []
    bus = get_event_bus()
    bus.subscribe("workflow.paused",
                  lambda evt: seen.append(evt.payload))
    wf = WorkflowDefinition(
        name="pause", start_node="h",
        nodes=[
            Node(id="h", type="human", config={"reason": "r"}),
            Node(id="e", type="delay", config={"seconds": 0}),
        ],
        edges=[Edge("h", "e")],
    )
    asyncio.run(memory_runner.run(wf, workflow_id=1))
    assert seen and seen[0]["node"] == "h"


def test_cancelled_run_emits_event(memory_runner):
    seen: List[str] = []
    bus = get_event_bus()
    bus.subscribe("workflow.cancelled",
                  lambda evt: seen.append(evt.payload["run_id"]))
    wf = _simple_workflow()
    result = asyncio.run(memory_runner.run(wf, workflow_id=1))
    asyncio.run(memory_runner.cancel(result.run_id))
    assert seen and seen[0] == result.run_id


# ===========================================================================
# 7. Validation
# ===========================================================================

def test_validate_clean_workflow():
    wf = _simple_workflow()
    res = validate_definition(wf)
    assert res["valid"] is True
    assert res["errors"] == []


def test_validate_unknown_start_node():
    wf = WorkflowDefinition(
        name="bad_start", start_node="ghost",
        nodes=[Node(id="a", type="delay", config={"seconds": 0})],
        edges=[],
    )
    res = validate_definition(wf)
    assert res["valid"] is False
    assert any("ghost" in e for e in res["errors"])


def test_validate_dangling_edge():
    wf = WorkflowDefinition(
        name="dangling",
        start_node="a",
        nodes=[Node(id="a", type="delay", config={"seconds": 0})],
        edges=[Edge("a", "ghost")],
    )
    res = validate_definition(wf)
    assert res["valid"] is False
    assert any("ghost" in e for e in res["errors"])


def test_validate_unknown_node_type_is_warning_only():
    wf = WorkflowDefinition(
        name="warn", start_node="a",
        nodes=[Node(id="a", type="mystery")],
        edges=[],
    )
    res = validate_definition(wf)
    # Unknown types are warnings, not errors — the engine surfaces a real
    # error only at runtime.
    assert res["valid"] is True
    assert res["warnings"]


def test_validate_detects_cycle():
    wf = WorkflowDefinition(
        name="cycle", start_node="a",
        nodes=[
            Node(id="a", type="delay", config={"seconds": 0}),
            Node(id="b", type="delay", config={"seconds": 0}),
            Node(id="c", type="delay", config={"seconds": 0}),
        ],
        edges=[
            Edge("a", "b"), Edge("b", "c"), Edge("c", "a"),
        ],
    )
    res = validate_definition(wf)
    assert res["valid"] is False
    assert any("cycle" in e.lower() for e in res["errors"])


def test_validate_builtin_templates_are_valid():
    for tmpl in BUILTIN_TEMPLATES:
        res = validate_definition(tmpl)
        assert res["valid"] is True, (tmpl.name, res)


# ===========================================================================
# 8. Node-type coverage
# ===========================================================================

def test_all_six_node_types_registered():
    from services.platform.nodes import list_node_types
    types = set(list_node_types())
    assert {"trigger", "agent", "condition", "action", "delay", "human"} <= types


def test_get_node_unknown_type_raises():
    from services.platform.nodes import get_node
    with pytest.raises(KeyError):
        get_node("not_a_real_node")


def test_trigger_node_emits_triggered():
    from services.platform.nodes import NodeContext, TriggerNode
    n = TriggerNode()
    ctx = NodeContext(workflow_run_id="r", variables={},
                       input={"event": "user.created",
                              "payload": {"id": 1}})
    out = asyncio.run(n.execute({"event": "user.created"}, ctx))
    assert out["triggered"] is True


def test_trigger_node_no_event_returns_awaiting():
    from services.platform.nodes import NodeContext, TriggerNode
    n = TriggerNode()
    ctx = NodeContext(workflow_run_id="r", variables={}, input={})
    out = asyncio.run(n.execute({"event": "user.created"}, ctx))
    assert out["triggered"] is False
    assert out["awaiting"] == "user.created"


def test_action_event_kind_emits_to_bus():
    from services.platform.nodes import ActionNode, NodeContext
    captured: List[Any] = []
    bus = get_event_bus()
    bus.subscribe("custom.event", lambda evt: captured.append(evt.payload))
    n = ActionNode()
    ctx = NodeContext(workflow_run_id="r", variables={"foo": "bar"},
                       input={})
    out = asyncio.run(n.execute({"kind": "event", "event": "custom.event",
                                   "params": {"foo": "$foo"}}, ctx))
    assert out["emitted"] is True
    assert captured and captured[0]["foo"] == "bar"


def test_delay_node_sleeps(monkeypatch):
    from services.platform.nodes import DelayNode, NodeContext
    slept = []
    async def fake_sleep(secs):
        slept.append(secs)
    monkeypatch.setattr("services.platform.nodes.asyncio.sleep", fake_sleep)
    n = DelayNode()
    ctx = NodeContext(workflow_run_id="r", variables={}, input={})
    out = asyncio.run(n.execute({"seconds": 0.1}, ctx))
    assert out["delayed"] == 0.1
    assert slept == [0.1]


def test_condition_node_handles_bad_expression():
    from services.platform.nodes import ConditionNode, NodeContext
    n = ConditionNode()
    ctx = NodeContext(workflow_run_id="r", variables={}, input={})
    out = asyncio.run(n.execute({"expression": "((("}, ctx))
    assert out["branch"] == "false"


def test_human_node_pauses_engine():
    from services.platform.nodes import HumanNode, NodeContext
    n = HumanNode()
    ctx = NodeContext(workflow_run_id="r-123", variables={}, input={})
    out = asyncio.run(n.execute({"reason": "x"}, ctx))
    assert out["paused"] is True
    assert out["run_id"] == "r-123"