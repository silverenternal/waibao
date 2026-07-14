"""v6.0 T2105 — Workflow admin API.

Endpoints (under ``/api/workflows``):
- GET    /                       List all workflows + built-in templates
- GET    /templates              List built-in templates only
- GET    /{workflow_id}          Read one workflow definition
- POST   /                       Create or update a workflow
- DELETE /{workflow_id}          Delete a workflow
- POST   /{workflow_id}/run      Start a run with optional input payload
- POST   /{workflow_id}/validate Dry-run validation
- POST   /runs/{run_id}/resume   Resume a paused run with a decision
- POST   /runs/{run_id}/cancel   Cancel a run
- GET    /runs/{run_id}          Get run detail (status, nodes, output)
- GET    /runs                   List recent runs (optional workflow filter)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from services.platform import (
    Edge,
    Node,
    WorkflowDefinition,
    get_template,
    get_workflow_runner,
    get_workflow_store,
    list_templates,
    validate_definition,
)
from services.platform.audit_v2 import audit_pii

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class NodeBody(BaseModel):
    id: str
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    next_nodes: List[str] = Field(default_factory=list)


class EdgeBody(BaseModel):
    from_node: str
    to_node: str
    condition: Optional[str] = None


class WorkflowBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    version: str = "1.0"
    nodes: List[NodeBody] = Field(default_factory=list)
    edges: List[EdgeBody] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    start_node: Optional[str] = None
    category: Optional[str] = None
    is_template: bool = False
    created_by: Optional[str] = None


class RunBody(BaseModel):
    input: Any = None
    run_id: Optional[str] = None
    actor: Optional[str] = None


class ResumeBody(BaseModel):
    decision: Any = None
    actor: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body_to_definition(body: WorkflowBody) -> WorkflowDefinition:
    return WorkflowDefinition(
        name=body.name,
        version=body.version,
        description=body.description,
        start_node=body.start_node,
        variables=body.variables,
        nodes=[Node(id=n.id, type=n.type, config=n.config,
                    next_nodes=n.next_nodes) for n in body.nodes],
        edges=[Edge(from_node=e.from_node, to_node=e.to_node,
                    condition=e.condition) for e in body.edges],
    )


def _row_to_response(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "description": row.get("description"),
        "version": row.get("version", "1.0"),
        "definition": row.get("definition", {}),
        "is_template": row.get("is_template", False),
        "category": row.get("category"),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Templates (no DB)
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_builtin_templates() -> List[Dict[str, Any]]:
    return list_templates()


@router.get("/templates/{name}")
@audit_pii("read", "workflow_template", pii_fields=["name"], resource_id_arg="name")
async def get_builtin_template(name: str) -> Dict[str, Any]:
    try:
        wf = get_template(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return wf.to_dict()


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_workflows(include_templates: bool = Query(True)) -> List[Dict[str, Any]]:
    store = get_workflow_store()
    rows = await store.list_workflows()
    if not include_templates:
        rows = [r for r in rows if not r.get("is_template")]
    return [_row_to_response(r) for r in rows]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: int) -> Dict[str, Any]:
    row = await get_workflow_store().get_workflow(workflow_id)
    if row is None:
        raise HTTPException(404, f"workflow {workflow_id} not found")
    return _row_to_response(row)


@router.post("")
async def upsert_workflow(body: WorkflowBody) -> Dict[str, Any]:
    if not body.nodes:
        raise HTTPException(400, "workflow must have at least one node")
    definition = _body_to_definition(body)
    payload = {
        "name": body.name,
        "description": body.description,
        "definition": definition.to_dict(),
        "version": body.version,
        "is_template": body.is_template,
        "category": body.category,
        "created_by": body.created_by,
    }
    row = await get_workflow_store().upsert_workflow(payload)
    return _row_to_response(row)


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: int) -> Dict[str, Any]:
    ok = await get_workflow_store().delete_workflow(workflow_id)
    if not ok:
        raise HTTPException(404, f"workflow {workflow_id} not found")
    return {"deleted": True, "id": workflow_id}


# ---------------------------------------------------------------------------
# Validation + run
# ---------------------------------------------------------------------------

@router.post("/{workflow_id}/validate")
async def validate_workflow(body: WorkflowBody) -> Dict[str, Any]:
    definition = _body_to_definition(body)
    return validate_definition(definition)


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: int, body: RunBody) -> Dict[str, Any]:
    store = get_workflow_store()
    row = await store.get_workflow(workflow_id)
    if row is None:
        raise HTTPException(404, f"workflow {workflow_id} not found")
    definition = _definition_from_row(row)
    if definition is None:
        raise HTTPException(400, "stored workflow has empty definition")

    runner = get_workflow_runner()
    result = await runner.run(definition,
                              workflow_id=workflow_id,
                              input=body.input,
                              run_id=body.run_id)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Run inspection + lifecycle
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    row = await get_workflow_store().get_run(run_id)
    if row is None:
        raise HTTPException(404, f"run {run_id} not found")
    return row


@router.get("/runs")
async def list_runs(workflow_id: Optional[int] = Query(None),
                   limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    return await get_workflow_store().list_runs(workflow_id=workflow_id,
                                                 limit=limit)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, body: ResumeBody) -> Dict[str, Any]:
    store = get_workflow_store()
    row = await store.get_run(run_id)
    if row is None:
        raise HTTPException(404, f"run {run_id} not found")
    workflow_row = None
    if row.get("workflow_id") is not None:
        workflow_row = await store.get_workflow(row["workflow_id"])
    definition = _definition_from_row(workflow_row) if workflow_row else None
    result = await get_workflow_runner().resume(run_id,
                                                 decision=body.decision,
                                                 workflow_definition=definition,
                                                 workflow_id=row.get("workflow_id"))
    return result.to_dict()


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> Dict[str, Any]:
    result = await get_workflow_runner().cancel(run_id)
    return result.to_dict()


@router.get("/runs/{run_id}/timeline")
async def run_timeline(run_id: str) -> Dict[str, Any]:
    """T5024 — return the per-run event timeline (started/completed/failed/
    paused/retried/cancelled/resumed) for observability + debugging."""
    timeline = get_run_timeline(run_id)
    return {"run_id": run_id, "events": timeline}


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------

def get_run_timeline(run_id: str) -> List[Dict[str, Any]]:
    """Return the recorded timeline for a run.

    The persistence manager (T5024) keeps an in-memory timeline that the
    engine emits to. When no timeline has been recorded yet we return an
    empty list so callers can always render the panel.
    """
    try:
        from services.platform.workflow_persistence import _global_timeline  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    return _global_timeline(run_id)


def _definition_from_row(row: Dict[str, Any]) -> Optional[WorkflowDefinition]:
    raw = row.get("definition") or {}
    if not raw:
        return None
    try:
        nodes = [Node(id=n["id"], type=n["type"],
                      config=n.get("config", {}),
                      next_nodes=n.get("next_nodes", []))
                 for n in raw.get("nodes", [])]
        edges = [Edge(from_node=e["from"], to_node=e["to"],
                      condition=e.get("condition"))
                 for e in raw.get("edges", [])]
        return WorkflowDefinition(
            name=raw.get("name") or row.get("name", "workflow"),
            version=raw.get("version", row.get("version", "1.0")),
            description=raw.get("description", row.get("description", "")),
            start_node=raw.get("start_node"),
            variables=raw.get("variables", {}),
            nodes=nodes,
            edges=edges,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not parse stored workflow: %s", exc)
        return None