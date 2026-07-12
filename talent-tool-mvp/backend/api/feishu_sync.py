"""T1204 — 飞书同步 API 包装."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.corp_sync import CorpSyncService
from services.feishu_sync import FeishuCorpClient

logger = logging.getLogger("waibao.api.feishu_sync")

router = APIRouter(prefix="/api/feishu", tags=["feishu"])


class SyncRequest(BaseModel):
    binding_id: str


class SyncResponse(BaseModel):
    binding_id: str
    total: int
    succeeded: int
    failed: int
    accuracy: float
    duration_ms: int


def _binding(binding_id: str) -> dict[str, str | None]:
    sb = get_supabase_admin()
    res = sb.table("corp_bindings").select("*").eq("id", binding_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "binding not found")
    return res.data


def _stub_http_for_test():
    class _Stub:
        def get(self, url, params=None, headers=None):
            return {"code": 0, "data": {"items": []}}

        def post(self, url, json=None, headers=None):
            return {"code": 0, "data": {}}

    return _Stub()


@router.post("/sync", response_model=SyncResponse)
async def sync_directory(body: SyncRequest, user: CurrentUser = Depends(get_current_user)):
    binding = _binding(body.binding_id)
    if binding["corp_type"] != "feishu":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "binding is not feishu")
    token = binding.get("access_token") or ""
    client = FeishuCorpClient(_stub_http_for_test(), token)
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


__all__ = ["router"]