"""Analytics API — T1303 招聘漏斗 + 渠道 ROI.

Endpoints:
    GET /api/analytics/funnel                 漏斗汇总
    GET /api/analytics/funnel/stages          各阶段详细 (candidates / events / conversion)
    GET /api/analytics/channels               渠道归因(三种模型)
    GET /api/analytics/channels/roi           渠道 ROI 报告
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.channel_attribution import (
    ATTRIBUTION_MODELS,
    ChannelAttributionService,
)
from services.funnel_events import FUNNEL_STAGES, FunnelEventTracker
from services.recruitment_funnel import (
    RecruitmentFunnel,
    stage_conversion_rates,
)

logger = logging.getLogger("recruittech.api.analytics")
router = APIRouter()


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _get_tracker() -> FunnelEventTracker:
    sb = get_supabase_admin()
    return FunnelEventTracker(sb)


def _get_service() -> ChannelAttributionService:
    return ChannelAttributionService(_get_tracker())


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------
@router.get("/funnel", summary="招聘漏斗汇总")
async def get_funnel(
    days: int = Query(default=30, ge=1, le=365),
    org_id: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    tracker = _get_tracker()
    funnel = RecruitmentFunnel(tracker)
    return (await funnel.compute_funnel(org_id=org_id, since_days=days)).to_dict()


@router.get("/funnel/stages", summary="各阶段详细 + 转化率")
async def get_funnel_stages(
    days: int = Query(default=30, ge=1, le=365),
    org_id: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """返回分阶段数据 + 转化率,适合前端漏斗图."""
    tracker = _get_tracker()
    funnel = RecruitmentFunnel(tracker)
    result = await funnel.compute_funnel(org_id=org_id, since_days=days)
    return {
        "stages": [
            {"stage": s.stage, "count": s.candidates, "events": s.events}
            for s in result.stages
        ],
        "conversion_rates": result.conversion_rates,
        "overall_conversion": result.overall_conversion,
        "total_candidates": result.total_candidates,
        "since_days": result.since_days,
        "period_start": result.period_start,
        "period_end": result.period_end,
    }


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
@router.get("/channels", summary="渠道归因(三模型)")
async def get_channels(
    days: int = Query(default=30, ge=1, le=365),
    org_id: Optional[str] = Query(default=None),
    model: str = Query(
        default="last_touch",
        pattern=f"^({'|'.join(ATTRIBUTION_MODELS)})$",
    ),
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """单模型下渠道归因."""
    service = _get_service()
    report = await service.compute_channel_roi(
        org_id=org_id, since_days=days, models=[model]
    )
    return {
        "model": model,
        "channels": [c.to_dict() for c in report.by_model.get(model, [])],
        "best_channel": report.best_channel_by_model.get(model),
    }


@router.get("/channels/roi", summary="渠道 ROI 完整报告")
async def get_channels_roi(
    days: int = Query(default=30, ge=1, le=365),
    org_id: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """admin-only — 全模型 ROI 对比 + summary."""
    service = _get_service()
    report = await service.compute_channel_roi(org_id=org_id, since_days=days)
    return report.to_dict()


__all__ = ["router"]