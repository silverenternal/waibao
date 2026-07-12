"""T2301 — 候选人/岗位对比 API.

提供端点:
- GET /api/match/compare?ids=...&role_id=...  候选人对比
- GET /api/mothership/roles/compare?ids=...   岗位对比
- POST /api/match/compare/save               保存快照
- GET /api/match/compare/saved               列出我的快照
- GET /api/match/compare/saved/{id}          获取单个快照
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase
from contracts.shared import UserRole
from services.matching.comparison import ComparisonService

logger = logging.getLogger("recruittech.api.match_compare")

# 注意: 挂在 /api/match 命名空间下,前缀在主 app 注册时设置
match_compare_router = APIRouter(prefix="/api/match/compare", tags=["compare"])
roles_compare_router = APIRouter(
    prefix="/api/mothership/roles/compare", tags=["compare"]
)


class SaveCompareRequest(BaseModel):
    item_type: str = Field(..., pattern="^(candidate|role)$")
    item_ids: list[str]
    title: Optional[str] = None
    payload: dict


@match_compare_router.get("")
async def compare_candidates(
    ids: str = Query(..., description="逗号分隔的候选人 UUID, 2-5 个"),
    role_id: Optional[UUID] = Query(None, description="可选:对比的 role context"),
    user: CurrentUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """候选人对比: 5 维度对齐 + top-3 差异高亮."""
    raw = [s.strip() for s in ids.split(",") if s.strip()]
    if len(raw) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个候选人 ID")
    if len(raw) > 5:
        raise HTTPException(status_code=400, detail="最多 5 个候选人")

    try:
        candidate_ids = [UUID(s) for s in raw]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效 UUID: {e}")

    service = ComparisonService(supabase)
    try:
        result = await service.compare_candidates(candidate_ids, role_id=role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("compare_candidates failed")
        raise HTTPException(status_code=500, detail=str(e))

    return result.to_dict()


@match_compare_router.post("/save")
async def save_comparison(
    req: SaveCompareRequest,
    user: CurrentUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """保存对比快照."""
    if len(req.item_ids) < 2:
        raise HTTPException(status_code=400, detail="item_ids 至少 2 个")

    service = ComparisonService(supabase)
    saved = await service.save_comparison(
        user_id=user.id,
        item_type=req.item_type,
        item_ids=req.item_ids,
        payload=req.payload,
        title=req.title,
    )
    return saved


@match_compare_router.get("/saved")
async def list_saved(
    user: CurrentUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """列出当前用户的对比快照."""
    service = ComparisonService(supabase)
    items = await service.list_saved(user.id)
    return {"items": items, "count": len(items)}


@match_compare_router.get("/saved/{saved_id}")
async def get_saved(
    saved_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    service = ComparisonService(supabase)
    saved = await service.get_saved(saved_id, user.id)
    if not saved:
        raise HTTPException(status_code=404, detail="快照未找到")
    return saved


@roles_compare_router.get("")
async def compare_roles(
    ids: str = Query(..., description="逗号分隔的岗位 UUID, 2-5 个"),
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.admin)),
    supabase: Client = Depends(get_supabase),
):
    """岗位对比: 5 维度对齐 + top-3 差异高亮."""
    raw = [s.strip() for s in ids.split(",") if s.strip()]
    if len(raw) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个岗位 ID")
    if len(raw) > 5:
        raise HTTPException(status_code=400, detail="最多 5 个岗位")

    try:
        role_ids = [UUID(s) for s in raw]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效 UUID: {e}")

    service = ComparisonService(supabase)
    try:
        result = await service.compare_roles(role_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("compare_roles failed")
        raise HTTPException(status_code=500, detail=str(e))

    return result.to_dict()
