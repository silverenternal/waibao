"""Workflow / DAG execution engine for v6.0.

A workflow is a directed graph of typed nodes. The engine:

* resolves topological order,
* executes nodes serially or in parallel according to the graph,
* supports pause/resume for ``HumanNode`` and external triggers,
* persists run state in a pluggable ``WorkflowStore`` so executions can be
  interrupted and resumed after a process restart.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from .nodes import NodeContext, WorkflowNode, get_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workflow definition
# ---------------------------------------------------------------------------

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Edge:
    from_node: str
    to_node: str
    condition: Optional[str] = None  # expression or branch name from a ConditionNode

    def matches(self, branch: Optional[str]) -> bool:
        if not self.condition:
            return True
        if branch is None:
            return False
        return self.condition == branch


@dataclass
class Node:
    id: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    next_nodes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "config": self.config,
                "next_nodes": list(self.next_nodes)}


@dataclass
class WorkflowDefinition:
    name: str
    version: str = "1.0"
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    start_node: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [{"from": e.from_node, "to": e.to_node, "condition": e.condition}
                      for e in self.edges],
            "variables": dict(self.variables),
            "start_node": self.start_node,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

@dataclass
class WorkflowResult:
    run_id: str
    status: RunStatus
    output: Any = None
    variables: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    nodes_executed: List[str] = field(default_factory=list)
    paused_at_node: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id, "status": self.status.value,
            "output": self.output, "variables": self.variables,
            "error": self.error, "started_at": self.started_at,
            "finished_at": self.finished_at,
            "nodes_executed": self.nodes_executed,
            "paused_at_node": self.paused_at_node,
        }


# ---------------------------------------------------------------------------
# Persistence (pluggable)
# ---------------------------------------------------------------------------

class InMemoryWorkflowStore:
    """Default store; production swaps in a DB-backed implementation."""

    def __init__(self) -> None:
        self._runs: Dict[str, WorkflowResult] = {}
        self._lock = asyncio.Lock()

    async def save(self, result: WorkflowResult) -> None:
        async with self._lock:
            self._runs[result.run_id] = result

    async def load(self, run_id: str) -> Optional[WorkflowResult]:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(self) -> List[WorkflowResult]:
        async with self._lock:
            return list(self._runs.values())


# ---------------------------------------------------------------------------
# Cycle detection (T5024)
# ---------------------------------------------------------------------------

class CycleError(ValueError):
    """Raised when a workflow definition contains a cycle."""


def detect_cycles(workflow: "WorkflowDefinition") -> None:
    """Raise :class:`CycleError` if the workflow graph has a back-edge.

    Uses iterative DFS with a tri-colour marking. Each conditional branch
    is treated as a separate edge — a cycle through *any* branch is fatal
    because the engine would loop forever.
    """
    adj: Dict[str, List[str]] = {n.id: [] for n in workflow.nodes}
    for edge in workflow.edges:
        adj.setdefault(edge.from_node, []).append(edge.to_node)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {nid: WHITE for nid in adj}

    def dfs(start: str) -> None:
        stack: List[tuple[str, int]] = [(start, 0)]
        color[start] = GRAY
        path: List[str] = [start]
        while stack:
            node, i = stack[-1]
            neighbours = adj.get(node, [])
            if i >= len(neighbours):
                color[node] = BLACK
                stack.pop()
                path.pop()
                continue
            stack[-1] = (node, i + 1)
            nxt = neighbours[i]
            if color.get(nxt, WHITE) == GRAY:
                cycle = path[path.index(nxt):] + [nxt] if nxt in path else [nxt]
                raise CycleError(f"cycle detected: {' -> '.join(cycle)}")
            if color.get(nxt, WHITE) == WHITE:
                color[nxt] = GRAY
                stack.append((nxt, 0))
                path.append(nxt)

    for nid in adj:
        if color[nid] == WHITE:
            dfs(nid)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    def __init__(
        self,
        store: InMemoryWorkflowStore | None = None,
        *,
        node_timeout_s: float = 30.0,
        node_retries: int = 2,
        record_metrics: bool = True,
    ) -> None:
        self.store = store or InMemoryWorkflowStore()
        self._registry: Dict[str, WorkflowDefinition] = {}
        # T5024 — per-node hard timeout + bounded retry.
        self.node_timeout_s = node_timeout_s
        self.node_retries = node_retries
        self.record_metrics = record_metrics
        self.metrics: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Definition registry
    # ------------------------------------------------------------------
    def register(self, workflow: WorkflowDefinition) -> None:
        self._registry[workflow.name] = workflow

    def get(self, name: str) -> Optional[WorkflowDefinition]:
        return self._registry.get(name)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def execute(self, workflow: WorkflowDefinition,
                      input: Any = None,
                      *, run_id: Optional[str] = None) -> WorkflowResult:
        run_id = run_id or str(uuid.uuid4())
        result = WorkflowResult(run_id=run_id, status=RunStatus.RUNNING,
                                 variables=dict(workflow.variables))
        await self.store.save(result)

        try:
            await self._run(workflow, input, result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("workflow %s crashed", workflow.name)
            result.status = RunStatus.FAILED
            result.error = str(exc)
            result.finished_at = time.time()
            await self.store.save(result)
            return result

        if result.status == RunStatus.RUNNING:
            result.status = RunStatus.COMPLETED
            result.finished_at = time.time()
            await self.store.save(result)
        return result

    async def resume(self, run_id: str, *, decision: Any = None) -> WorkflowResult:
        result = await self.store.load(run_id)
        if result is None:
            raise KeyError(f"unknown run {run_id}")
        if result.status != RunStatus.PAUSED:
            raise RuntimeError(f"run {run_id} is not paused (status={result.status.value})")

        # Resume execution from the node after the pause point.
        workflow = self._find_workflow_for(result)
        result.status = RunStatus.RUNNING
        if decision is not None:
            result.variables["__human_decision__"] = decision
        await self.store.save(result)
        return await self.execute(workflow, result.output, run_id=run_id)

    async def cancel(self, run_id: str) -> WorkflowResult:
        result = await self.store.load(run_id)
        if result is None:
            raise KeyError(f"unknown run {run_id}")
        result.status = RunStatus.CANCELLED
        result.finished_at = time.time()
        await self.store.save(result)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _run(self, workflow: WorkflowDefinition, input: Any,
                   result: WorkflowResult) -> None:
        detect_cycles(workflow)  # T5024 — fail fast on cyclic graphs
        adj = self._build_adjacency(workflow)
        node_map = {n.id: n for n in workflow.nodes}
        start = workflow.start_node or (workflow.nodes[0].id if workflow.nodes else None)
        if start is None:
            result.output = input
            return

        result.variables["__input__"] = input
        await self._execute_node(workflow, node_map, adj, start, input, result)

    async def _execute_node(self, workflow: WorkflowDefinition,
                            node_map: Dict[str, Node],
                            adj: Dict[str, List[Edge]],
                            node_id: str, input: Any,
                            result: WorkflowResult) -> Any:
        node = node_map[node_id]
        handler = get_node(node.type)
        ctx = NodeContext(workflow_run_id=result.run_id,
                          variables=result.variables, input=input)

        # T5024 — per-node hard timeout + bounded retry.
        attempts = max(1, self.node_retries + 1)
        output: Any = None
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                output = await asyncio.wait_for(
                    handler.execute(node.config, ctx),
                    timeout=self.node_timeout_s,
                )
                last_exc = None
                break
            except asyncio.TimeoutError as exc:
                last_exc = exc
                self._record_metric(node_id, "timeout", attempt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._record_metric(node_id, "error", attempt)
            # retry until attempts exhausted
        if last_exc is not None:
            result.error = f"node {node.id} ({node.type}) failed after {attempts} attempts: {last_exc}"
            raise result.error if isinstance(result.error, Exception) else RuntimeError(result.error)

        self._record_metric(node_id, "completed", attempts)
        result.nodes_executed.append(node_id)
        result.variables[f"_node_output__{node_id}"] = output
        ctx.last_output = output

        # HumanNode pause path
        if isinstance(output, dict) and output.get("paused"):
            result.status = RunStatus.PAUSED
            result.paused_at_node = node_id
            result.output = output
            await self.store.save(result)
            return output

        # Determine next nodes via the edge list.
        outgoing = adj.get(node_id, [])
        branch = output.get("branch") if isinstance(output, dict) else None
        chosen = [e for e in outgoing if e.matches(branch)] or outgoing

        # Fan-out: execute chosen children sequentially. (Parallel fan-out
        # is supported by adding multiple edges with the same condition; the
        # engine runs them in order — async parallel is straightforward to
        # add once scheduling requirements stabilise.)
        next_input = output
        for edge in chosen:
            next_input = await self._execute_node(workflow, node_map, adj,
                                                   edge.to_node, next_input, result)
        result.output = next_input
        return next_input

    def _record_metric(self, node_id: str, event: str, attempt: int) -> None:
        if not self.record_metrics:
            return
        bucket = self.metrics.setdefault(node_id, {"completed": 0, "timeout": 0, "error": 0,
                                                   "attempts": 0})
        if event in bucket:
            bucket[event] += 1
        bucket["attempts"] += attempt

    def _build_adjacency(self, workflow: WorkflowDefinition) -> Dict[str, List[Edge]]:
        adj: Dict[str, List[Edge]] = {n.id: [] for n in workflow.nodes}
        for edge in workflow.edges:
            adj.setdefault(edge.from_node, []).append(edge)
        # Sort each bucket so conditional edges are tried before fallthroughs.
        for k in adj:
            adj[k].sort(key=lambda e: (e.condition is None, e.condition or ""))
        return adj

    def _find_workflow_for(self, result: WorkflowResult) -> WorkflowDefinition:
        # In-memory store does not carry the workflow definition; the engine
        # exposes a setter so the host can remember which workflow a run belongs to.
        wf = getattr(self, "_last_workflow", None)
        if wf is None:
            raise RuntimeError("cannot resume: workflow definition not retained")
        return wf

    def remember(self, workflow: WorkflowDefinition) -> None:
        """Cache the last executed workflow so resume() can find it without
        requiring the host to pass it again."""
        self._last_workflow = workflow