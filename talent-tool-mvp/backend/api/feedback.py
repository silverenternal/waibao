"""T1106 — Feedback API.

Endpoints:
- POST /api/feedback                    用户主动反馈 (bug/feature_request/praise)
- POST /api/feedback/nps                NPS 评分 (0-10) + 可选 comment
- POST /api/feedback/quick-survey       3 题内嵌问卷
- GET  /api/feedback/me                 当前用户的反馈历史

所有 endpoint 接受已登录用户 (``get_current_user``),未登录时返回 401.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.feedback")
router = APIRouter()


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class FeedbackCreate(BaseModel):
    """主动留言类反馈 (含 bug/feature/praise)."""

    category: str = Field(..., pattern="^(bug|feature_request|praise|complaint|other)$")
    comment: str = Field(..., min_length=1, max_length=2000)
    feature_used: Optional[str] = Field(None, max_length=120)
    program_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NPSCreate(BaseModel):
    """NPS 评分 (0-10)."""

    score: int = Field(..., ge=0, le=10)
    comment: Optional[str] = Field(None, max_length=1000)
    feature_used: Optional[str] = Field(None, max_length=120)
    program_id: Optional[str] = None


class QuickSurveyCreate(BaseModel):
    """3 题快速问卷: easy_to_use / value / speed (1-5)."""

    easy_to_use: int = Field(..., ge=1, le=5)
    value: int = Field(..., ge=1, le=5)
    speed: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    feature_used: Optional[str] = Field(None, max_length=120)
    program_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """用户主动提交反馈 (留言类)."""
    supabase = get_supabase_admin()
    payload = {
        "user_id": str(user.id),
        "category": body.category,
        "comment": body.comment,
        "feature_used": body.feature_used,
        "program_id": body.program_id,
        "metadata": body.metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("pilot_feedback").insert(payload).execute()
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")
    return rows[0]


@router.post("/api/feedback/nps", status_code=201)
async def submit_nps(
    body: NPSCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """NPS 评分 (0-10). 写入 category='nps' 行,score 字段保留原始 0-10.

    经典 NPS 分桶:
      0-6  -> detractor
      7-8  -> passive
      9-10 -> promoter
    """
    if body.score < 0 or body.score > 10:
        raise HTTPException(status_code=400, detail="NPS score must be 0..10")

    if body.score >= 9:
        bucket = "promoter"
    elif body.score >= 7:
        bucket = "passive"
    else:
        bucket = "detractor"

    supabase = get_supabase_admin()
    payload = {
        "user_id": str(user.id),
        "category": "nps",
        "score": body.score,
        "comment": body.comment,
        "feature_used": body.feature_used,
        "program_id": body.program_id,
        "metadata": {"bucket": bucket},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("pilot_feedback").insert(payload).execute()
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")
    return {"id": rows[0]["id"], "score": body.score, "bucket": bucket}


@router.post("/api/feedback/quick-survey", status_code=201)
async def submit_quick_survey(
    body: QuickSurveyCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """3 题快速问卷: 写入 category='survey',score 取平均值."""
    avg = round((body.easy_to_use + body.value + body.speed) / 3, 2)
    supabase = get_supabase_admin()
    payload = {
        "user_id": str(user.id),
        "category": "survey",
        "score": int(round(avg * 2)),  # 1-5 -> 2-10 (和 NPS 数值范围对齐,便于同图展示)
        "comment": body.comment,
        "feature_used": body.feature_used,
        "program_id": body.program_id,
        "metadata": {
            "easy_to_use": body.easy_to_use,
            "value": body.value,
            "speed": body.speed,
            "average": avg,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("pilot_feedback").insert(payload).execute()
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="insert returned no rows")
    return {"id": rows[0]["id"], "average": avg}


@router.get("/api/feedback/me")
async def my_feedback(
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    """当前用户的历史反馈 (供 account/feedback-history 页面)."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("pilot_feedback")
        .select("id, category, score, comment, feature_used, created_at")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"data": result.data or [], "total": len(result.data or [])}


__all__ = ["router"]