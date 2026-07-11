"""Compliance API (T103 增强).

现有端点 (来自原 compliance_api.py):
    POST /upload               上传资质 → ComplianceAgent 审核
    GET  /status              组织资质状态汇总

新增端点:
    GET  /expiry-alerts       即将到期 / 已过期的资质提醒

设计要点:
    1) 复用 services.compliance_service: 不在 API 层重新拼装 risk score
    2) expiry-alerts 默认从 supabase 拉数据;无法连接时优雅降级返回空数组
    3) days_ahead 控制阈值 (默认 30 天),可由 query 参数覆盖
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.compliance")
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CredentialUpload(BaseModel):
    file_url: str
    credential_type: str = "business_license"
    hint_company_name: str = ""
    hint_credit_code: str = ""
    expiry_at: str | None = None


class ExpiryAlertItem(BaseModel):
    credential_id: str | None = None
    organisation_id: str | None = None
    company_name: str | None = None
    credential_type: str | None = None
    file_url: str | None = None
    expires_at: str | None = None
    days_to_expiry: int
    severity: str            # expired / critical / warning
    trust_score: float | None = None
    verified: bool | None = None


# ---------------------------------------------------------------------------
# Backwards-compatible /upload and /status
# ---------------------------------------------------------------------------
@router.post("/upload")
async def upload_credential(
    body: CredentialUpload,
    user: CurrentUser = Depends(get_current_user),
):
    """上传资质审核."""
    agent = registry.get_or_raise("compliance_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={
            "file_url": body.file_url,
            "credential_type": body.credential_type,
            "hint_company_name": body.hint_company_name,
            "hint_credit_code": body.hint_credit_code,
            "expiry_at": body.expiry_at,
        },
    ))
    return {"text": out.text, "verdict": out.artifacts}


@router.get("/status")
async def get_compliance_status(
    organisation_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取组织资质状态."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("company_credentials")
        .select("*")
        .eq("organisation_id", organisation_id)
        .order("created_at", desc=True)
        .execute()
    )
    creds = result.data or []
    avg_trust = sum(c.get("trust_score", 0) or 0 for c in creds) / max(1, len(creds))
    return {
        "credentials": creds,
        "total": len(creds),
        "verified_count": sum(1 for c in creds if c.get("verified")),
        "average_trust_score": round(avg_trust, 2),
    }


# ---------------------------------------------------------------------------
# New: expiry alerts
# ---------------------------------------------------------------------------
@router.get("/expiry-alerts")
async def list_expiry_alerts(
    organisation_id: str | None = Query(default=None, description="按组织过滤;不传=全局"),
    days_ahead: int = Query(default=30, ge=1, le=365, description="多少天内视为即将到期"),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """返回即将到期 (warning/critical) 或已过期 (expired) 的资质列表.

    实现:
        1) 优先调用 services.compliance_service.list_expiry_alerts
        2) 当 supabase 不可用 → 返回空 alerts 但 HTTP 200, 让前端仍能加载页面
        3) 上层应用层可基于 alerts 渲染告警卡
    """
    try:
        from services.compliance_service import list_expiry_alerts
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"compliance_service import failed: {exc}")
        raise HTTPException(status_code=500, detail="compliance service unavailable")

    try:
        supabase = get_supabase_admin()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"supabase unavailable: {exc}")
        supabase = None  # service 会内部处理

    try:
        alerts = await list_expiry_alerts(
            organisation_id=organisation_id,
            supabase=supabase,
            days_ahead=days_ahead,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"list_expiry_alerts failed: {exc}")
        alerts = []

    # 统计
    counts = {"expired": 0, "critical": 0, "warning": 0}
    for a in alerts:
        sev = a.get("severity")
        if sev in counts:
            counts[sev] += 1

    return {
        "alerts": alerts,
        "total": len(alerts),
        "counts_by_severity": counts,
        "days_ahead": days_ahead,
        "organisation_id": organisation_id,
    }


# 新增直接评估接口 — 方便前端 / 第三方调用,跳过上传流程
@router.get("/assess")
async def quick_assess(
    credit_code: str | None = Query(default=None, description="统一社会信用代码"),
    company_name: str | None = Query(default=None, description="公司名 (与 credit_code 二选一或同时)"),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """直接调 services.compliance_service.assess_company.

    不需要上传文件 — 适合前端集成编辑场景 (用户已输入公司名或信用代码)。
    """
    try:
        from services.compliance_service import assess_company
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"compliance_service import failed: {exc}")
        raise HTTPException(status_code=500, detail="compliance service unavailable")

    verdict = await assess_company(credit_code=credit_code, company_name=company_name)
    return verdict
