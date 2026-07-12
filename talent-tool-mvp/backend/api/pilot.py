"""T1702 — Pilot API (v3.0, 改写).

Endpoints:
- POST /api/pilot/programs                  创建 pilot (admin)
- GET  /api/pilot/programs                  列表 (admin 全部 / partner 仅自己 org)
- GET  /api/pilot/programs/{id}             详情
- PATCH /api/pilot/programs/{id}            更新 (admin)
- DELETE /api/pilot/programs/{id}           删除 (admin)
- POST /api/pilot/programs/{id}/start       开始试用
- POST /api/pilot/programs/{id}/end         结束试用 + 记录最终 NPS
- POST /api/pilot/invite                    邀请用户
- POST /api/pilot/invitations/accept        token -> 接受邀请
- GET  /api/pilot/programs/{id}/stats       试用统计 (NPS / 反馈 / 周活 / Top 痛点)
- GET  /api/pilot/programs/{id}/report      完整报告 (JSON, admin)
- POST /api/pilot/programs/{id}/report/pdf  生成月度 PDF 报告 (admin)
- POST /api/pilot/feedback                  用户主动反馈
- POST /api/pilot/feedback/nps              NPS 评分
- POST /api/pilot/feedback/categorize       LLM 分类 (admin/debug)
- GET  /api/pilot/feedback                  反馈汇总 (admin)

业务方法下沉到 ``services.integrations.pilot_service`` / ``nps_service``,
本模块只负责 HTTP 路由 + 入参校验.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.integrations.nps_service import (
    CATEGORY_OTHER,
    SUPPORTED_CATEGORIES,
    CategorizedFeedback,
    calculate_nps,
    categorize_feedback,
)
from services.integrations.pilot_report import generate_monthly_report
from services.integrations.pilot_service import (
    NPS_TARGET,
    PROGRAM_STATUSES,
    TOP_PAIN_POINTS_LIMIT,
    WEEKLY_ACTIVE_TARGET,
    PilotReport,
    ProgramStats,
    create_program as svc_create_program,
    end_program as svc_end_program,
    generate_report as svc_generate_report,
    get_program as svc_get_program,
    get_stats as svc_get_stats,
    invite as svc_invite,
    list_programs as svc_list_programs,
)

logger = logging.getLogger("recruittech.api.pilot")
router = APIRouter()


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ProgramCreate(BaseModel):
    organisation_id: UUID
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    target_nps: int = Field(default=NPS_TARGET, ge=-100, le=100)
    max_users: int = Field(default=20, ge=1, le=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProgramUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    target_nps: Optional[int] = Field(None, ge=-100, le=100)
    max_users: Optional[int] = Field(None, ge=1, le=500)
    status: Optional[str] = Field(None, pattern="^(recruiting|active|completed|cancelled)$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProgramEndRequest(BaseModel):
    final_notes: Optional[str] = Field(None, max_length=2000)


class InviteRequest(BaseModel):
    program_id: UUID
    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(default="jobseeker", pattern="^(jobseeker|employer|observer|talent_partner|client|admin)$")
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


class FeedbackSubmit(BaseModel):
    """用户主动反馈 (非 NPS)."""

    category: str = Field(default=CATEGORY_OTHER, max_length=40)
    comment: str = Field(..., min_length=1, max_length=2000)
    feature_used: Optional[str] = Field(None, max_length=120)
    program_id: Optional[str] = None
    score: Optional[int] = Field(None, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NPSSubmit(BaseModel):
    score: int = Field(..., ge=0, le=10)
    comment: Optional[str] = Field(None, max_length=1000)
    feature_used: Optional[str] = Field(None, max_length=120)
    program_id: Optional[str] = None


class CategorizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    use_llm: bool = True


class CategorizeResponse(BaseModel):
    category: str
    confidence: float
    sentiment: str
    tags: list[str]
    rationale: str


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------


@router.post("/api/pilot/programs", status_code=201)
async def create_program(
    body: ProgramCreate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """创建一个 pilot program."""
    try:
        row = svc_create_program(
            organisation_id=str(body.organisation_id),
            name=body.name,
            description=body.description,
            target_nps=body.target_nps,
            max_users=body.max_users,
            metadata=body.metadata,
            created_by=str(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return row


@router.get("/api/pilot/programs")
async def list_programs(
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """列出 pilot programs."""
    if status and status not in PROGRAM_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")

    organisation_id: Optional[str] = None
    if user.role == UserRole.talent_partner:
        supabase = get_supabase_admin()
        me_resp = (
            supabase.table("users")
            .select("organisation_id")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
        organisation_id = (me_resp.data or {}).get("organisation_id")
        if not organisation_id:
            return {"data": [], "total": 0}

    rows = svc_list_programs(
        organisation_id=organisation_id, status=status, limit=limit
    )
    return {"data": rows, "total": len(rows)}


@router.get("/api/pilot/programs/{program_id}")
async def get_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    try:
        return svc_get_program(str(program_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/api/pilot/programs/{program_id}")
async def update_program(
    program_id: UUID,
    body: ProgramUpdate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """更新 program 字段."""
    supabase = get_supabase_admin()
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="no fields to update")
    # metadata 走 JSONB merge (避免覆盖其他 key)
    if "metadata" in payload:
        existing = svc_get_program(str(program_id)).get("metadata") or {}
        payload["metadata"] = {**existing, **payload["metadata"]}
    resp = (
        supabase.table("pilot_programs")
        .update(payload)
        .eq("id", str(program_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="pilot program not found")
    return rows[0]


@router.delete("/api/pilot/programs/{program_id}", status_code=204)
async def delete_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_programs")
        .delete()
        .eq("id", str(program_id))
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="pilot program not found")
    return None


@router.post("/api/pilot/programs/{program_id}/start")
async def start_program(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """recruiting -> active."""
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
    body: ProgramEndRequest,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """active -> completed, 记录最终 NPS 到 metadata."""
    try:
        row = svc_end_program(program_id=str(program_id), final_notes=body.final_notes)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return row


# ---------------------------------------------------------------------------
# 邀请 / 接受
# ---------------------------------------------------------------------------


@router.post("/api/pilot/invite", status_code=201)
async def invite_user(
    body: InviteRequest,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    try:
        invitation = await svc_invite(
            program_id=str(body.program_id),
            email=body.email,
            role=body.role,
            invited_by=str(user.id),
            ttl_days=body.ttl_days,
            send_email=body.send_email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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
    from services.integrations.pilot_invitation import accept_invitation

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
# Stats / Report
# ---------------------------------------------------------------------------


# 向后兼容 (旧测试 from api.pilot import _compute_nps)
def _compute_nps(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """兼容旧接口: 从 [{score: int}] 行计算 NPS. 委托给 ``calculate_nps``."""
    result = calculate_nps([r.get("score") for r in rows])
    return {
        "nps": result.nps,
        "promoters": result.promoters,
        "passives": result.passives,
        "detractors": result.detractors,
        "responses": result.responses,
    }


def _stats_response(stats: ProgramStats) -> dict[str, Any]:
    d = stats.to_dict()
    # 把内部 target_nps 字段融入外层 (供前端展示)
    d["targets"] = {
        "nps": stats.targets_met.get("nps", False),
        "weekly_active": stats.targets_met.get("weekly_active", False),
        "top_pain_points": stats.targets_met.get("top_pain_points", False),
        "thresholds": {
            "nps": NPS_TARGET,
            "weekly_active": WEEKLY_ACTIVE_TARGET,
            "top_pain_points_max": TOP_PAIN_POINTS_LIMIT,
        },
    }
    return d


@router.get("/api/pilot/programs/{program_id}/stats")
async def program_stats(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    """试用统计: 邀请/反馈/NPS/周活/Top 痛点."""
    try:
        stats = svc_get_stats(str(program_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _stats_response(stats)


@router.get("/api/pilot/programs/{program_id}/report")
async def program_report(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """完整 report (JSON, 含 stats + feedback samples + notes)."""
    try:
        report = svc_generate_report(str(program_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return report.to_dict()


@router.post("/api/pilot/programs/{program_id}/report/pdf")
async def program_report_pdf(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """生成月度 PDF 报告,返回文件路径 + 字节数."""
    try:
        result = generate_monthly_report(str(program_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("pilot_report_pdf failed")
        raise HTTPException(status_code=500, detail=f"report failed: {exc}")
    return {
        "path": result["path"],
        "bytes": result["bytes"],
        "format": result["format"],
        "generated_at": result["generated_at"],
    }


@router.get("/api/pilot/programs/{program_id}/report/download")
async def program_report_download(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """生成并直接返回 PDF 文件 (供下载)."""
    try:
        result = generate_monthly_report(str(program_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    media_type = "application/pdf" if result["format"] == "pdf" else "text/plain"
    filename = f"pilot_report_{program_id}.{'pdf' if result['format'] == 'pdf' else 'txt'}"
    return FileResponse(result["path"], media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# Feedback / NPS (用户主动提交)
# ---------------------------------------------------------------------------


@router.post("/api/pilot/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """用户主动提交反馈."""
    supabase = get_supabase_admin()
    payload = {
        "user_id": str(user.id),
        "category": body.category,
        "comment": body.comment,
        "feature_used": body.feature_used,
        "program_id": body.program_id,
        "score": body.score,
        "metadata": body.metadata,
    }
    resp = supabase.table("pilot_feedback").insert(payload).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")
    return rows[0]


@router.post("/api/pilot/feedback/nps", status_code=201)
async def submit_nps(
    body: NPSSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """提交 NPS 评分 (0-10)."""
    supabase = get_supabase_admin()
    payload = {
        "user_id": str(user.id),
        "category": "nps",
        "score": body.score,
        "comment": body.comment,
        "feature_used": body.feature_used,
        "program_id": body.program_id,
        "metadata": {},
    }
    resp = supabase.table("pilot_feedback").insert(payload).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")

    # 立即返回当前 NPS 概览 (单条提交也立即反馈)
    return {
        "feedback": rows[0],
        "score": body.score,
        "is_promoter": body.score >= 9,
        "is_detractor": body.score <= 6,
    }


@router.post("/api/pilot/feedback/categorize", response_model=CategorizeResponse)
async def categorize_endpoint(
    body: CategorizeRequest,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """对一段反馈文本做 LLM/启发式分类 (admin/debug 端点)."""
    result: CategorizedFeedback = await categorize_feedback(
        body.text, use_llm=body.use_llm
    )
    return CategorizeResponse(**result.to_dict())


@router.get("/api/pilot/feedback")
async def list_feedback(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
    program_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """反馈汇总 (admin)."""
    if category and category not in SUPPORTED_CATEGORIES and category != "nps":
        raise HTTPException(status_code=400, detail=f"invalid category: {category}")
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


# ---------------------------------------------------------------------------
# NPS summary (管理员快速查看)
# ---------------------------------------------------------------------------


@router.get("/api/pilot/programs/{program_id}/nps")
async def program_nps(
    program_id: UUID,
    user: CurrentUser = Depends(require_role(UserRole.admin, UserRole.talent_partner)),
):
    """拉取 program 所有 NPS 评分,实时计算 NPS (供 dashboard 轮询)."""
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_feedback")
        .select("score, created_at, feature_used, comment")
        .eq("program_id", str(program_id))
        .eq("category", "nps")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    rows = resp.data or []
    scores = [r.get("score") for r in rows]
    nps = calculate_nps(scores)
    return {
        "program_id": str(program_id),
        "nps": nps.to_dict(),
        "samples": rows[:20],
    }


__all__ = ["router"]