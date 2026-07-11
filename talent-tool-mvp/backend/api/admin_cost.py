"""Cost dashboard API — T806.

Endpoints:
- GET /api/admin/cost/summary?tenant_id=&since_days=
- GET /api/admin/cost/by-provider?tenant_id=&since_days=
- GET /api/admin/cost/cache-stats
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, require_role
from contracts.shared import UserRole
from services.cost_tracker import get_cost_service
from services.llm_cache import get_stats

router = APIRouter()


@router.get("/summary")
async def get_cost_summary(
    tenant_id: Optional[str] = Query(None),
    since_days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """总成本 + per-provider/tenant/model/day 维度."""
    service = get_cost_service()
    payload = service.query_summary(tenant_id=tenant_id, since_days=since_days)
    return {"data": payload}


@router.get("/by-provider")
async def get_cost_by_provider(
    tenant_id: Optional[str] = Query(None),
    since_days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """Provider 维度聚合."""
    service = get_cost_service()
    rows = service.query_by_provider(tenant_id=tenant_id, since_days=since_days)
    return {"data": rows}


@router.get("/by-tenant")
async def get_cost_by_tenant(
    since_days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """Tenant 维度聚合 (admin 全局视图)."""
    service = get_cost_service()
    rows = service.query_by_tenant(since_days=since_days)
    return {"data": rows}


@router.get("/cache-stats")
async def get_cache_stats(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """LLM cache hit/miss + size — 来自服务进程 in-memory 计数器.

    多副本部署时建议从 Redis 聚合,此处返回当前进程视图.
    """
    return {"data": get_stats()}
