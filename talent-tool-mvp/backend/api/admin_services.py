"""v8.0 T3501 — Admin API for Service Toggle.

Mounted under /api/admin/services (see main.py). All write endpoints
require the caller to be an admin; reads are open to authenticated users
so the catalog UI can render for everyone.

Implementation note: every endpoint uses ``Annotated[..., Depends(...)]``
to avoid FastAPI's BaseModel-as-body heuristic when ``CurrentUser`` is a
Pydantic model. Without this, FastAPI may parse ``user`` as a body field.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from services.platform.service_toggle import (
    DependencyError,
    ServiceNotFoundError,
    service_toggle,
)
from services.platform.service_registry import (
    catalog_snapshot,
    register_all,
    get_dependencies_for,
)
from services.platform.service_catalog import ServiceStatus

router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class StatusPatch(BaseModel):
    status: str
    reason: str = ""
    actor_id: Optional[str] = None


class OverrideIn(BaseModel):
    org_id: str
    status: str
    reason: str = ""
    expires_at: Optional[str] = None
    actor_id: Optional[str] = None


def _is_admin(user: CurrentUser) -> bool:
    role = getattr(user, "role", None)
    return (str(role).lower() if role is not None else "") == "admin"


def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="admin role required")
    return user


# ---------------------------------------------------------------------------
# Public reads (catalog for UI)
# ---------------------------------------------------------------------------
@router.get("")
async def list_services(
    plan: str = Query("free"),
    role: str = Query(""),
    _user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    """List every service with availability for (plan, role)."""
    items = service_toggle.get_catalog(plan=plan, role=role)
    return {
        "count": len(items),
        "plan": plan,
        "role": role,
        "items": items,
    }


@router.get("/dependencies")
async def dependency_graph(
    _user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    """Return the full dependency graph for visualization."""
    declared = catalog_snapshot()
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for svc in declared:
        nodes.append(
            {
                "id": svc["name"],
                "label": svc.get("display_name", svc["name"]),
                "category": svc.get("category", "misc"),
                "plan_required": svc.get("plan_required", "free"),
            }
        )
        for d in svc.get("dependencies", []):
            edges.append({"from": svc["name"], "to": d})
    return {"nodes": nodes, "edges": edges, "count": len(nodes)}


@router.get("/{name}")
async def get_service(
    name: str,
    _user: Annotated[CurrentUser, Depends(get_current_user)] = None,
):
    svc = service_toggle.get_service(name)
    if svc is None:
        raise HTTPException(status_code=404, detail="service not found")
    payload = svc.to_dict()
    payload["dependencies_resolved"] = service_toggle.resolve_dependencies(name)
    payload["dependents"] = service_toggle._find_dependents(name)
    payload["declared_dependencies"] = get_dependencies_for(name)
    return payload


# ---------------------------------------------------------------------------
# Admin writes
# ---------------------------------------------------------------------------
@router.patch("/{name}")
async def update_status(
    name: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
    body: StatusPatch = Body(...),
):
    """Toggle status to ``body.status`` (enabled/disabled/maintenance/beta)."""
    try:
        target = ServiceStatus.coerce(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid status {body.status!r}")
    actor_id = body.actor_id or str(user.id)
    try:
        if target == ServiceStatus.ENABLED:
            return {"ok": True, **service_toggle.enable(name, actor_id=actor_id, reason=body.reason)}
        if target == ServiceStatus.DISABLED:
            return {"ok": True, **service_toggle.disable(name, actor_id=actor_id, reason=body.reason)}
        return {
            "ok": True,
            **service_toggle._set_status(  # noqa: SLF001
                name,
                target,
                actor_id=actor_id,
                reason=body.reason,
            ),
        }
    except ServiceNotFoundError:
        raise HTTPException(status_code=404, detail="service not found")
    except DependencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{name}/override")
async def set_override(
    name: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
    body: OverrideIn = Body(...),
):
    """Force per-org status (highest priority)."""
    try:
        ov = service_toggle.override(
            org_id=body.org_id,
            name=name,
            status=body.status,
            reason=body.reason,
            expires_at=body.expires_at,
            actor_id=body.actor_id or str(user.id),
        )
    except (ValueError, ServiceNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "override": ov.to_dict()}


@router.post("/{name}/rollback")
async def rollback(
    name: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """One-click rollback to the previous status."""
    actor_id = str(user.id) if user is not None else "system"
    try:
        return {"ok": True, **service_toggle.rollback(name, actor_id=actor_id)}
    except ServiceNotFoundError:
        raise HTTPException(status_code=404, detail="service not found")


@router.post("/reload")
async def reload_registry(
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Force a fresh auto-discover + register_all pass (admin only)."""
    registered = register_all(persist=False)
    return {"ok": True, "registered": registered, "count": len(registered)}


# ---------------------------------------------------------------------------
# Public decision endpoint (for client hooks)
# ---------------------------------------------------------------------------
@router.get("/{name}/decide")
async def decide(
    name: str,
    plan: str = Query("free"),
    role: str = Query(""),
    org_id: Optional[str] = Query(None),
):
    """Return boolean decision for the client (no DB write)."""
    available = service_toggle.is_enabled(name, org_id, plan, role)
    svc = service_toggle.get_service(name)
    status = svc.status.value if svc else "disabled"
    plan_required = svc.plan_required.value if svc else "free"
    return {
        "name": name,
        "available": available,
        "status": status,
        "plan_required": plan_required,
        "role": role or None,
        "org_id": org_id,
        "reason": "" if available else "service_not_available",
    }
