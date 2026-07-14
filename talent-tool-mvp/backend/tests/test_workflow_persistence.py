"""T5024 — WorkflowEngine persistence + metrics + retry tests."""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.platform import nodes as wf_nodes  # noqa: E402
from services.platform.nodes import NodeContext, WorkflowNode  # noqa: E402
from services.platform.workflow_engine import (  # noqa: E402
    CycleError,
    Edge,
    Node,
    RunStatus,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowResult,
    detect_cycles,
)
from services.platform.workflow_persistence import (  # noqa: E402
    DBWorkflowStore,
    Timeline,
    TimelineEvent,
    WorkflowPersistenceManager,
)


# ---------------------------------------------------------------------------
# Custom test nodes (registered into the builtin table temporarily)
# ---------------------------------------------------------------------------

class _FlakyNode(WorkflowNode):
    type = "flaky_test"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, config, ctx):  # type: ignore[no-untyped-def]
        self.calls += 1
        succeed_on = config.get("succeed_on", 2)
        if self.calls < succeed_on:
            raise RuntimeError(f"flaky failure #{self.calls}")
        return {"ok": True, "attempts": self.calls}


class _SlowNode(WorkflowNode):
    type = "slow_test"

    async def execute(self, config, ctx):  # type: ignore[no-untyped-def]
        await asyncio.sleep(config.get("sleep", 10))
        return {"ok": True}


@pytest.fixture(autouse=True)
def _register_test_nodes():
    saved = dict(wf_nodes._BUILTIN_NODES)
    wf_nodes._BUILTIN_NODES["flaky_test"] = _FlakyNode
    wf_nodes._BUILTIN_NODES["slow_test"] = _SlowNode
    yield
    wf_nodes._BUILTIN_NODES.clear()
    wf_nodes._BUILTIN_NODES.update(saved)


def _linear(name="wf", node_type="action"):
    return WorkflowDefinition(
        name=name,
        start_node="a",
        nodes=[Node(id="a", type=node_type, config={"value": "x"}),
               Node(id="b", type=node_type, config={"value": "y"})],
        edges=[Edge(from_node="a", to_node="b")],
    )


# ---------------------------------------------------------------------------
# Metrics + retry + timeout
# ---------------------------------------------------------------------------

def test_engine_records_completion_metrics():
    eng = WorkflowEngine(node_retries=1)
    result = asyncio.run(eng.execute(_linear(), "in"))
    assert result.status == RunStatus.COMPLETED
    assert sum(m["completed"] for m in eng.metrics.values()) == 2


def test_engine_retries_failing_node_until_success():
    eng = WorkflowEngine(node_retries=3, node_timeout_s=5)
    wf = WorkflowDefinition(
        name="retry",
        start_node="a",
        nodes=[Node(id="a", type="flaky_test", config={"succeed_on": 2})],
        edges=[],
    )
    result = asyncio.run(eng.execute(wf, None))
    assert result.status == RunStatus.COMPLETED
    # one node recorded a completion; retries counted as errors
    assert eng.metrics["a"]["error"] >= 1
    assert eng.metrics["a"]["completed"] == 1


def test_engine_fails_after_exhausting_retries():
    eng = WorkflowEngine(node_retries=1, node_timeout_s=5)
    wf = WorkflowDefinition(
        name="retry-exhaust",
        start_node="a",
        nodes=[Node(id="a", type="flaky_test", config={"succeed_on": 99})],
        edges=[],
    )
    result = asyncio.run(eng.execute(wf, None))
    assert result.status == RunStatus.FAILED
    assert "failed after" in (result.error or "")


def test_node_timeout_is_enforced():
    eng = WorkflowEngine(node_timeout_s=0.2, node_retries=0)
    wf = WorkflowDefinition(
        name="timeout",
        start_node="a",
        nodes=[Node(id="a", type="slow_test", config={"sleep": 5})],
        edges=[],
    )
    result = asyncio.run(eng.execute(wf, None))
    assert result.status == RunStatus.FAILED
    assert eng.metrics["a"]["timeout"] >= 1


# ---------------------------------------------------------------------------
# Persistence manager (in-memory store) + timeline
# ---------------------------------------------------------------------------

def test_persistence_manager_save_load_resume_cancel():
    eng = WorkflowEngine(node_retries=0)
    pm = WorkflowPersistenceManager(eng)
    result = asyncio.run(eng.execute(_linear(), "in"))
    asyncio.run(pm.save(result))
    loaded = asyncio.run(pm.load(result.run_id))
    assert loaded is not None
    assert loaded.run_id == result.run_id

    cancelled = asyncio.run(pm.cancel(result.run_id))
    assert cancelled.status == RunStatus.CANCELLED


def test_timeline_records_events():
    eng = WorkflowEngine(node_retries=0)
    pm = WorkflowPersistenceManager(eng)
    asyncio.run(pm.record_node("run-1", "a", "started"))
    asyncio.run(pm.record_node("run-1", "a", "completed"))
    asyncio.run(pm.record_node("run-1", None, "cancelled"))
    events = asyncio.run(pm.timeline_for("run-1"))
    assert [e["event"] for e in events] == ["started", "completed", "cancelled"]


# ---------------------------------------------------------------------------
# DBWorkflowStore with a fake Supabase client
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, store):
        self.store = store
        self._payload = None
        self._filters = []

    def upsert(self, row):
        self._payload = row
        return self

    def select(self, *_):
        self._payload = {"__select__": True}
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def delete(self):
        self._payload = {"__delete__": True}
        return self

    def execute(self):
        if self._payload and "__select__" in self._payload:
            rows = [r for r in self.store["rows"]
                    if all(str(r.get(c)) == str(v) for c, v in self._filters)]
            return _Resp(rows)
        if self._payload and "__delete__" in self._payload:
            keep = [r for r in self.store["rows"]
                    if not all(str(r.get(c)) == str(v) for c, v in self._filters)]
            self.store["rows"] = keep
            return _Resp([])
        if self._payload:
            self.store["rows"] = [r for r in self.store["rows"]
                                  if r["id"] != self._payload["id"]]
            self.store["rows"].append(self._payload)
            return _Resp([self._payload])
        return _Resp(None)


class FakeDB:
    def __init__(self):
        self.store = {"rows": []}

    def table(self, name):
        return _Table(self.store)


def test_db_workflow_store_save_and_load():
    fake = FakeDB()
    store = DBWorkflowStore(client_factory=lambda: fake)
    result = WorkflowResult(run_id="r-db", status=RunStatus.COMPLETED, output={"done": True})
    asyncio.run(store.save(result))
    loaded = asyncio.run(store.load("r-db"))
    assert loaded is not None
    # store.load() returns the deserialised state dict
    assert loaded["run_id"] == "r-db"
    rows = asyncio.run(store.list_runs())
    assert len(rows) == 1


def test_db_workflow_store_delete():
    fake = FakeDB()
    store = DBWorkflowStore(client_factory=lambda: fake)
    result = WorkflowResult(run_id="r-del", status=RunStatus.COMPLETED)
    asyncio.run(store.save(result))
    assert asyncio.run(store.delete("r-del")) is True
    assert asyncio.run(store.load("r-del")) is None
