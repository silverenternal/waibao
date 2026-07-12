"""Recommendations API — T1304 HR 主动推荐候选人.

Endpoints:
    GET  /api/recommendations/candidates/{role_id}
        对单个 role 推荐 top N 候选人(默认 20)
    POST /api/recommendations/refresh
        对所有 active role 重新跑一遍推荐(管理员触发,异步友好)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.candidate_recommender import CandidateRecommender

logger = logging.getLogger("recruittech.api.recommendations")
router = APIRouter()


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
        require_role(UserRole.talent_partner, UserRole.admin, UserRole.client)
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


__all__ = ["router"]