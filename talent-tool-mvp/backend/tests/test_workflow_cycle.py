"""T5024 — WorkflowEngine cycle detection tests."""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.platform.workflow_engine import (  # noqa: E402
    CycleError,
    Edge,
    Node,
    RunStatus,
    WorkflowDefinition,
    WorkflowEngine,
    detect_cycles,
)


def _wf(nodes, edges, start=None):
    return WorkflowDefinition(
        name="g",
        start_node=start or nodes[0],
        nodes=[Node(id=n, type="action", config={"value": n}) for n in nodes],
        edges=[Edge(from_node=a, to_node=b) for a, b in edges],
    )


# ---------------------------------------------------------------------------
# detect_cycles
# ---------------------------------------------------------------------------

def test_acyclic_chain_passes():
    detect_cycles(_wf(["a", "b", "c"], [("a", "b"), ("b", "c")]))  # no raise


def test_diamond_acyclic_passes():
    detect_cycles(_wf(["a", "b", "c", "d"],
                      [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]))


def test_self_loop_detected():
    with pytest.raises(CycleError):
        detect_cycles(_wf(["a"], [("a", "a")]))


def test_two_node_cycle_detected():
    with pytest.raises(CycleError):
        detect_cycles(_wf(["a", "b"], [("a", "b"), ("b", "a")]))


def test_longer_cycle_detected():
    with pytest.raises(CycleError):
        detect_cycles(_wf(["a", "b", "c", "d"],
                          [("a", "b"), ("b", "c"), ("c", "d"), ("d", "b")]))


def test_cycle_through_conditional_branch_detected():
    wf = WorkflowDefinition(
        name="cond",
        start_node="a",
        nodes=[Node(id=n, type="action") for n in ("a", "b", "c")],
        edges=[
            Edge(from_node="a", to_node="b", condition="yes"),
            Edge(from_node="a", to_node="c", condition="no"),
            Edge(from_node="c", to_node="a"),  # back edge via the 'no' branch
        ],
    )
    with pytest.raises(CycleError):
        detect_cycles(wf)


# ---------------------------------------------------------------------------
# Engine integration — cyclic workflow fails fast
# ---------------------------------------------------------------------------

def test_engine_rejects_cyclic_workflow_without_running():
    eng = WorkflowEngine(node_retries=0)
    wf = _wf(["a", "b"], [("a", "b"), ("b", "a")])
    result = asyncio.run(eng.execute(wf, "in"))
    assert result.status == RunStatus.FAILED
    assert "cycle" in (result.error or "").lower()
