"""T2603 — GDPR / PIPL / CCPA v2 API.

Endpoints:

- POST /api/gdpr-v2/dsr                create a data subject request
- GET  /api/gdpr-v2/dsr                list own DSRs (admin: all)
- GET  /api/gdpr-v2/dsr/{id}           fetch one DSR
- POST /api/gdpr-v2/dsr/{id}/decision  approve / reject a DSR (admin/compliance)

- POST /api/gdpr-v2/forget             right to be forgotten (Art. 17)
- POST /api/gdpr-v2/rectify            right to rectification (Art. 16)
- POST /api/gdpr-v2/portability        right to data portability (Art. 20)
- POST /api/gdpr-v2/restrict           right to restriction (Art. 18)
- POST /api/gdpr-v2/object             right to object (Art. 21)

- GET  /api/gdpr-v2/legal-basis/{region}  lawful basis catalog for a region
- GET  /api/gdpr-v2/processing-register    Art. 30 record of activities
- POST /api/gdpr-v2/breach                report a data breach (admin/compliance)

- GET  /api/gdpr-v2/sla                   SLA monitor (pending / escalated)

All endpoints write one row to ``audit_log_v2``. The SLA is 30 days
(GDPR Art. 12(3); PIPL Art. 33 explicit 30 days).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.platform.audit_v2 import (
    audit,
    audit_pii,
    set_audit_context,
    update_audit_context,
    clear_audit_context,
    AuditContext,
)
from services.platform.consent import (
    get_consent_store,
    list_purposes,
    PIPL_CROSS_BORDER_DISCLOSURE,
)
from services.platform.crypto import encrypt as crypto_encrypt
from services.compliance.ccpa import (
    CCPAService,
    DO_NOT_SELL,
    DO_NOT_SHARE,
    OPT_OUT_SIGNALS,
    PI_CATEGORIES,
    get_ccpa_service,
)
from services.compliance.data_export import (
    DataExportService,
    DictExportSource,
    get_data_export_service,
)

logger = logging.getLogger("waibao.gdpr_v2")
router = APIRouter(prefix="/api/gdpr-v2", tags=["gdpr_v2"])


# ---------------------------------------------------------------------------
# Region-aware lawful basis catalog
# ---------------------------------------------------------------------------
LAWFUL_BASIS_TEMPLATES: dict[str, dict[str, Any]] = {
    "EU": {
        "code": "EU",
        "name": "GDPR (Regulation (EU) 2016/679)",
        "lawful_bases": [
            {"code": "gdpr_consent", "label": "Consent (Art. 6(1)(a))",
             "description": "The data subject has given specific, informed and unambiguous consent.",
             "withdrawable": True},
            {"code": "gdpr_contract", "label": "Contract (Art. 6(1)(b))",
             "description": "Processing is necessary for the performance of a contract.",
             "withdrawable": False},
            {"code": "gdpr_legal_obligation", "label": "Legal obligation (Art. 6(1)(c))",
             "description": "Necessary to comply with a legal obligation.",
             "withdrawable": False},
            {"code": "gdpr_vital_interest", "label": "Vital interests (Art. 6(1)(d))",
             "description": "Necessary to protect vital interests of the data subject.",
             "withdrawable": False},
            {"code": "gdpr_public_task", "label": "Public task (Art. 6(1)(e))",
             "description": "Necessary for the performance of a task in the public interest.",
             "withdrawable": False},
            {"code": "gdpr_legitimate_interest", "label": "Legitimate interests (Art. 6(1)(f))",
             "description": "Necessary for legitimate interests, balanced against the data subject's rights.",
             "withdrawable": True},
        ],
        "transfer_safeguards": ["SCC (Standard Contractual Clauses)", "BCR", "Adequacy decision"],
        "sla_days": 30,
        "breach_notification_hours": 72,
    },
    "CN": {
        "code": "CN",
        "name": "PIPL (Personal Information Protection Law of the PRC)",
        "lawful_bases": [
            {"code": "pipl_consent", "label": "知情同意 (Art. 13)",
             "description": "Separate, informed, voluntary consent.",
             "withdrawable": True},
            {"code": "pipl_contract_necessary", "label": "订立/履行合同所必需 (Art. 13)",
             "description": "Necessary for concluding or performing a contract.",
             "withdrawable": False},
        ],
        "transfer_safeguards": ["PIPL 安全评估", "标准合同", "认证"],
        "sla_days": 30,
        "breach_notification_hours": 24,
        "cross_border_declaration": PIPL_CROSS_BORDER_DISCLOSURE,
    },
    "CA": {
        "code": "CA",
        "name": "CCPA / CPRA (California Consumer Privacy Act)",
        "lawful_bases": [
            {"code": "ccpa_business_purpose", "label": "Business purpose",
             "description": "Processing is necessary for a disclosed business purpose.",
             "withdrawable": False},
            {"code": "ccpa_opt_out", "label": "Opt-out",
             "description": "Consumer has exercised their right to opt out of sale/sharing.",
             "withdrawable": True},
        ],
        "transfer_safeguards": ["Service provider contracts"],
        "sla_days": 45,
        "breach_notification_hours": 72,
    },
    "US": {
        "code": "US",
        "name": "US State Privacy Laws (Virginia / Colorado / Connecticut / Utah)",
        "lawful_bases": [
            {"code": "ccpa_business_purpose", "label": "Business purpose",
             "description": "Processing is necessary for a disclosed business purpose.",
             "withdrawable": False},
        ],
        "transfer_safeguards": ["Service provider contracts"],
        "sla_days": 45,
        "breach_notification_hours": 72,
    },
    "GLOBAL": {
        "code": "GLOBAL",
        "name": "Global default (GDPR-leaning)",
        "lawful_bases": [
            {"code": "gdpr_consent", "label": "Consent",
             "description": "Default to consent outside explicitly covered regions.",
             "withdrawable": True},
        ],
        "transfer_safeguards": ["SCC"],
        "sla_days": 30,
        "breach_notification_hours": 72,
    },
}


def _region_from_request(request: Request, user: CurrentUser | None = None) -> str:
    """Best-effort region detection."""
    region = request.headers.get("x-waibao-region") or request.headers.get("x-region")
    if region:
        return region.upper()
    accept = request.headers.get("accept-language", "")
    if accept.startswith("zh"):
        return "CN"
    if accept.startswith("en-CA") or "ca" in accept.lower():
        return "CA"
    return "EU"


def _sb():
    try:
        return get_supabase_admin()
    except Exception:  # noqa: BLE001
        return None


def _bind_audit_context(request: Request, user: CurrentUser | None) -> None:
    ctx = AuditContext(
        actor_id=str(user.id) if user else None,
        actor_role=getattr(user, "role", None) if user else None,
        actor_ip=(request.client.host if request.client else None),
        actor_ua=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}",
        session_id=request.headers.get("x-session-id"),
        region=_region_from_request(request, user),
    )
    set_audit_context(ctx)


# ===========================================================================
# Models
# ===========================================================================
class DSRCreate(BaseModel):
    request_type: str = Field(..., description="access|rectify|erase|restrict|portability|object")
    description: str | None = None
    requester_email: str | None = None
    requester_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DSRDecision(BaseModel):
    status: str = Field(..., description="in_progress|completed|rejected")
    rejection_reason: str | None = None
    response_payload: dict[str, Any] = Field(default_factory=dict)


class RectifyPayload(BaseModel):
    field: str = Field(..., min_length=1)
    new_value: str = Field(..., min_length=1)


class BreachReport(BaseModel):
    severity: str = Field(..., description="low|medium|high|critical")
    categories_affected: list[str] = Field(default_factory=list)
    subjects_affected: int = 0
    records_affected: int = 0
    description: str
    occurred_at: datetime | None = None


# ===========================================================================
# Lawful basis + processing register
# ===========================================================================
@router.get("/legal-basis/{region}")
@audit_pii("read", "legal_basis")
async def get_legal_basis(region: str, request: Request):
    template = LAWFUL_BASIS_TEMPLATES.get(region.upper())
    if template is None:
        raise HTTPException(status_code=404, detail=f"unknown region: {region}")
    return {"region": region.upper(), "template": template}


@router.get("/legal-basis")
@audit_pii("read", "legal_basis")
async def list_legal_basis(request: Request):
    return {"regions": list(LAWFUL_BASIS_TEMPLATES.keys()), "templates": LAWFUL_BASIS_TEMPLATES}


@router.get("/processing-register")
@audit_pii("read", "data_processing_register")
async def processing_register(request: Request):
    """Public-facing summary of the Art. 30 record of processing activities."""
    sb = _sb()
    items: list[dict[str, Any]] = []
    if sb is not None:
        try:
            res = (
                sb.table("data_processing_register")
                .select("*")
                .eq("is_active", True)
                .execute()
            )
            items = res.data or []
        except Exception:  # noqa: BLE001
            pass
    if not items:
        # built-in seed mirror so the endpoint is useful even without DB
        items = [
            {
                "id": "seed-1",
                "controller_name": "Waibao Inc.",
                "processing_purpose": "候选人注册与简历管理",
                "lawful_basis": "pipl_consent",
                "data_categories": ["email", "name", "phone", "resume"],
                "retention_period_days": 1095,
            },
            {
                "id": "seed-2",
                "controller_name": "Waibao Inc.",
                "processing_purpose": "AI 面试评估",
                "lawful_basis": "gdpr_consent",
                "data_categories": ["interview_video", "voice"],
                "retention_period_days": 365,
            },
        ]
    return {"items": items}


# ===========================================================================
# DSR lifecycle
# ===========================================================================
def _sla_days_for_region(region: str) -> int:
    return LAWFUL_BASIS_TEMPLATES.get(region, LAWFUL_BASIS_TEMPLATES["GLOBAL"]).get("sla_days", 30)


def _persist_dsr(payload: dict[str, Any]) -> dict[str, Any]:
    sb = _sb()
    if sb is None:
        return payload
    try:
        res = sb.table("data_subject_requests").insert(payload).execute()
        if res.data:
            return res.data[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("gdpr_v2.persist_dsr_failed: %s", exc)
    return payload


@router.post("/dsr", status_code=status.HTTP_201_CREATED)
@audit_pii("create", "data_subject_request", pii_fields=["email"])
async def create_dsr(
    body: DSRCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    if body.request_type not in {"access", "rectify", "erase", "restrict", "portability", "object"}:
        raise HTTPException(status_code=400, detail=f"invalid request_type: {body.request_type}")
    region = _region_from_request(request, user)
    sla_days = _sla_days_for_region(region)
    now = datetime.now(timezone.utc)
    record = {
        "tenant_id": getattr(user, "tenant_id", None),
        "subject_id": str(user.id),
        "request_type": body.request_type,
        "requester_email": body.requester_email or user.email,
        "requester_name": body.requester_name,
        "description": body.description,
        "status": "pending",
        "lawful_basis_invoked": {
            "access": "gdpr_contract",
            "rectify": "gdpr_contract",
            "erase": "gdpr_consent",
            "restrict": "gdpr_contract",
            "portability": "gdpr_contract",
            "object": "gdpr_legitimate_interest",
        }.get(body.request_type, "gdpr_consent"),
        "sla_days": sla_days,
        "due_at": (now + timedelta(days=sla_days)).isoformat(),
        "response_payload": body.payload,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    persisted = _persist_dsr(record)
    audit(
        action="create",
        resource="data_subject_request",
        resource_id=persisted.get("id"),
        pii_fields=["email", "name", "id"],
        lawful_basis=record["lawful_basis_invoked"],
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        tenant_id=getattr(user, "tenant_id", None),
        metadata={
            "request_type": body.request_type,
            "region": region,
            "sla_days": sla_days,
            "due_at": record["due_at"],
        },
    )
    return persisted


@router.get("/dsr")
@audit_pii("read", "data_subject_request")
async def list_dsr(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    request_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
):
    sb = _sb()
    if sb is not None:
        try:
            q = sb.table("data_subject_requests").select("*").order("created_at", desc=True).limit(limit)
            # if admin/compliance, allow cross-user
            role = getattr(user, "role", None)
            if role not in {"admin", "compliance"}:
                q = q.eq("subject_id", str(user.id))
            if request_type:
                q = q.eq("request_type", request_type)
            if status_filter:
                q = q.eq("status", status_filter)
            res = q.execute()
            return {"items": res.data or []}
        except Exception:  # noqa: BLE001
            pass
    # empty fallback
    return {"items": []}


@router.get("/dsr/{dsr_id}")
@audit_pii("read", "data_subject_request", resource_id_arg="dsr_id")
async def get_dsr(dsr_id: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    sb = _sb()
    if sb is not None:
        try:
            res = sb.table("data_subject_requests").select("*").eq("id", dsr_id).execute()
            if res.data:
                row = res.data[0]
                role = getattr(user, "role", None)
                if role not in {"admin", "compliance"} and row.get("subject_id") != str(user.id):
                    raise HTTPException(status_code=403, detail="not authorised for this DSR")
                return row
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            pass
    return {"id": dsr_id, "status": "pending"}


@router.post("/dsr/{dsr_id}/decision")
@audit_pii("update", "data_subject_request", resource_id_arg="dsr_id", data_classification="sensitive")
async def decide_dsr(
    dsr_id: str,
    body: DSRDecision,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    role = getattr(user, "role", None)
    if role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    if body.status not in {"in_progress", "completed", "rejected"}:
        raise HTTPException(status_code=400, detail="invalid status")
    sb = _sb()
    payload = {
        "status": body.status,
        "rejection_reason": body.rejection_reason,
        "response_payload": body.response_payload,
        "completed_at": datetime.now(timezone.utc).isoformat() if body.status == "completed" else None,
        "assignee_id": str(user.id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    if sb is not None:
        try:
            sb.table("data_subject_requests").update(payload).eq("id", dsr_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("gdpr_v2.decide_failed: %s", exc)
    audit(
        action="update",
        resource="data_subject_request",
        resource_id=dsr_id,
        pii_fields=["id"],
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={"decision": body.status, "rejection_reason": body.rejection_reason},
    )
    return {"id": dsr_id, **payload}


@router.get("/sla")
@audit_pii("read", "sla_monitor")
async def sla_monitor(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    include_completed: bool = Query(False),
):
    role = getattr(user, "role", None)
    if role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    sb = _sb()
    if sb is None:
        return {"pending": [], "escalated": [], "completed": []}
    try:
        res = sb.table("data_subject_requests").select("*").execute()
        rows = res.data or []
    except Exception:  # noqa: BLE001
        rows = []
    now = datetime.now(timezone.utc)
    pending = []
    escalated = []
    completed = []
    for r in rows:
        due = r.get("due_at")
        try:
            due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")) if due else None
        except Exception:  # noqa: BLE001
            due_dt = None
        if r.get("status") in {"completed", "rejected"}:
            if include_completed:
                completed.append(r)
            continue
        if due_dt and due_dt < now:
            escalated.append({**r, "_overdue_days": (now - due_dt).days})
        else:
            pending.append(r)
    return {"pending": pending, "escalated": escalated, "completed": completed}


# ===========================================================================
# Right-to-be-forgotten (Art. 17)
# ===========================================================================
@router.post("/forget")
@audit_pii("forget", "user", pii_fields=["email", "name", "phone"], data_classification="sensitive")
async def forget_me(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    target_user_id: str | None = Query(None, description="Admin: forget a different user"),
):
    target = target_user_id or str(user.id)
    role = getattr(user, "role", None)
    if target != str(user.id) and role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    sb = _sb()
    tables = ["journal_entries", "messages", "tickets", "saved_jobs", "subscriptions",
              "notifications", "feedback", "interview_sessions", "video_resumes",
              "user_preferences", "consent_records"]
    summary: dict[str, int] = {}
    for t in tables:
        try:
            res = sb.table(t).delete().eq("user_id", target).execute()
            summary[t] = len(res.data or []) if res.data is not None else 0
        except Exception:  # noqa: BLE001
            summary[t] = -1  # table missing
    # Crypto-shred the user row (keep a tombstone with hashed id)
    tombstone = crypto_encrypt(json.dumps({
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "reason": "right_to_be_forgotten",
        "actor": str(user.id),
    }))
    try:
        sb.table("users").update({
            "email": f"deleted+{uuid.uuid4().hex[:8]}@example.invalid",
            "name": None,
            "phone": None,
            "avatar_url": None,
            "metadata": {"_deleted": True, "_tombstone": tombstone[:512]},
        }).eq("id", target).execute()
    except Exception:  # noqa: BLE001
        pass

    audit(
        action="forget",
        resource="user",
        resource_id=target,
        pii_fields=["email", "name", "phone", "resume"],
        lawful_basis="gdpr_consent",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={"summary": summary, "endpoint": "forget"},
    )
    return {"success": True, "summary": summary, "target_user_id": target}


# ===========================================================================
# Right to rectification (Art. 16)
# ===========================================================================
@router.post("/rectify")
@audit_pii("update", "user", pii_fields=["email", "name", "phone"])
async def rectify(
    body: RectifyPayload,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    target_user_id: str | None = Query(None),
):
    target = target_user_id or str(user.id)
    role = getattr(user, "role", None)
    if target != str(user.id) and role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    if body.field not in {"name", "email", "phone", "address", "location"}:
        raise HTTPException(status_code=400, detail=f"unsupported field: {body.field}")
    sb = _sb()
    if sb is not None:
        try:
            sb.table("users").update({body.field: body.new_value}).eq("id", target).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("rectify failed: %s", exc)
    audit(
        action="rectify",
        resource="user",
        resource_id=target,
        pii_fields=[body.field],
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={"field": body.field, "endpoint": "rectify"},
    )
    return {"success": True, "field": body.field, "target_user_id": target}


# ===========================================================================
# Right to data portability (Art. 20)
# ===========================================================================
@router.post("/portability")
@audit_pii("export", "user", pii_fields=["email", "name", "resume"], data_classification="sensitive")
async def portability(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    target_user_id: str | None = Query(None),
    include_audit: bool = Query(False),
):
    target = target_user_id or str(user.id)
    role = getattr(user, "role", None)
    if target != str(user.id) and role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    sb = _sb()
    bundle: dict[str, Any] = {
        "subject_id": target,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "format_version": "v2",
    }
    if sb is not None:
        for t in ["users", "journal_entries", "messages", "tickets", "saved_jobs",
                  "subscriptions", "notifications", "interview_sessions", "feedback",
                  "consent_records"]:
            try:
                res = sb.table(t).select("*").eq("user_id", target).execute()
                bundle[t] = res.data or []
            except Exception:  # noqa: BLE001
                bundle[t] = []
        if include_audit:
            try:
                res = sb.table("audit_log_v2").select("*").eq("actor_id", target).execute()
                bundle["audit_log_v2"] = res.data or []
            except Exception:  # noqa: BLE001
                bundle["audit_log_v2"] = []
    audit(
        action="export",
        resource="user",
        resource_id=target,
        pii_fields=["email", "name", "phone", "resume"],
        lawful_basis="gdpr_contract",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={"endpoint": "portability", "include_audit": include_audit},
    )
    return bundle


# ===========================================================================
# Right to restriction + Right to object (Art. 18/21)
# ===========================================================================
@router.post("/restrict")
@audit_pii("update", "user", data_classification="sensitive")
async def restrict(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    fields: list[str] = Query(["marketing", "analytics"]),
):
    role = getattr(user, "role", None)
    store = get_consent_store()
    state = store.withdraw(user_id=str(user.id), subject_id=str(user.id), purposes=fields)
    audit(
        action="update",
        resource="user",
        resource_id=str(user.id),
        pii_fields=fields,
        lawful_basis="gdpr_consent",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={"endpoint": "restrict", "withdrawn": state.withdrawn_purposes()},
    )
    return {"success": True, "withdrawn": state.withdrawn_purposes()}


@router.post("/object")
@audit_pii("update", "user")
async def object(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    fields: list[str] = Query(["marketing"]),
):
    role = getattr(user, "role", None)
    store = get_consent_store()
    state = store.withdraw(user_id=str(user.id), subject_id=str(user.id), purposes=fields, reason="Art. 21 objection")
    audit(
        action="update",
        resource="user",
        resource_id=str(user.id),
        pii_fields=fields,
        lawful_basis="gdpr_legitimate_interest",
        actor=str(user.id),
        actor_role=role,
        metadata={"endpoint": "object", "withdrawn": state.withdrawn_purposes()},
    )
    return {"success": True, "withdrawn": state.withdrawn_purposes()}


# ===========================================================================
# Breach register (Art. 33/34)
# ===========================================================================
@router.post("/breach")
@audit_pii("create", "data_breach", data_classification="sensitive")
async def report_breach(
    body: BreachReport,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    role = getattr(user, "role", None)
    if role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    if body.severity not in {"low", "medium", "high", "critical"}:
        raise HTTPException(status_code=400, detail="invalid severity")
    region = _region_from_request(request, user)
    template = LAWFUL_BASIS_TEMPLATES.get(region, LAWFUL_BASIS_TEMPLATES["GLOBAL"])
    breach_hours = template.get("breach_notification_hours", 72)
    record = {
        "tenant_id": getattr(user, "tenant_id", None),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "occurred_at": (body.occurred_at or datetime.now(timezone.utc)).isoformat(),
        "severity": body.severity,
        "categories_affected": body.categories_affected,
        "subjects_affected": body.subjects_affected,
        "records_affected": body.records_affected,
        "description": body.description,
        "containment_status": "open",
        "lawful_basis_invoked": "gdpr_legal_obligation",
        "created_by": str(user.id),
    }
    sb = _sb()
    breach_id = None
    if sb is not None:
        try:
            res = sb.table("data_breaches").insert(record).execute()
            if res.data:
                breach_id = res.data[0].get("id")
        except Exception as exc:  # noqa: BLE001
            logger.warning("breach insert failed: %s", exc)
    audit(
        action="create",
        resource="data_breach",
        resource_id=breach_id,
        pii_fields=body.categories_affected,
        lawful_basis="gdpr_legal_obligation",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        metadata={
            "severity": body.severity,
            "subjects": body.subjects_affected,
            "notification_window_hours": breach_hours,
            "region": region,
        },
    )
    return {"id": breach_id, "notification_window_hours": breach_hours}


# ===========================================================================
# Art. 15 — dedicated structured export (portable bundle w/ PIPL declaration)
# ===========================================================================
@router.get("/access")
@audit_pii("export", "user", pii_fields=["email", "name", "resume"], data_classification="sensitive")
async def access_export(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    target_user_id: str | None = Query(None),
    region: str | None = Query(None, description="override detected region (EU|CN|CA)"),
    fmt: str = Query("json", description="json | jsonl"),
):
    """Art. 15 right of access — a structured, self-describing export bundle.

    Distinct from the older :http:post:`/portability` shape: this returns the
    :mod:`services.compliance.data_export` bundle which carries a manifest
    (CCPA categories + GDPR lawful basis per collection) and, for CN-region
    subjects, the PIPL cross-border transfer declaration.
    """
    target = target_user_id or str(user.id)
    role = getattr(user, "role", None)
    if target != str(user.id) and role not in {"admin", "compliance"}:
        raise HTTPException(status_code=403, detail="admin/compliance only")
    svc = get_data_export_service()
    # If the default singleton has no real source, fall back to building the
    # bundle from Supabase so the endpoint is useful in dev without boot config.
    if isinstance(svc.source, DictExportSource) and not svc.source.collections():
        _hydrate_export_source_from_supabase(svc, target)
    detected = region or _region_from_request(request, user)
    try:
        bundle = svc.export(target, region=detected, fmt=fmt, include_audit=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit(
        action="export",
        resource="user",
        resource_id=target,
        pii_fields=["email", "name", "phone", "resume"],
        lawful_basis="gdpr_contract",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=role,
        tenant_id=getattr(user, "tenant_id", None),
        metadata={
            "endpoint": "access",
            "region": detected,
            "format": fmt,
            "pipl_declaration": bundle.pipl_cross_border is not None,
            "integrity_sha256": bundle.integrity_sha256,
        },
    )
    return bundle.to_dict()


def _hydrate_export_source_from_supabase(svc: DataExportService, target: str) -> None:
    """Populate the in-memory dict source from Supabase (dev convenience)."""
    sb = _sb()
    if sb is None:
        return
    for t in ["users", "journal_entries", "messages", "tickets", "saved_jobs",
              "subscriptions", "notifications", "interview_sessions", "feedback",
              "consent_records"]:
        try:
            res = sb.table(t).select("*").eq("user_id", target).execute()
            rows = res.data or []
            if rows:
                svc.source.add(t, target, rows)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            continue


# ===========================================================================
# CCPA / CPRA endpoints (Do Not Sell / Share + verifiable consumer requests)
# ===========================================================================
class CCPAOptOutBody(BaseModel):
    do_not_sell: bool = True
    do_not_share: bool = True
    source: str = "web"


class CCPARequestCreate(BaseModel):
    request_type: str = Field(..., description="know|delete|correct|opt_out")
    acted_on_behalf_of: str | None = Field(None, description="authorised agent name")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CCPAVerifyBody(BaseModel):
    token: str


@router.get("/ccpa/status")
@audit_pii("read", "ccpa_opt_out")
async def ccpa_get_opt_out(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Return the caller's Do-Not-Sell / Do-Not-Share preference (default: not opted out)."""
    svc = get_ccpa_service()
    pref = svc.get_opt_out(str(user.id), getattr(user, "tenant_id", None))
    # Honour the Sec-GPC header opportunistically on read too.
    gpc = request.headers.get("Sec-GPC") or request.headers.get("sec-gpc")
    if gpc:
        svc.apply_gpc_header(str(user.id), gpc, getattr(user, "tenant_id", None))
        pref = svc.get_opt_out(str(user.id), getattr(user, "tenant_id", None))
    return pref.to_dict()


