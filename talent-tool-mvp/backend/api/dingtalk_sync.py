"""T1204 — 钉钉同步 API 包装.

主要是把 corp_integrations 的通用端点 + 钉钉专属:
  - /api/dingtalk/sync (全量同步)
  - /api/dingtalk/approval/submit (为工单发起审批)
  - /api/dingtalk/approval/{instance_id} (查询审批结果)

真正的 DingTalkCorpClient 实例化由 services 层处理 (需要 access_token).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.corp_sync import CorpSyncService
from services.dingtalk_approval import submit_ticket_approval
from services.dingtalk_sync import DingTalkCorpClient

logger = logging.getLogger("waibao.api.dingtalk_sync")

router = APIRouter(prefix="/api/dingtalk", tags=["dingtalk"])


class SyncRequest(BaseModel):
    binding_id: str


class SyncResponse(BaseModel):
    binding_id: str
    total: int
    succeeded: int
    failed: int
    accuracy: float
    duration_ms: int


class ApprovalSubmitRequest(BaseModel):
    binding_id: str
    ticket_id: str
    approver_external_ids: list[str] = Field(default_factory=list)
    originator_user_id: str
    dept_id: str
    form_components: list[dict[str, Any]] | None = None
    process_code: str | None = None


def _binding(binding_id: str) -> dict[str, Any]:
    sb = get_supabase_admin()
    res = sb.table("corp_bindings").select("*").eq("id", binding_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "binding not found")
    return res.data


def _stub_http_for_test():
    """未配置真实 access_token 时,使用空 stub — 返回 0 用户."""
    class _Stub:
        def get(self, url, params=None):
            return {"errcode": 0, "result": {"list": [], "has_more": False, "next_cursor": 0}}

        def post(self, url, json=None):
            return {"errcode": 0, "result": {"list": [], "has_more": False, "next_cursor": 0}}

    return _Stub()


@router.post("/sync", response_model=SyncResponse)
async def sync_directory(body: SyncRequest, user: CurrentUser = Depends(get_current_user)):
    binding = _binding(body.binding_id)
    if binding["corp_type"] != "dingtalk":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "binding is not dingtalk")
    access_token = binding.get("access_token") or ""
    client = DingTalkCorpClient(_stub_http_for_test(), access_token)
    svc = CorpSyncService(body.binding_id)
    result = svc.sync_all(client)
    return SyncResponse(
        binding_id=body.binding_id,
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        accuracy=result.accuracy,
        duration_ms=result.duration_ms,
    )


@router.post("/approval/submit")
async def submit_approval(
    body: ApprovalSubmitRequest,
    user: CurrentUser = Depends(get_current_user),
):
    binding = _binding(body.binding_id)
    if binding["corp_type"] != "dingtalk":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "binding is not dingtalk")
    record = await submit_ticket_approval(
        binding_id=body.binding_id,
        ticket_id=body.ticket_id,
        approver_user_ids=body.approver_external_ids,
        originator_user_id=body.originator_user_id,
        dept_id=body.dept_id,
        form_components=body.form_components,
        process_code=body.process_code,
    )
    return {"ok": True, "approval_id": record.get("id"), "status": record.get("status")}


__all__ = ["router"]