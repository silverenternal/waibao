"""v10.0 T5016 — Data-breach notification API (GDPR Art. 33 / Art. 34).

This router exposes the :mod:`services.compliance.breach` service as the
controller-facing workflow for managing a personal-data breach end-to-end:

Endpoints
---------
* ``POST   /api/breach``               register a breach, start the 72h clock
* ``GET    /api/breach``               list breaches (admin/compliance)
* ``GET    /api/breach/{id}``          fetch one breach
* ``GET    /api/breach/{id}/status``   live Art. 33 escalation status
* ``POST   /api/breach/{id}/notify-authority``  record Art. 33 authority notice
* ``POST   /api/breach/{id}/notify-subjects``   record Art. 34 subject notice
* ``POST   /api/breach/{id}/contain``  mark containment status

The 72-hour (GDPR) / 24-hour (PIPL) authority-notification window is computed
from ``awareness_at`` by the service; this layer is a thin, audited
pass-through.  Every mutation writes an :mod:`audit_v2` row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_admin
from services.compliance.breach import (
    VALID_SEVERITIES,
    BreachService,
    get_breach_service,
)
from services.platform.audit_v2 import audit

logger = logging.getLogger("waibao.api.breach")
router = APIRouter(prefix="/api/breach", tags=["breach"])


# ---------------------------------------------------------------------------
# Role gate — admin OR a synthetic "compliance" role carried on the JWT.
# ---------------------------------------------------------------------------
def _is_authorised(user: CurrentUser) -> bool:
    role = getattr(user, "role", None)
    role_val = role.value if hasattr(role, "value") else str(role)
    return role_val in {"admin", "compliance"}


def _require_breach_authority(user: CurrentUser) -> None:
    if not _is_authorised(user):
        raise HTTPException(status_code=403, detail="admin/compliance only")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class BreachCreate(BaseModel):
    severity: str = Field(..., description="low|medium|high|critical")
    description: str = Field(..., min_length=1)
    region: str = Field("EU", description="EU|CN|CA|GLOBAL — drives the deadline")
    categories_affected: list[str] = Field(default_factory=list)
    subjects_affected: int = Field(0, ge=0)
    records_affected: int = Field(0, ge=0)
    occurred_at: Optional[datetime] = None
    awareness_at: Optional[datetime] = None
    notify_authority_now: bool = False
    notify_subjects_now: bool = False
    art34_exemption: Optional[str] = Field(
        None,
        description=(
            "If an Art. 34 exemption applies, record which one: "
            "'appropriately_protected' | 'no_high_risk' | 'disproportionate_effort'"
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContainBody(BaseModel):
    status: str = Field("contained", description="open|contained|resolved")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _svc() -> BreachService:
    return get_breach_service()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
async def register_breach(
    body: BreachCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Art. 33 — register a breach and start the authority-notification clock."""
    _require_breach_authority(user)
    if body.severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"invalid severity: {body.severity}")
    svc = _svc()
    rec = svc.register(
        severity=body.severity,
        description=body.description,
        region=body.region,
        tenant_id=getattr(user, "tenant_id", None),
        categories_affected=body.categories_affected,
        subjects_affected=body.subjects_affected,
        records_affected=body.records_affected,
        occurred_at=body.occurred_at,
        awareness_at=body.awareness_at,
        created_by=str(user.id),
        notify_authority=body.notify_authority_now,
        notify_subjects=body.notify_subjects_now,
        art34_exemption=body.art34_exemption,
        metadata=body.metadata,
    )
    audit(
        action="create",
        resource="data_breach",
        resource_id=rec.id,
        pii_fields=body.categories_affected,
        lawful_basis="gdpr_legal_obligation",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        tenant_id=getattr(user, "tenant_id", None),
        metadata={
            "severity": body.severity,
            "region": body.region,
            "subjects": body.subjects_affected,
            "deadline": rec.authority_deadline.isoformat(),
            "high_risk_to_subjects": rec.high_risk_to_subjects,
        },
    )
    return rec.to_dict()


@router.get("")
async def list_breaches(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    _require_breach_authority(user)
    svc = _svc()
    rows = svc.list(tenant_id=getattr(user, "tenant_id", None), limit=limit)
    return {"items": [r.to_dict() for r in rows]}


@router.get("/{breach_id}")
async def get_breach(
    breach_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    _require_breach_authority(user)
    rec = _svc().get(breach_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="breach not found")
    return rec.to_dict()


@router.get("/{breach_id}/status")
async def breach_status(
    breach_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Live Art. 33 escalation state: on_time | imminent | breached | fulfilled."""
    _require_breach_authority(user)
    try:
        return _svc().escalation_status(breach_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="breach not found")


@router.post("/{breach_id}/notify-authority")
async def notify_authority(
    breach_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Record Art. 33 authority notification (idempotent)."""
    _require_breach_authority(user)
    svc = _svc()
    try:
        result = svc.notify_authority(breach_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="breach not found")
    audit(
        action="notify",
        resource="data_breach_authority",
        resource_id=breach_id,
        lawful_basis="gdpr_legal_obligation",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        metadata=result,
    )
    return result


@router.post("/{breach_id}/notify-subjects")
async def notify_subjects(
    breach_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Record Art. 34 subject notification (required when high_risk_to_subjects)."""
    _require_breach_authority(user)
    svc = _svc()
    try:
        result = svc.notify_subjects(breach_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="breach not found")
    audit(
        action="notify",
        resource="data_breach_subjects",
        resource_id=breach_id,
        lawful_basis="gdpr_legal_obligation",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        metadata=result,
    )
    return result


@router.post("/{breach_id}/contain")
async def contain_breach(
    breach_id: str,
    body: ContainBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Update containment status (open | contained | resolved)."""
    _require_breach_authority(user)
    svc = _svc()
    try:
        rec = svc.contain(breach_id, status=body.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="breach not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit(
        action="update",
        resource="data_breach",
        resource_id=breach_id,
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        metadata={"containment_status": body.status},
    )
    return rec.to_dict()


__all__ = ["router"]