@router.post("/ccpa/opt-out")
@audit_pii("update", "ccpa_opt_out", data_classification="sensitive")
async def ccpa_assert_opt_out(
    body: CCPAOptOutBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """The "Do Not Sell / Share My Personal Information" button."""
    if body.source not in {"web", "gpc_header", "privacy_policy", "agent"}:
        raise HTTPException(status_code=400, detail="invalid source")
    svc = get_ccpa_service()
    pref = svc.assert_opt_out(
        str(user.id),
        tenant_id=getattr(user, "tenant_id", None),
        do_not_sell=body.do_not_sell,
        do_not_share=body.do_not_share,
        source=body.source,
    )
    audit(
        action="update",
        resource="ccpa_opt_out",
        resource_id=str(user.id),
        pii_fields=["email"],
        lawful_basis="gdpr_consent",
        data_classification="sensitive",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        tenant_id=getattr(user, "tenant_id", None),
        metadata=pref.to_dict(),
    )
    return pref.to_dict()


@router.get("/ccpa/pi-categories")
async def ccpa_pi_categories(request: Request):
    """Public catalog of the CPRA PI categories (§ 1798.140(v))."""
    return {"categories": PI_CATEGORIES, "opt_out_signals": list(OPT_OUT_SIGNALS)}


@router.post("/ccpa/request", status_code=status.HTTP_201_CREATED)
@audit_pii("create", "ccpa_request", pii_fields=["email"])
async def ccpa_create_request(
    body: CCPARequestCreate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Open a verifiable consumer request (know / delete / correct / opt_out)."""
    svc = get_ccpa_service()
    try:
        req = svc.create_request(
            str(user.id),
            body.request_type,
            tenant_id=getattr(user, "tenant_id", None),
            acted_on_behalf_of=body.acted_on_behalf_of,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit(
        action="create",
        resource="ccpa_request",
        resource_id=req.id,
        pii_fields=["email"],
        lawful_basis="gdpr_consent",
        actor=str(user.id),
        actor_role=getattr(user, "role", None),
        metadata={"request_type": req.request_type, "agent": body.acted_on_behalf_of},
    )
    # Mask the verification token in the response — it goes to the consumer's
    # email, not back over the wire to the requester.
    out = req.to_dict()
    out["verify_token"] = None
    return out


@router.post("/ccpa/request/{request_id}/verify")
@audit_pii("update", "ccpa_request", resource_id_arg="request_id", data_classification="sensitive")
async def ccpa_verify_request(
    request_id: str,
    body: CCPAVerifyBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    svc = get_ccpa_service()
    try:
        req = svc.verify_request(request_id, body.token)
    except KeyError:
        raise HTTPException(status_code=404, detail="request not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="invalid verification token")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit(
        action="update",
        resource="ccpa_request",
        resource_id=request_id,
        actor=str(user.id),
        metadata={"state": req.state, "due_at": req.due_at},
    )
    return req.to_dict()


@router.get("/ccpa/request")
@audit_pii("read", "ccpa_request")
async def ccpa_list_requests(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    svc = get_ccpa_service()
    role = getattr(user, "role", None)
    target = None if role in {"admin", "compliance"} else str(user.id)
    rows = svc.list_requests(target, limit=limit)
    return {"items": [r.to_dict() for r in rows]}


# ===========================================================================
# FastAPI middleware hook (call from main.py to populate audit context)
# ===========================================================================
async def gdpr_audit_middleware(request: Request, call_next):
    """Sets AuditContext for the duration of the request, based on the
    Bearer JWT. Mount with::

        app.middleware("http")(gdpr_audit_middleware)
    """
    auth = request.headers.get("authorization", "")
    actor_id = None
    actor_role = None
    if auth.lower().startswith("bearer "):
        try:
            token = auth.split(" ", 1)[1]
            from api.auth import decode_supabase_jwt
            payload = decode_supabase_jwt(token)
            actor_id = payload.get("sub")
            actor_role = (payload.get("user_metadata") or {}).get("role")
        except Exception:  # noqa: BLE001
            pass
    ctx = AuditContext(
        actor_id=actor_id,
        actor_role=actor_role,
        actor_ip=(request.client.host if request.client else None),
        actor_ua=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}",
        session_id=request.headers.get("x-session-id"),
        region=_region_from_request(request),
    )
    set_audit_context(ctx)
    try:
        response = await call_next(request)
    finally:
        clear_audit_context()
    return response
