"""GDPR / 个保法合规 API - T403 + T1004 audit."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.audit import audit

logger = logging.getLogger("recruittech.api.gdpr")
router = APIRouter()


@router.delete("/all-data")
@audit("forget", "gdpr", resource_id_arg="target_user_id", metadata_fn=lambda a, k, r: {"endpoint": "all-data"})
async def forget_me(user: CurrentUser = Depends(get_current_user)):
    """被遗忘权: 删除该用户所有数据."""
    supabase = get_supabase_admin()
    try:
        result = supabase.rpc("forget_user", {"target_user_id": str(user.id)}).execute()
        # 单独再写一条 (decorator 可能拿不到 target_user_id 显式值)
        from services.audit import record as _record

        _record(
            actor_user_id=str(user.id),
            action="forget",
            resource_type="gdpr",
            resource_id=str(user.id),
            user_id=str(user.id),
            metadata={"endpoint": "all-data", "self_service": True},
        )
        return {"success": True, "message": "所有个人数据已删除"}
    except Exception as e:
        logger.exception(f"forget_user failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
@audit("export", "gdpr", resource_id_arg="target_user_id", metadata_fn=lambda a, k, r: {"endpoint": "export"})
async def export_my_data(user: CurrentUser = Depends(get_current_user)):
    """导出我的所有数据(GDPR 数据可携权)."""
    supabase = get_supabase_admin()
    try:
        result = supabase.rpc("export_user_data", {"target_user_id": str(user.id)}).execute()
        from services.audit import record as _record

        _record(
            actor_user_id=str(user.id),
            action="export",
            resource_type="gdpr",
            resource_id=str(user.id),
            user_id=str(user.id),
            metadata={"endpoint": "export", "self_service": True},
        )
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
        "audit": "所有 PII 访问均记录到 audit_log 表 (admin-only 可读).",
    }