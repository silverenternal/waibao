"""Recommendations API — T1304 HR 主动推荐候选人.

Endpoints:
    GET  /api/recommendations/candidates/{role_id}
        对单个 role 推荐 top N 候选人(默认 20)
    POST /api/recommendations/refresh
        对所有 active role 重新跑一遍推荐(管理员触发,异步友好)
    POST /api/recommendations/initiate-contact   (T6304) 发起沟通 (阀值门)
    GET  /api/recommendations/channels            (T6304) 沟通渠道列表
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.candidate_recommender import CandidateRecommender
from services.marketplace.talent_market import get_service as get_market_service

logger = logging.getLogger("recruittech.api.recommendations")
router = APIRouter()


class InitiateContactBody(BaseModel):
    """Body for POST /recommendations/initiate-contact (employer only)."""

    talent_id: str
    role_id: str


_BELOW_THRESHOLD_MSG = "匹配度未达阀值(70%)，暂无法发起沟通"


def _get_recommender() -> CandidateRecommender:
    return CandidateRecommender(get_supabase_admin())


@router.get(
    "/candidates/{role_id}",
    summary="对单个 role 推荐候选人",
)
async def recommend_candidates(
    role_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.client)
    ),
):
    rec = _get_recommender()
    candidates = await rec.recommend_to_employer(role_id, limit=limit)
    return {
        "role_id": role_id,
        "count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }


@router.post("/refresh", summary="批量刷新推荐")
async def refresh_recommendations(
    role_limit: int = Query(default=50, ge=1, le=500),
    candidates_per_role: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    rec = _get_recommender()
    out = await rec.recommend_for_active_roles(
        role_limit=role_limit,
        candidates_per_role=candidates_per_role,
    )
    return {
        "role_count": len(out),
        "results": {
            rid: [c.to_dict() for c in items] for rid, items in out.items()
        },
    }


@router.post("/partner", summary="T1804 — 给单个合作方 HR 推荐候选人")
async def recommend_for_partner(
    hr_id: str = Query(..., description="HR user_id"),
    hr_name: str = Query(default="(匿名 HR)"),
    partner_id: str = Query(..., description="partner org_id"),
    role_id: str = Query(..., description="role_id to recommend against"),
    limit: int = Query(default=5, ge=1, le=20),
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """T1804 — 给合作方 HR 推荐 top 5 候选人,返回 PartnerRecommendation 列表."""
    rec = _get_recommender()
    recs = await rec.recommend_for_partner(
        hr_id=hr_id,
        hr_name=hr_name,
        partner_id=partner_id,
        role_id=role_id,
        limit=limit,
    )
    return {
        "partner_id": partner_id,
        "hr_id": hr_id,
        "count": len(recs),
        "recommendations": [r.to_dict() for r in recs],
        "stats": rec.partner_recommendation_stats(recs),
    }


@router.get("/partner/stats", summary="T1804 — 合作方推荐统计")
async def partner_recommendation_stats(
    partner_id: str | None = Query(default=None),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """T1804 — 拉取合作方推荐记录的统计 (by confidence, by hr)."""
    rec = _get_recommender()
    # 注: 直接从 supabase 拉最近 N 条
    sb = get_supabase_admin()
    rows: list = []
    try:
        q = sb.table("partner_recommendations").select("*").limit(500)
        if partner_id:
            q = q.eq("partner_id", partner_id)
        rows = q.execute().data or []
    except Exception:  # noqa: BLE001
        rows = []
    # 转对象
    from services.candidate_recommender import PartnerRecommendation as _PR
    recs: list[_PR] = []
    for r in rows:
        try:
            recs.append(
                _PR(
                    id=str(r["id"]),
                    partner_id=str(r["partner_id"]),
                    hr_id=str(r["hr_id"]),
                    hr_name=str(r.get("hr_name", "")),
                    candidate_id=str(r["candidate_id"]),
                    candidate_name=str(r.get("candidate_name", "")),
                    role_id=str(r["role_id"]),
                    role_title=str(r.get("role_title", "")),
                    overall_score=float(r.get("overall_score", 0.0)),
                    confidence=str(r.get("confidence", "moderate")),
                    reasons=list(r.get("reasons") or []),
                    created_at=str(r.get("created_at", "")),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return {
        "partner_id": partner_id,
        "stats": rec.partner_recommendation_stats(recs),
    }


# ---------------------------------------------------------------------------
# T6304 — 发起沟通 / 沟通渠道 (阀值门). Delegates to the talent-market
# service, which is the single source of truth for threshold scoring +
# communication_channels persistence.
# ---------------------------------------------------------------------------

def _employer_role_rows(user: CurrentUser) -> list[dict]:
    """Best-effort fetch of the caller's open roles (for org_id + scoring)."""
    try:
        sb = get_supabase_admin()
        res = (
            sb.table("roles")
            .select("*")
            .or_(f"owner_id.eq.{user.id},hr_id.eq.{user.id}")
            .limit(50)
            .execute()
        )
        return list(res.data or [])
    except Exception:  # noqa: BLE001 — dev fallback
        return []


@router.post("/initiate-contact", summary="T6304 — 发起沟通 (阀值门)")
async def initiate_contact(
    body: InitiateContactBody,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
):
    """发起沟通: 仅当匹配度 ≥ 阀值(70%) 才创建沟通渠道, 否则 403."""
    roles = _employer_role_rows(user)
    role = next((r for r in roles if str(r.get("id")) == str(body.role_id)), None)
    org_id = str((role or {}).get("org_id") or (role or {}).get("organisation_id") or "")
    market = get_market_service()
    try:
        channel = market.initiate_contact(
            candidate_id=body.talent_id,
            role_id=body.role_id,
            org_id=org_id,
            initiated_by="employer",
            employer_roles=roles,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail=_BELOW_THRESHOLD_MSG)
    return channel.to_dict()


@router.get("/channels", summary="T6304 — 沟通渠道列表")
async def list_channels(
    user: CurrentUser = Depends(
        require_role(UserRole.client, UserRole.talent_partner, UserRole.admin)
    ),
):
    """沟通渠道列表 — 雇主看本企业, 求职者看本人."""
    market = get_market_service()
    if user.role == UserRole.talent_partner:
        # talent: scope to their own candidate id (best-effort lookup).
        candidate_id: Optional[str] = str(user.id)
        try:
            sb = get_supabase_admin()
            res = (
                sb.table("candidates")
                .select("id")
                .eq("user_id", str(user.id))
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                candidate_id = str(rows[0].get("id"))
        except Exception:  # noqa: BLE001 — dev fallback
            pass
        channels = market.list_channels(candidate_id=candidate_id)
    else:
        roles = _employer_role_rows(user)
        org_ids = {
            str(r.get("org_id") or r.get("organisation_id") or "") for r in roles
        }
        channels = []
        for oid in org_ids:
            channels.extend(market.list_channels(org_id=oid))
    return [c.to_dict() for c in channels]


__all__ = ["router"]