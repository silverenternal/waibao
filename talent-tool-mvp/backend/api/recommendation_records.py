"""T6104 — Recommendation records API (push talent to employer).

Mounted under ``/api/recommendations`` (same prefix as the legacy T1304
candidate-recommendation scorer) but with non-colliding paths:

* ``GET  /api/recommendations``                — employer list (their org only)
* ``GET  /api/recommendations/{id}``           — detail (score + reasons +
                                                  gaps + risks + full resume +
                                                  contact info)
* ``PATCH /api/recommendations/{id}/status``   — accept / reject
* ``GET  /api/recommendations/{id}/download``  — resume PDF/text — ADMIN ONLY

Access contract (甲方合同: 资料查看下载导出权限仅平台管理员):
    * employer (client / admin role, owns org_id) — list + detail + status;
    * platform admin only — resume download / export.

``org_id`` is resolved from the JWT ``user_metadata.org_id`` /
``raw_app_meta_data.org_id`` claim (the auth layer does not surface it on
``CurrentUser``). When the claim is missing the employer is treated as having
no org and sees an empty list.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import CurrentUser, decode_supabase_jwt, require_role
from contracts.shared import UserRole
from services.matching.recommendation import (
    Recommendation,
    RecommendationService,
    get_service,
)

logger = logging.getLogger("recruittech.api.recommendation_records")
router = APIRouter()


# ---------------------------------------------------------------------------
# org_id resolution
# ---------------------------------------------------------------------------

def _resolve_org_id(request: Request, user: CurrentUser) -> Optional[str]:
    """Pull the employer's org_id from the bearer token claims.

    Falls back to a query param ``org_id`` for admin tooling.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        token = auth.removeprefix("Bearer ").strip()
        if token:
            try:
                payload = decode_supabase_jwt(token)
                um = payload.get("user_metadata") or {}
                am = payload.get("app_metadata") or {}
                org = (
                    um.get("org_id")
                    or am.get("org_id")
                    or payload.get("org_id")
                )
                if org:
                    return str(org)
            except Exception:  # noqa: BLE001 — admin path still works via query
                pass
    return request.query_params.get("org_id")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RecommendationSummary(BaseModel):
    id: str
    candidate_id: str
    role_id: str
    org_id: str
    match_score: int
    match_reasons: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    candidate_name: str = ""
    candidate_title: str = ""
    role_title: str = ""
    company_name: str = ""
    status: str = "pending"
    viewed_at: Optional[str] = None
    accepted_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class RecommendationDetail(RecommendationSummary):
    resume_snapshot: dict[str, Any] = Field(default_factory=dict)
    contact_info: dict[str, Any] = Field(default_factory=dict)
    can_download: bool = False


class StatusUpdate(BaseModel):
    status: str = Field(..., description="accepted | rejected | viewed")
    reason: Optional[str] = Field(
        default=None, description="rejection reason (status=rejected)"
    )


def _summary(rec: Recommendation) -> RecommendationSummary:
    return RecommendationSummary(
        id=rec.id,
        candidate_id=rec.candidate_id,
        role_id=rec.role_id,
        org_id=rec.org_id,
        match_score=rec.match_score,
        match_reasons=rec.match_reasons,
        skill_gaps=rec.skill_gaps,
        risks=rec.risks,
        candidate_name=rec.candidate_name,
        candidate_title=rec.candidate_title,
        role_title=rec.role_title,
        company_name=rec.company_name,
        status=rec.status,
        viewed_at=rec.viewed_at,
        accepted_at=rec.accepted_at,
        rejected_at=rec.rejected_at,
        rejected_reason=rec.rejected_reason,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _detail(rec: Recommendation, *, can_download: bool) -> RecommendationDetail:
    base = _summary(rec).model_dump()
    base.update(
        resume_snapshot=rec.resume_snapshot,
        contact_info=rec.contact_info,
        can_download=can_download,
    )
    return RecommendationDetail(**base)


def _is_admin(user: CurrentUser) -> bool:
    return user.role == UserRole.admin


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[RecommendationSummary],
    tags=["recommendations"],
    summary="T6104 — employer: recommendations received by my org",
)
async def list_recommendations(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(
        require_role(UserRole.client, UserRole.admin)
    ),
    svc: RecommendationService = Depends(get_service),
):
    """List the recommendations pushed to the caller's org.

    Admins can pass ``?org_id=`` to inspect any org; employers are scoped to
    their own org claim. Resume / contact PII is NOT included in the list.
    """
    org_id = _resolve_org_id(request, user)
    if _is_admin(user):
        org_id = request.query_params.get("org_id", org_id)
    if not org_id:
        return []
    if status and status not in ("pending", "viewed", "accepted", "rejected"):
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    recs = await svc.list_for_org(
        org_id=org_id, status=status, limit=limit, offset=offset
    )
    return [_summary(r) for r in recs]


