"""双向匹配 API 端点."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from matching.two_way import (
    compute_two_way,
    get_top_candidates_for_role,
    get_top_matches_for_candidate,
    persist_two_way_match,
)

logger = logging.getLogger("recruittech.api.two_way_match")
router = APIRouter()


@router.post("/compute")
async def compute_match(
    candidate_id: UUID = Query(...),
    role_id: UUID = Query(...),
    user: CurrentUser = Depends(get_current_user),
):
    """计算并存储一次双向匹配."""
    supabase = get_supabase_admin()

    # 拉取数据
    cand = supabase.table("candidates").select("*").eq("id", str(candidate_id)).maybe_single().execute()
    role = supabase.table("roles").select("*").eq("id", str(role_id)).maybe_single().execute()
    if not cand.data or not role.data:
        raise HTTPException(status_code=404, detail="candidate or role not found")

    # 拉取双方 clarifications
    cand_clar = supabase.table("candidate_clarifications").select("*").eq(
        "user_id", cand.data.get("created_by", "")
    ).maybe_single().execute()
    role_clar = supabase.table("employer_clarifications").select("*").eq(
        "role_id", str(role_id)
    ).maybe_single().execute()

    # 计算
    score = await compute_two_way(
        candidate_profile=cand.data,
        role_profile=role.data,
        candidate_needs=(cand_clar.data or {}).get("must_haves", []) if cand_clar.data else {},
        role_needs=(role_clar.data or {}).get("explicit_requirements", {}) if role_clar.data else {},
    )

    # 持久化
    record = await persist_two_way_match(candidate_id, role_id, score, supabase)

    # Webhook: MATCH_PROPOSED
    try:
        from services.webhook import fire_webhook, WebhookEvent
        cand_org = (
            cand.data.get("organisation_id")
            or role.data.get("organisation_id")
            or str(user.organisation_id or "")
        )
        await fire_webhook(
            WebhookEvent.MATCH_PROPOSED,
            str(cand_org),
            {
                "candidate_id": str(candidate_id),
                "role_id": str(role_id),
                "harmonic_score": score.harmonic_score,
                "candidate_to_role": score.candidate_to_role,
                "role_to_candidate": score.role_to_candidate,
                "match_record_id": record.get("id"),
            },
        )
    except Exception as _wh_exc:  # noqa: BLE001
        import logging as _l
        _l.getLogger(__name__).warning("match.compute webhook fire failed: %r", _wh_exc)

    return {
        "candidate_to_role": round(score.candidate_to_role, 4),
        "role_to_candidate": round(score.role_to_candidate, 4),
        "harmonic_score": round(score.harmonic_score, 4),
        "candidate_perspective": score.candidate_perspective,
        "employer_perspective": score.employer_perspective,
        "record_id": record.get("id"),
    }


@router.get("/for-candidate/{candidate_id}")
async def top_matches_for_candidate(
    candidate_id: UUID,
    limit: int = Query(default=10, le=50),
    user: CurrentUser = Depends(get_current_user),
):
    """给求职者推荐岗位."""
    return await get_top_matches_for_candidate(candidate_id, limit)


@router.get("/for-role/{role_id}")
async def top_candidates_for_role(
    role_id: UUID,
    limit: int = Query(default=20, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """给 HR 推荐候选人."""
    return await get_top_candidates_for_role(role_id, limit)


@router.post("/batch")
async def batch_compute(
    candidate_id: UUID,
    top_n_roles: int = Query(default=20, le=50),
    user: CurrentUser = Depends(get_current_user),
):
    """批量计算候选人对 Top N 活跃岗位的双向匹配."""
    supabase = get_supabase_admin()
    roles = (
        supabase.table("roles")
        .select("id, title")
        .eq("status", "active")
        .limit(top_n_roles)
        .execute()
    )

    results = []
    for role in (roles.data or []):
        try:
            score = await compute_two_way({}, role, {}, {})
            results.append({
                "role_id": role["id"],
                "role_title": role.get("title"),
                "harmonic_score": score.harmonic_score,
            })
        except Exception as e:
            logger.warning(f"batch skip role {role.get('id')}: {e}")

    results.sort(key=lambda x: x["harmonic_score"], reverse=True)
    return results[:top_n_roles]