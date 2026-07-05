"""GDPR / 个保法合规 API - T403."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.gdpr")
router = APIRouter()


@router.delete("/all-data")
async def forget_me(user: CurrentUser = Depends(get_current_user)):
    """被遗忘权: 删除该用户所有数据."""
    supabase = get_supabase_admin()
    try:
        result = supabase.rpc("forget_user", {"target_user_id": str(user.id)}).execute()
        return {"success": True, "message": "所有个人数据已删除"}
    except Exception as e:
        logger.exception(f"forget_user failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_my_data(user: CurrentUser = Depends(get_current_user)):
    """导出我的所有数据(GDPR 数据可携权)."""
    supabase = get_supabase_admin()
    try:
        result = supabase.rpc("export_user_data", {"target_user_id": str(user.id)}).execute()
        return {"data": result.data}
    except Exception as e:
        logger.exception(f"export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/privacy")
async def privacy_policy():
    """返回隐私政策摘要."""
    return {
        "summary": "本平台严格遵守《个人信息保护法》和 GDPR,所有 PII 字段均加密存储。",
        "user_rights": [
            "访问权: GET /api/gdpr/export",
            "删除权: DELETE /api/gdpr/all-data",
            "更正权: 各类资源 PATCH 接口",
            "可携权: GET /api/gdpr/export",
        ],
        "data_retention_days": 730,
        "encryption": "AES-GCM 256-bit (字段级)",
    }