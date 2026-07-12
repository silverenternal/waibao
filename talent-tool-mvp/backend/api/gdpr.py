"""GDPR / 个保法合规 API - T403 + T1004 + T1201 (consent).

端点:
- DELETE /api/gdpr/all-data    被遗忘权
- GET    /api/gdpr/export       数据可携权
- GET    /api/gdpr/privacy      隐私政策摘要
- POST   /api/gdpr/consent      记录 / 撤回同意 (T1201)
- GET    /api/gdpr/consent      查询用户同意状态 (T1201)
- GET    /api/gdpr/banner       获取 cookie banner 内容 (T1201)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from compliance.consent import (
    ConsentDecision,
    get_consent_service,
)
from services.audit import audit

logger = logging.getLogger("recruittech.api.gdpr")
router = APIRouter()


# ---------------------------------------------------------------------------
# Request models — T1201
# ---------------------------------------------------------------------------

class ConsentSubmission(BaseModel):
    """提交一条同意记录."""

    decisions: list[ConsentDecision] = Field(..., min_length=1)


class ConsentUpdate(BaseModel):
    """更新单个 category 的同意状态."""

    consent_type: str = Field(..., description="necessary/functional/analytics/marketing/cross_border")
    granted: bool


# ---------------------------------------------------------------------------
# Forgetting + Export (T403 / T1004)
# ---------------------------------------------------------------------------

@router.delete("/all-data")
@audit("forget", "gdpr", resource_id_arg="target_user_id", metadata_fn=lambda a, k, r: {"endpoint": "all-data"})
async def forget_me(user: CurrentUser = Depends(get_current_user)):
    """被遗忘权: 删除该用户所有数据."""
    supabase = get_supabase_admin()
    try:
        result = supabase.rpc("forget_user", {"target_user_id": str(user.id)}).execute()
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


# ---------------------------------------------------------------------------
# Privacy summary (T403)
# ---------------------------------------------------------------------------

@router.get("/privacy")
async def privacy_policy() -> dict[str, Any]:
    """返回隐私政策摘要."""
    return {
        "summary": "本平台严格遵守《个人信息保护法》和 GDPR,所有 PII 字段均加密存储。",
        "user_rights": [
            "访问权: GET /api/gdpr/export",
            "删除权: DELETE /api/gdpr/all-data",
            "更正权: 各类资源 PATCH 接口",
            "可携权: GET /api/gdpr/export",
            "撤回同意: POST /api/gdpr/consent/withdraw",
        ],
        "data_retention_days": 730,
        "encryption": "Fernet (AES-128-CBC + HMAC-SHA256) 字段级",
        "audit": "所有 PII 访问均记录到 audit_log 表 (admin-only 可读).",
        "policy_versions": {
            "tos": "v1.0",
            "privacy": "v1.0",
            "cookie": "v1.0",
            "dpa": "v1.0",
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Consent (T1201)
# ---------------------------------------------------------------------------

@router.post("/consent")
async def record_consent(
    body: ConsentSubmission,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """记录用户同意状态(可一次提交多个 category).

    内部会自动写入 audit_log.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    svc = get_consent_service()
    record = svc.record_consent(
        user_id=str(user.id),
        subject_id=str(user.id),
        decisions=body.decisions,
        ip=ip,
        source="web" if ua else "api",
    )
    return {
        "success": True,
        "record": svc.get_consent_status(str(user.id)),
    }


@router.post("/consent/quick")
async def record_consent_quick(
    body: ConsentUpdate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """便捷:记录单个 category 同意."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    svc = get_consent_service()
    record = svc.record_consent_simple(
        user_id=str(user.id),
        consent_type=body.consent_type,
        granted=body.granted,
        ip=ip,
        user_agent=ua,
    )
    return {
        "success": True,
        "status": svc.get_consent_status(str(user.id)),
    }


@router.post("/consent/withdraw")
async def withdraw_consent(
    body: ConsentUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """撤回某 category 的同意."""
    svc = get_consent_service()
    record = svc.withdraw_consent(
        user_id=str(user.id),
        consent_type=body.consent_type,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="no consent record to withdraw")
    return {
        "success": True,
        "status": svc.get_consent_status(str(user.id)),
    }


@router.get("/consent")
async def get_consent(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """查询当前用户全部同意状态."""
    svc = get_consent_service()
    return svc.get_consent_status(str(user.id))


@router.get("/banner")
async def get_banner(
    lang: str = "zh-CN",
) -> dict[str, Any]:
    """获取 cookie banner 内容(前端无需登录)."""
    svc = get_consent_service()
    banner = svc.build_banner(locale=lang)
    return {
        "title": banner.title,
        "description": banner.description,
        "categories": banner.categories,
        "policy_version": banner.policy_version,
        "locale": banner.locale,
        "privacy_url": banner.privacy_url,
    }