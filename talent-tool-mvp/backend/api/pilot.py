"""T1106 — Pilot API.

Endpoints:
- POST /api/pilot/programs                  创建 pilot (admin only)
- GET  /api/pilot/programs                  列表 (admin 看全部,partner 看自己 org)
- GET  /api/pilot/programs/{id}             详情
- POST /api/pilot/programs/{id}/start       开始试用 (admin)
- POST /api/pilot/programs/{id}/end         结束试用 (admin)
- POST /api/pilot/invite                    邀请用户 (admin/partner)
- POST /api/pilot/invitations/accept        token -> 接受邀请 (登录用户)
- GET  /api/pilot/programs/{id}/stats       试用统计 (NPS / 反馈数 / 活跃度)
- GET  /api/pilot/feedback                  反馈汇总 (admin)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.auth import CurrentUser, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.pilot_invitation import accept_invitation, create_invitation

logger = logging.getLogger("recruittech.api.pilot")
router = APIRouter()


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ProgramCreate(BaseModel):
    organisation_id: UUID
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    target_nps: int = Field(default=50, ge=-100, le=100)
    max_users: int = Field(default=20, ge=1, le=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InviteRequest(BaseModel):
    program_id: UUID
    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(default="jobseeker", pattern="^(jobseeker|employer|observer)$")
    ttl_days: int = Field(default=14, ge=1, le=60)
    send_email: bool = True

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, v: str) -> str:
        if "@" not in v or " " in v:
            raise ValueError("invalid email")
        return v.strip().lower()


class AcceptRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------


@router.post("/api/pilot/programs", status_code=201)
async def create_program(
    body: ProgramCreate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """创建一个 pilot program (管理员)."""
    supabase = get_supabase_admin()
    payload = body.model_dump()
    payload["organisation_id"] = str(payload["organisation_id"])
    payload["status"] = "recruiting"

    result = supabase.table("pilot_programs").insert(payload).execute()
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")
    return rows[0]


@router.get("/api/pilot/programs")
async def list_programs(
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
    status: Optional[str] = Query(None),
):
    """列出 pilot programs (admin 看全部;partner 仅看自己 org)."""
    supabase = get_supabase_admin()
    query = supabase.table("pilot_programs").select(
        "*, organisations(name)"
    ).order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if user.role == UserRole.talent_partner:
        # talent_partner 仅看自己 organisation
        me_resp = supabase.table("users").select("organisation_id").eq(
            "id", str(user.id)
        ).single().execute()
        org_id = (me_resp.data or {}).get("organisation_id")
        if not org_id:
            return {"data": [], "total": 0}
        query = query.eq("organisation_id", org_id)

    result = query.execute()
    return {"data": result.data or [], "total": len(result.data or [])}


@router.get("/api/pilot/programs/{program_id}")
async def get_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_programs")
        .select("*, organisations(name)")
        .eq("id", str(program_id))
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="pilot program not found")
    return resp.data


@router.post("/api/pilot/programs/{program_id}/start")
async def start_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """把 program 从 recruiting 切到 active,记录 started_at."""
    supabase = get_supabase_admin()
    now = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase.table("pilot_programs")
        .update({"status": "active", "started_at": now})
        .eq("id", str(program_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="pilot program not found")
    return rows[0]


@router.post("/api/pilot/programs/{program_id}/end")
async def end_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    now = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase.table("pilot_programs")
        .update({"status": "completed", "ended_at": now})
        .eq("id", str(program_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="pilot program not found")
    return rows[0]


# ---------------------------------------------------------------------------
# 邀请 / 接受
# ---------------------------------------------------------------------------


@router.post("/api/pilot/invite", status_code=201)
async def invite_user(
    body: InviteRequest,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    """邀请用户加入 pilot program (发邮件)."""
    try:
        invitation = await create_invitation(
            program_id=str(body.program_id),
            email=body.email,
            role=body.role,
            invited_by=str(user.id),
            ttl_days=body.ttl_days,
            send_email=body.send_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("invite_user failed")
        raise HTTPException(status_code=500, detail=f"invite failed: {exc}")

    return invitation.to_dict()


@router.post("/api/pilot/invitations/accept")
async def accept(
    body: AcceptRequest,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.talent_partner)),
):
    """被邀请者用 token 接受邀请 (需登录)."""
    try:
        result = await accept_invitation(token=body.token, user_id=str(user.id))
    except LookupError:
        raise HTTPException(status_code=404, detail="invitation not found")
    except PermissionError as exc:
        raise HTTPException(status_code=410, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("accept_invitation failed")
        raise HTTPException(status_code=500, detail=f"accept failed: {exc}")
    return result


# ---------------------------------------------------------------------------
# 反馈汇总 (admin dashboard)
# ---------------------------------------------------------------------------


def _compute_nps(rows: list[dict]) -> dict[str, Any]:
    """从 NPS 行计算 detractor / passive / promoter / nps.

    NPS = %promoter - %detractor (经典 Bain & Co. 公式).
    """
    if not rows:
        return {"nps": None, "promoters": 0, "passives": 0, "detractors": 0, "responses": 0}
    promoters = sum(1 for r in rows if r.get("score") is not None and r["score"] >= 9)
    detractors = sum(1 for r in rows if r.get("score") is not None and r["score"] <= 6)
    passives = sum(1 for r in rows if r.get("score") is not None and 6 < r["score"] < 9)
    total = promoters + detractors + passives
    if total == 0:
        return {"nps": None, "promoters": 0, "passives": 0, "detractors": 0, "responses": 0}
    nps = round((promoters - detractors) / total * 100, 1)
    return {
        "nps": nps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "responses": total,
    }


@router.get("/api/pilot/programs/{program_id}/stats")
async def program_stats(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    """试用统计: invitation 数 / accepted 数 / NPS / 反馈分类统计."""
    supabase = get_supabase_admin()

    inv_resp = (
        supabase.table("pilot_invitations")
        .select("id, status, role, email, accepted_at")
        .eq("program_id", str(program_id))
        .execute()
    )
    invs = inv_resp.data or []
    total_inv = len(invs)
    accepted_inv = [i for i in invs if i["status"] == "accepted"]

    fb_resp = (
        supabase.table("pilot_feedback")
        .select("id, category, score, comment, user_id, feature_used, created_at")
        .eq("program_id", str(program_id))
        .execute()
    )
    feedbacks = fb_resp.data or []
    nps_rows = [f for f in feedbacks if f.get("category") == "nps" and f.get("score") is not None]
    nps_stats = _compute_nps(nps_rows)

    # 分类计数
    category_counts: dict[str, int] = {}
    feature_counts: dict[str, int] = {}
    for f in feedbacks:
        cat = f.get("category") or "other"
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if f.get("feature_used"):
            feature_counts[f["feature_used"]] = feature_counts.get(f["feature_used"], 0) + 1

    # Top 痛点 = bug + feature_request 频次最高
    pain_points = sorted(
        (
            {"category": c, "count": category_counts.get(c, 0)}
            for c in ("bug", "feature_request")
        ),
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "program_id": str(program_id),
        "invitations": {
            "total": total_inv,
            "accepted": len(accepted_inv),
            "pending": sum(1 for i in invs if i["status"] == "pending"),
            "expired": sum(1 for i in invs if i["status"] == "expired"),
        },
        "nps": nps_stats,
        "feedback_by_category": category_counts,
        "feedback_by_feature": feature_counts,
        "top_pain_points": pain_points,
        "feedback_count": len(feedbacks),
    }


@router.get("/api/pilot/feedback")
async def list_feedback(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
    program_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """反馈汇总 (admin 视角),可按 program / category 过滤."""
    supabase = get_supabase_admin()
    query = (
        supabase.table("pilot_feedback")
        .select("*, users(email, first_name, last_name)")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if program_id:
        query = query.eq("program_id", str(program_id))
    if category:
        query = query.eq("category", category)
    result = query.execute()
    return {"data": result.data or [], "total": len(result.data or [])}


__all__ = ["router"]