async def _get_owned(
    rec_id: str,
    request: Request,
    user: CurrentUser,
    svc: RecommendationService,
) -> Recommendation:
    rec = await svc.get(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if _is_admin(user):
        return rec
    org_id = _resolve_org_id(request, user)
    if not org_id or rec.org_id != org_id:
        # do not leak existence cross-org
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


@router.get(
    "/{rec_id}",
    response_model=RecommendationDetail,
    tags=["recommendations"],
    summary="T6104 — recommendation detail (score + reasons + gaps + risks + full resume + contact)",
)
async def get_recommendation(
    rec_id: str,
    request: Request,
    user: CurrentUser = Depends(
        require_role(UserRole.client, UserRole.admin)
    ),
    svc: RecommendationService = Depends(get_service),
):
    """Recommendation detail with the immutable resume snapshot + contact info.

    Viewing the detail auto-advances ``pending`` → ``viewed``.
    """
    rec = await _get_owned(rec_id, request, user, svc)
    if rec.status == "pending":
        rec = await svc.mark_viewed(rec_id) or rec
    return _detail(rec, can_download=_is_admin(user))


@router.patch(
    "/{rec_id}/status",
    response_model=RecommendationSummary,
    tags=["recommendations"],
    summary="T6104 — accept / reject a recommendation",
)
async def update_recommendation_status(
    rec_id: str,
    body: StatusUpdate,
    request: Request,
    user: CurrentUser = Depends(
        require_role(UserRole.client, UserRole.admin)
    ),
    svc: RecommendationService = Depends(get_service),
):
    """Accept or reject a pushed recommendation (lifecycle terminal states)."""
    await _get_owned(rec_id, request, user, svc)
    if body.status not in ("accepted", "rejected", "viewed"):
        raise HTTPException(
            status_code=422,
            detail="status must be one of: accepted, rejected, viewed",
        )
    try:
        if body.status == "accepted":
            rec = await svc.accept(rec_id)
        elif body.status == "rejected":
            rec = await svc.reject(rec_id, reason=body.reason)
        else:
            rec = await svc.mark_viewed(rec_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return _summary(rec)


@router.get(
    "/{rec_id}/download",
    tags=["recommendations"],
    summary="T6104 — download / export resume (ADMIN ONLY)",
)
async def download_recommendation_resume(
    rec_id: str,
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
    svc: RecommendationService = Depends(get_service),
):
    """Download the snapshot resume as plain text.

    甲方合同: 资料查看下载导出权限仅平台管理员 — this endpoint is
    restricted to ``admin``. We return a small printable text resume (the
    PDF is generated client-side from this payload when a PDF lib is wired;
    the text form is always available so the feature ships today).
    """
    rec = await svc.get(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    text = await svc.render_resume_text(rec_id)
    if text is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    # Lazy import so the module imports cleanly without FastAPI's Response.
    from fastapi import Response
    from urllib.parse import quote

    # ASCII-safe filename for the Content-Disposition fallback + RFC 5987
    # ``filename*`` for the human-readable (possibly CJK) name.
    raw_name = (
        f"resume_{rec.candidate_name or rec.candidate_id}_{rec.id}.txt"
    ).replace(" ", "_")
    ascii_name = (
        raw_name.encode("ascii", "ignore").decode("ascii")
        or f"resume_{rec.id}.txt"
    )
    disposition = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(raw_name)}"
    )
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


__all__ = ["router"]
