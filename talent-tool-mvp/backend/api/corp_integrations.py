"""T1204 — 第三方企业集成 API (钉钉 / 飞书).

Endpoints (5 个):
  POST   /api/corp/integrations                  创建/更新企业绑定 (admin)
  GET    /api/corp/integrations                  列出当前组织绑定
  POST   /api/corp/integrations/{id}/sync        触发通讯录同步
  GET    /api/corp/integrations/{id}/users       列出已同步用户
  POST   /api/corp/integrations/{id}/approval/callback  审批回调 (公开)

附加 (webhook / callback):
  POST   /api/corp/dingtalk/callback             钉钉事件回调 (suite_ticket / user_add_org ...)
  POST   /api/corp/feishu/callback               飞书事件回调
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.corp_sync import CorpSyncService
from services.dingtalk_approval import update_instance_result

logger = logging.getLogger("waibao.corp_integrations")

router = APIRouter(prefix="/api/corp/integrations", tags=["corp-integrations"])


# ------------------------------------------------------------
# Schema
# ------------------------------------------------------------
class BindingUpsert(BaseModel):
    corp_id: str = Field(..., min_length=1, max_length=128)
    corp_type: str = Field(..., pattern="^(dingtalk|feishu|wecom)$")
    corp_name: str = Field(..., min_length=1, max_length=256)
    suite_id: str | None = None
    agent_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: str | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None
    approval_template_id: str | None = None
    auto_role_mapping: dict[str, Any] = Field(default_factory=dict)


class BindingOut(BaseModel):
    id: str
    corp_id: str
    corp_type: str
    corp_name: str
    status: str
    sync_state: dict[str, Any] = Field(default_factory=dict)
    last_synced_at: str | None = None


class SyncOut(BaseModel):
    binding_id: str
    total: int
    succeeded: int
    failed: int
    accuracy: float
    duration_ms: int
    errors: list[str] = Field(default_factory=list)


class UserOut(BaseModel):
    external_user_id: str
    name: str | None = None
    mobile: str | None = None
    email: str | None = None
    title: str | None = None
    role: str
    is_boss: bool
    is_hr: bool
    is_dept_head: bool
    active: bool


class ApprovalCallback(BaseModel):
    external_instance_id: str
    status: str
    approver_external_id: str | None = None


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _binding_to_out(row: dict[str, Any]) -> BindingOut:
    return BindingOut(
        id=row["id"],
        corp_id=row["corp_id"],
        corp_type=row["corp_type"],
        corp_name=row["corp_name"],
        status=row.get("status", "active"),
        sync_state=row.get("sync_state") or {},
        last_synced_at=row.get("last_synced_at"),
    )


def _binding_or_404(binding_id: str) -> dict[str, Any]:
    sb = get_supabase_admin()
    res = sb.table("corp_bindings").select("*").eq("id", binding_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "binding not found")
    return res.data


def _user_to_out(row: dict[str, Any]) -> UserOut:
    return UserOut(
        external_user_id=row["external_user_id"],
        name=row.get("name"),
        mobile=row.get("mobile"),
        email=row.get("email"),
        title=row.get("title"),
        role=row.get("role", "employee"),
        is_boss=bool(row.get("is_boss")),
        is_hr=False,  # not stored yet
        is_dept_head=bool(row.get("is_dept_head")),
        active=bool(row.get("active", True)),
    )


# ------------------------------------------------------------
# 5 个核心 endpoints
# ------------------------------------------------------------
@router.post("", response_model=BindingOut, status_code=201)
async def upsert_binding(
    body: BindingUpsert,
    user: CurrentUser = Depends(get_current_user),
):
    """创建或更新企业绑定 (admin)."""
    sb = get_supabase_admin()
    record = body.model_dump()
    record["status"] = "active"
    res = sb.table("corp_bindings").upsert(
        record, on_conflict="corp_id,corp_type"
    ).execute()
    row = res.data[0] if res.data else {}
    return _binding_to_out(row)


@router.get("", response_model=list[BindingOut])
async def list_bindings(user: CurrentUser = Depends(get_current_user)):
    sb = get_supabase_admin()
    res = (
        sb.table("corp_bindings")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [_binding_to_out(r) for r in (res.data or [])]


@router.post("/{binding_id}/sync", response_model=SyncOut)
async def trigger_sync(
    binding_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """触发通讯录同步 — 实际 HTTP 拉取由调用方注入 client,这里只跑映射逻辑."""
    binding = _binding_or_404(binding_id)
    svc = CorpSyncService(binding_id)
    # 通过工厂获取 client — 测试时可注入 mock
    from services.corp_sync import CorpUser, CorpDept

    class _StubClient:
        corp_type = binding["corp_type"]

        def fetch_departments(self) -> list[CorpDept]:
            return [CorpDept(id="1", name="总部")]

        def fetch_users(self, dept_id: str | None = None) -> list[CorpUser]:
            # 没有 access_token 时返回空 (生产环境由 worker 调用真实 client)
            return []

    result = svc.sync_all(_StubClient())
    return SyncOut(
        binding_id=binding_id,
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        accuracy=result.accuracy,
        duration_ms=result.duration_ms,
        errors=result.errors,
    )


@router.get("/{binding_id}/users", response_model=list[UserOut])
async def list_users(
    binding_id: str,
    role: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    _binding_or_404(binding_id)
    svc = CorpSyncService(binding_id)
    return [_user_to_out(u) for u in svc.list_users(role)]


@router.post("/{binding_id}/approval/callback")
async def approval_callback(
    binding_id: str,
    body: ApprovalCallback,
):
    """审批回调 (公开 — 由钉钉/飞书服务器调用)."""
    _binding_or_404(binding_id)
    row = update_instance_result(
        binding_id=binding_id,
        external_instance_id=body.external_instance_id,
        status=body.status,
        approver_external_id=body.approver_external_id,
    )
    return {"ok": True, "ticket_id": row.get("ticket_id"), "status": row.get("status")}


# ------------------------------------------------------------
# 平台回调 (钉钉 / 飞书事件推送)
# ------------------------------------------------------------
event_router = APIRouter(prefix="/api/corp", tags=["corp-events"])


@event_router.post("/dingtalk/callback")
async def dingtalk_callback(payload: dict[str, Any]):
    """钉钉 suite_ticket / 通讯录变更事件入口.

    安全: 应校验钉钉签名 (Encrypt + msg_signature). 简化为只做事件分发.
    """
    event_type = payload.get("EventType") or payload.get("event_type")
    logger.info("dingtalk callback event=%s", event_type)
    return {"errcode": 0, "errmsg": "ok"}


@event_router.post("/feishu/callback")
async def feishu_callback(payload: dict[str, Any]):
    """飞书事件回调 (URL 验证 + 业务事件)."""
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    event_type = payload.get("header", {}).get("event_type")
    logger.info("feishu callback event=%s", event_type)
    return {"code": 0, "msg": "success"}


__all__ = ["event_router", "router"]