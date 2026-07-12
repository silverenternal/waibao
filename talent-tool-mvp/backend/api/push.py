"""Push API — T1804 推送引擎 + 订阅管理.

Endpoints:
    GET  /api/push/stats         实时推送统计
    POST /api/push/trigger       手动触发推送(测试用)
    POST /api/push/broadcast     全量补推(管理员)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.job_subscription import JobPosting, JobSubscriptionService
from services.push_engine import PushEngine

logger = logging.getLogger("recruittech.api.push")
router = APIRouter()


def _get_engine() -> PushEngine:
    svc = JobSubscriptionService(get_supabase_admin())
    return PushEngine(svc)


@router.get("/stats", summary="T1804 — 推送引擎实时统计")
async def push_stats(
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """返回累计 total_pushed / success / failed / by_channel / avg_latency_ms."""
    engine = _get_engine()
    return {
        "engine": "push_engine",
        "stats": engine.push_stats(),
    }


@router.post("/trigger", summary="T1804 — 手动触发实时推送(测试用)")
async def trigger_push(
    job_id: str = Query(...),
    job_title: str = Query(default="Test Role"),
    company: str = Query(default="Test Co"),
    city: str = Query(default="Shanghai"),
    salary_min: float = Query(default=30000),
    salary_max: float = Query(default=60000),
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """用 mock JobPosting 触发一次实时推送,统计返回."""
    engine = _get_engine()
    job = JobPosting(
        id=job_id,
        title=job_title,
        company=company,
        city=city,
        salary_min=salary_min,
        salary_max=salary_max,
        currency="CNY",
        skills=[],
        seniority="",
        remote_policy="",
    )
    records = await engine.realtime_match_and_push(job)
    return {
        "engine": "push_engine",
        "job_id": job_id,
        "matched_subs": len(records),
        "records": [
            {
                "subscription_id": r.subscription_id,
                "channels": r.channels,
                "success": r.success,
                "attempts": r.attempts,
                "duration_ms": r.duration_ms,
                "matches": len(r.matches),
                "error": r.error,
            }
            for r in records
        ],
        "stats_after": engine.push_stats(),
    }


@router.post("/broadcast", summary="T1804 — 全量补推(管理员)")
async def broadcast_push(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """对所有 enabled 订阅跑一次匹配并推送(冷启动 / 周期任务)。"""
    engine = _get_engine()
    records = await engine.broadcast_existing()
    return {
        "engine": "push_engine",
        "pushed": len(records),
        "stats_after": engine.push_stats(),
    }


__all__ = ["router"]
