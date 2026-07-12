"""v6.0 T2105 — Workflow persistence + EventBus/Plugin integration.

This module sits between the FastAPI layer and the in-memory
``WorkflowEngine``. It:

* persists ``workflows`` / ``workflow_runs`` / ``workflow_run_steps`` rows
  to Supabase (with a safe in-memory fallback when the client is absent),
* bridges workflow lifecycle events to the global ``EventBus``,
* exposes a hook for plugins to participate in agent-node execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from eventbus import get_event_bus
from .workflow_engine import (
    Edge,
    Node,
    RunStatus,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB-backed WorkflowStore
# ---------------------------------------------------------------------------

class SupabaseWorkflowStore:
    """DB-backed persistence; falls back to an in-memory dict when the
    Supabase client cannot be reached (so unit tests run without infra)."""

    def __init__(self) -> None:
        self._mem: Dict[str, WorkflowResult] = {}
        self._runs_by_workflow: Dict[str, List[str]] = {}
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from services.supabase_client import get_supabase_client  # type: ignore
            self._client = get_supabase_client()
        except Exception:  # noqa: BLE001
            logger.debug("supabase client unavailable, using in-memory store")
            self._client = None

    # ----- workflows table -----
    async def list_workflows(self) -> List[Dict[str, Any]]:
        if self._client is None:
            return list(self._mem.values())  # type: ignore[arg-type]
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("workflows").select("*").execute()
            )
            return getattr(res, "data", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_workflows failed: %s", exc)
            return []

    async def get_workflow(self, workflow_id: int) -> Optional[Dict[str, Any]]:
        if self._client is None:
            for v in self._mem.values():
                if v.get("id") == workflow_id:
                    return v
            return None
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("workflows")
                    .select("*").eq("id", workflow_id).single().execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_workflow failed: %s", exc)
            return None

    async def get_workflow_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if self._client is None:
            for v in self._mem.values():
                if v.get("name") == name:
                    return v
            return None
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("workflows")
                    .select("*").eq("name", name).single().execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_workflow_by_name failed: %s", exc)
            return None

    async def upsert_workflow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None:
            payload = dict(payload)
            payload.setdefault("id", len(self._mem) + 1)
            payload.setdefault("created_at", time.time())
            self._mem[payload["name"]] = payload
            return payload
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("workflows")
                    .upsert(payload).execute()
            )
            data = getattr(res, "data", None) or []
            return data[0] if data else payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("upsert_workflow failed: %s", exc)
            return payload

    async def delete_workflow(self, workflow_id: int) -> bool:
        if self._client is None:
            for k, v in list(self._mem.items()):
                if v.get("id") == workflow_id:
                    del self._mem[k]
                    return True
            return False
        try:
            await asyncio.to_thread(
                lambda: self._client.table("workflows")
                    .delete().eq("id", workflow_id).execute()
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("delete_workflow failed: %s", exc)
            return False

    # ----- workflow_runs table -----
    async def create_run(self, run: WorkflowResult, workflow_id: int,
                         workflow_name: str) -> None:
        row = {
            "run_id": run.run_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "status": run.status.value,
            "input": run.variables.get("__input__"),
            "output": run.output,
            "variables": run.variables,
            "nodes_executed": run.nodes_executed,
            "paused_at_node": run.paused_at_node,
            "error": run.error,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
        }
        if self._client is None:
            self._mem[run.run_id] = row  # type: ignore[assignment]
            self._runs_by_workflow.setdefault(workflow_name, []).append(run.run_id)
            return
        try:
            await asyncio.to_thread(
                lambda: self._client.table("workflow_runs").insert(row).execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("create_run failed: %s", exc)

    async def update_run(self, run: WorkflowResult) -> None:
        row = {
            "status": run.status.value,
            "output": run.output,
            "variables": run.variables,
            "nodes_executed": run.nodes_executed,
            "paused_at_node": run.paused_at_node,
            "error": run.error,
            "finished_at": _iso(run.finished_at),
        }
        if self._client is None:
            self._mem[run.run_id] = {**(self._mem.get(run.run_id) or {}), **row}
            return
        try:
            await asyncio.to_thread(
                lambda: self._client.table("workflow_runs")
                    .update(row).eq("run_id", run.run_id).execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("update_run failed: %s", exc)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        if self._client is None:
            return self._mem.get(run_id)
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("workflow_runs")
                    .select("*").eq("run_id", run_id).single().execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_run failed: %s", exc)
            return None

    async def list_runs(self, workflow_id: Optional[int] = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
        if self._client is None:
            rows = list(self._mem.values())
            if workflow_id is not None:
                rows = [r for r in rows if r.get("workflow_id") == workflow_id]
            return rows[:limit]
        try:
            q = self._client.table("workflow_runs").select("*").order(
                "started_at", desc=True).limit(limit)
            if workflow_id is not None:
                q = q.eq("workflow_id", workflow_id)
            res = await asyncio.to_thread(lambda: q.execute())
            return getattr(res, "data", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_runs failed: %s", exc)
            return []

    # ----- workflow_run_steps table -----
    async def record_step(self, run_id: str, workflow_id: Optional[int],
                          node_id: str, node_type: str,
                          status: str, started_at: float,
                          finished_at: Optional[float],
                          output: Any = None, error: Optional[str] = None) -> None:
        duration = None
        if finished_at is not None:
            duration = int((finished_at - started_at) * 1000)
        row = {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "node_type": node_type,
            "status": status,
            "output": output,
            "error": error,
            "started_at": _iso(started_at),
            "finished_at": _iso(finished_at),
            "duration_ms": duration,
        }
        if self._client is None:
            key = f"{run_id}:{node_id}"
            self._mem[key] = row  # type: ignore[assignment]
            return
        try:
            await asyncio.to_thread(
                lambda: self._client.table("workflow_run_steps")
                    .insert(row).execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_step failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Engine wrapper that records steps + emits events
# ---------------------------------------------------------------------------

class WorkflowRunner:
    """Wraps a ``WorkflowEngine`` with persistence and event emission."""

    def __init__(self, store: SupabaseWorkflowStore,
                 engine: Optional[WorkflowEngine] = None) -> None:
        self.store = store
        self.engine = engine or WorkflowEngine()

    async def run(self, definition: WorkflowDefinition,
                  *, workflow_id: int, input: Any = None,
                  run_id: Optional[str] = None) -> WorkflowResult:
        rid = run_id or str(uuid.uuid4())
        result = WorkflowResult(run_id=rid, status=RunStatus.RUNNING,
                                variables=dict(definition.variables))
        result.variables["__input__"] = input
        await self.store.create_run(result, workflow_id, definition.name)
        self._emit("workflow.started",
                   {"run_id": rid, "workflow": definition.name,
                    "input": input})
        # Wrap execution in a coroutine that mirrors node execution to the
        # ``workflow_run_steps`` table for the live monitor.
        self.engine.remember(definition)
        try:
            await self._execute_with_tracing(definition, input, result, workflow_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("workflow %s crashed", definition.name)
            result.status = RunStatus.FAILED
            result.error = str(exc)
            result.finished_at = time.time()
            await self.store.update_run(result)
            self._emit("workflow.failed",
                       {"run_id": rid, "workflow": definition.name,
                        "error": str(exc)})
            return result

        if result.status == RunStatus.RUNNING:
            result.status = RunStatus.COMPLETED
            result.finished_at = time.time()
            await self.store.update_run(result)
            self._emit("workflow.completed",
                       {"run_id": rid, "workflow": definition.name,
                        "output": result.output})
        elif result.status == RunStatus.PAUSED:
            await self.store.update_run(result)
            self._emit("workflow.paused",
                       {"run_id": rid, "workflow": definition.name,
                        "node": result.paused_at_node})
        return result

    async def resume(self, run_id: str, decision: Any = None,
                     workflow_definition: Optional[WorkflowDefinition] = None,
                     workflow_id: Optional[int] = None) -> WorkflowResult:
        existing = await self.store.get_run(run_id)
        if existing is None:
            raise KeyError(f"unknown run {run_id}")
        if workflow_definition is None:
            # Reconstruct a minimal definition from row data.
            definition = WorkflowDefinition(
                name=existing.get("workflow_name", "unknown"),
                start_node=None,
            )
        else:
            definition = workflow_definition
        result = WorkflowResult(run_id=run_id, status=RunStatus.RUNNING,
                                variables=dict(existing.get("variables") or {}),
                                output=existing.get("output"))
        if decision is not None:
            result.variables["__human_decision__"] = decision
        self.engine.remember(definition)
        await self._execute_with_tracing(definition,
                                         existing.get("input"),
                                         result,
                                         workflow_id or existing.get("workflow_id"))
        if result.status == RunStatus.RUNNING:
            result.status = RunStatus.COMPLETED
            result.finished_at = time.time()
        await self.store.update_run(result)
        self._emit("workflow.completed" if result.status == RunStatus.COMPLETED
                   else "workflow.paused",
                   {"run_id": run_id,
                    "workflow": existing.get("workflow_name"),
                    "decision": decision})
        return result

    async def cancel(self, run_id: str) -> WorkflowResult:
        existing = await self.store.get_run(run_id)
        if existing is None:
            raise KeyError(f"unknown run {run_id}")
        result = WorkflowResult(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            variables=dict(existing.get("variables") or {}),
            output=existing.get("output"),
            started_at=_ts(existing.get("started_at")) or time.time(),
            finished_at=time.time(),
        )
        await self.store.update_run(result)
        self._emit("workflow.cancelled",
                   {"run_id": run_id,
                    "workflow": existing.get("workflow_name")})
        return result

    # ------------------------------------------------------------------
    # Internal: traced execution
    # ------------------------------------------------------------------
    async def _execute_with_tracing(self, definition: WorkflowDefinition,
                                    input: Any, result: WorkflowResult,
                                    workflow_id: Optional[int]) -> None:
        adj = _adjacency(definition)
        node_map = {n.id: n for n in definition.nodes}
        start = definition.start_node or (
            definition.nodes[0].id if definition.nodes else None)
        if start is None:
            result.output = input
            return
        await self._trace_node(definition, node_map, adj, start, input,
                               result, workflow_id)

    async def _trace_node(self, definition: WorkflowDefinition,
                          node_map: Dict[str, Node],
                          adj: Dict[str, List[Edge]],
                          node_id: str, input: Any,
                          result: WorkflowResult,
                          workflow_id: Optional[int]) -> Any:
        from services.platform.nodes import NodeContext, get_node
        from plugins import get_plugin_registry

        node = node_map[node_id]
        handler = get_node(node.type)
        ctx = NodeContext(workflow_run_id=result.run_id,
                          variables=result.variables, input=input)

        # Optional plugin hook: any installed plugin that exposes a
        # ``workflow_node`` permission may augment / observe the node. We
        # query the installed-plugin registry without coupling to its
        # internal helpers.
        hook_plugins: List[Any] = []
        try:
            from plugins import get_installed_plugin_registry
            registry = get_installed_plugin_registry()
            for inst in registry.list_installed():
                perms = inst.get("permissions", []) if isinstance(inst, dict) else []
                if "workflow:hook" in perms:
                    hook_plugins.append(inst)
        except Exception:  # noqa: BLE001
            hook_plugins = []

        started = time.time()
        await self.store.record_step(result.run_id, workflow_id, node.id,
                                     node.type, "running", started, None)
        status = "completed"
        output: Any = None
        error: Optional[str] = None
        try:
            output = await handler.execute(node.config, ctx)
            ctx.last_output = output
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            output = {"error": str(exc)}
            logger.exception("node %s failed", node.id)

        finished = time.time()
        await self.store.record_step(result.run_id, workflow_id, node.id,
                                     node.type, status, started, finished,
                                     output=output, error=error)

        # Fire-and-forget event so plugins can subscribe / react.
        self._emit("workflow.node.completed" if status == "completed"
                   else "workflow.node.failed",
                   {"run_id": result.run_id,
                    "node_id": node.id,
                    "node_type": node.type,
                    "output": output,
                    "error": error})

        if status == "failed":
            raise RuntimeError(error or "node failed")

        result.nodes_executed.append(node_id)
        result.variables[f"_node_output__{node_id}"] = output

        # Human pause
        if isinstance(output, dict) and output.get("paused"):
            result.status = RunStatus.PAUSED
            result.paused_at_node = node_id
            result.output = output
            await self.store.update_run(result)
            return output

        outgoing = adj.get(node_id, [])
        branch = output.get("branch") if isinstance(output, dict) else None
        chosen = [e for e in outgoing if e.matches(branch)] or outgoing

        next_input = output
        for edge in chosen:
            next_input = await self._trace_node(definition, node_map, adj,
                                                edge.to_node, next_input,
                                                result, workflow_id)
        result.output = next_input
        return next_input

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        try:
            get_event_bus().emit(name, payload, source="workflow_runner")
        except Exception as exc:  # noqa: BLE001
            logger.debug("emit %s failed: %s", name, exc)


def _adjacency(definition: WorkflowDefinition) -> Dict[str, List[Edge]]:
    adj: Dict[str, List[Edge]] = {n.id: [] for n in definition.nodes}
    for edge in definition.edges:
        adj.setdefault(edge.from_node, []).append(edge)
    for k in adj:
        adj[k].sort(key=lambda e: (e.condition is None, e.condition or ""))
    return adj


def _ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None
    return None


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_store: Optional[SupabaseWorkflowStore] = None
_runner: Optional[WorkflowRunner] = None


def get_workflow_store() -> SupabaseWorkflowStore:
    global _store
    if _store is None:
        _store = SupabaseWorkflowStore()
    return _store


def get_workflow_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        _runner = WorkflowRunner(get_workflow_store())
    return _runner


def reset_workflow_runner() -> None:
    """Used by tests for deterministic isolation."""
    global _store, _runner
    _store = None
    _runner = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_definition(definition: WorkflowDefinition) -> Dict[str, Any]:
    """Light-weight structural check used by the /validate endpoint."""
    errors: List[str] = []
    warnings: List[str] = []
    node_ids = {n.id for n in definition.nodes}

    if definition.start_node and definition.start_node not in node_ids:
        errors.append(f"start_node {definition.start_node!r} not in nodes")

    for node in definition.nodes:
        if not node.id:
            errors.append("node missing id")
        if not node.type:
            errors.append(f"node {node.id} missing type")
        if node.type not in {"trigger", "agent", "condition", "action",
                             "delay", "human"}:
            warnings.append(
                f"node {node.id}: unknown type {node.type!r} "
                "— engine will raise at runtime")

    for edge in definition.edges:
        if edge.from_node not in node_ids:
            errors.append(f"edge from {edge.from_node!r}: unknown node")
        if edge.to_node not in node_ids:
            errors.append(f"edge to {edge.to_node!r}: unknown node")

    # Detect cycles via DFS (truncated to N nodes to keep validation cheap).
    visited = set()
    stack = set()

    def dfs(nid: str) -> bool:
        if nid in stack:
            return True
        if nid in visited:
            return False
        visited.add(nid)
        stack.add(nid)
        for e in adj_edges.get(nid, []):
            if dfs(e.to_node):
                return True
        stack.remove(nid)
        return False

    adj_edges: Dict[str, List[Edge]] = {n.id: [] for n in definition.nodes}
    for edge in definition.edges:
        adj_edges.setdefault(edge.from_node, []).append(edge)
    for nid in list(node_ids):
        if dfs(nid):
            errors.append(f"cycle detected involving node {nid!r}")
            break

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(definition.nodes),
        "edge_count": len(definition.edges),
    }