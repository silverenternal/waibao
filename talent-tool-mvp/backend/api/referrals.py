"""Referrals API (T2405).

Endpoints:
    POST /api/referrals              — 员工推荐候选人
    GET  /api/referrals/me           — 我的推荐
    GET  /api/referrals/team         — HR 收件箱
    POST /api/referrals/{id}/review  — HR 审核 / 推进状态
    POST /api/referrals/{id}/reward  — 发奖
    GET  /api/referrals/leaderboard  — 排行
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.employer.referral_service import (
    DEFAULT_BONUS_CNY,
    ReferralStatus,
    get_referral_service,
)

logger = logging.getLogger("recruittech.api.referrals")
router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateReferralRequest(BaseModel):
    candidate_email: str = Field(..., description="候选人邮箱")
    candidate_name: Optional[str] = None
    candidate_phone: Optional[str] = None
    role_id: Optional[str] = None
    job_title: Optional[str] = None
    notes: Optional[str] = None


class ReviewRequest(BaseModel):
    target_status: str = Field(..., description="reviewed/interview/offered/hired/rewarded/rejected")
    hr_notes: Optional[str] = None
    reason: Optional[str] = None  # for reject


class RewardRequest(BaseModel):
    amount: float = DEFAULT_BONUS_CNY
    currency: str = "CNY"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_referral(
    body: CreateReferralRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """员工推荐候选人 (防重复)."""
    svc = get_referral_service()
    try:
        ref = svc.create_referral(
            referrer_id=user.id,
            candidate_email=body.candidate_email,
            candidate_name=body.candidate_name,
            candidate_phone=body.candidate_phone,
            role_id=body.role_id,
            job_title=body.job_title,
            notes=body.notes,
            # existing_referrals 真实场景从 DB 查询, 这里空列表 (演示)
            existing_referrals=[],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 默认 +5 积分 (提交即得)
    points = svc.award_points(user.id, ref["referrer_id"] or user.id, "submission")
    return {"referral": ref, "points_awarded": points}


@router.get("/me")
async def my_referrals(
    user: CurrentUser = Depends(get_current_user),
):
    """我的推荐 + 积分 + 排行."""
    svc = get_referral_service()
    # Demo: 真实从 DB 取
    referrals = [
        {
            "id": "ref-1",
            "candidate_email": "alice@example.com",
            "candidate_name": "Alice Wang",
            "job_title": "高级前端工程师",
            "status": "hired",
            "bonus_amount": 5000,
            "created_at": "2026-04-01T00:00:00+00:00",
        },
        {
            "id": "ref-2",
            "candidate_email": "bob@example.com",
            "job_title": "后端工程师",
            "status": "interview",
            "created_at": "2026-05-15T00:00:00+00:00",
        },
    ]
    points = [
        {"referrer_id": user.id, "points": 5, "reason": "submission", "referral_id": "ref-1"},
        {"referrer_id": user.id, "points": 20, "reason": "interview", "referral_id": "ref-1"},
        {"referrer_id": user.id, "points": 100, "reason": "hired", "referral_id": "ref-1"},
        {"referrer_id": user.id, "points": 5, "reason": "submission", "referral_id": "ref-2"},
    ]
    summary = svc.summarize_referrer(user.id, referrals, points)
    return summary


@router.get("/team")
async def hr_inbox(
    user: CurrentUser = Depends(get_current_user),
    status: Optional[str] = Query(None, description="过滤: pending/reviewed/interview/..."),
):
    """HR 收件箱: 团队收到的所有推荐."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    # Demo
    items = [
        {
            "id": "ref-1",
            "referrer_id": "emp-A",
            "referrer_name": "张三 (技术部)",
            "candidate_email": "alice@example.com",
            "candidate_name": "Alice Wang",
            "job_title": "高级前端工程师",
            "status": "pending",
            "created_at": "2026-07-01T00:00:00+00:00",
        },
        {
            "id": "ref-2",
            "referrer_id": "emp-B",
            "referrer_name": "李四 (产品部)",
            "candidate_email": "bob@example.com",
            "job_title": "后端工程师",
            "status": "reviewed",
            "created_at": "2026-06-28T00:00:00+00:00",
        },
        {
            "id": "ref-3",
            "referrer_id": "emp-C",
            "referrer_name": "王五 (设计部)",
            "candidate_email": "carol@example.com",
            "job_title": "UI 设计师",
            "status": "interview",
            "created_at": "2026-06-20T00:00:00+00:00",
        },
    ]
    if status:
        items = [i for i in items if i["status"] == status]
    return {"items": items, "count": len(items)}


@router.post("/{referral_id}/review")
async def review_referral(
    referral_id: str,
    body: ReviewRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """HR 审核: 推进状态 / 拒绝."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_referral_service()
    if body.target_status == ReferralStatus.REJECTED.value:
        if not body.reason:
            raise HTTPException(status_code=400, detail="reason required for reject")
        return svc.reject(referral_id, body.reason)
    try:
        return svc.advance_status(
            referral_id,
            current_status="pending",  # demo
            target_status=body.target_status,
            hr_notes=body.hr_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{referral_id}/reward")
async def reward_referral(
    referral_id: str,
    body: RewardRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """发奖: 现金 + 积分."""
    if user.role.value not in ("hr", "admin"):
        raise HTTPException(status_code=403, detail="admin role required")
    svc = get_referral_service()
    try:
        bonus = svc.grant_bonus("referrer-id", referral_id, body.amount, body.currency)
        # 推荐人 ID 真实从 referral 查询; demo 占位
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    advance = svc.advance_status(referral_id, "hired", "rewarded")
    return {"bonus": bonus, "transition": advance}


@router.get("/leaderboard")
async def referral_leaderboard(
    limit: int = Query(10, ge=1, le=100),
    _user: CurrentUser = Depends(get_current_user),
):
    """推荐积分排行榜 (激励)."""
    svc = get_referral_service()
    # Demo: 真实从 DB 汇总
    points = [
        {"referrer_id": "emp-A", "points": 250},
        {"referrer_id": "emp-B", "points": 180},
        {"referrer_id": "emp-C", "points": 150},
        {"referrer_id": "emp-D", "points": 100},
        {"referrer_id": "emp-E", "points": 80},
    ]
    return {"leaderboard": svc.leaderboard(points, limit=limit)}
