"""Admin API Keys 管理 (T803).

Endpoints (mothership/admin 内部使用):
  GET    /api/admin/api-keys             列表
  POST   /api/admin/api-keys             创建 (一次性返回明文)
  GET    /api/admin/api-keys/{id}        详情 (不含明文)
  PATCH  /api/admin/api-keys/{id}        更新 name/scopes/rate_limit/expires_at
  DELETE /api/admin/api-keys/{id}        撤销 (软删)
  POST   /api/admin/api-keys/{id}/revoke  同上 (显式动作)
  GET    /api/admin/api-keys/{id}/usage  用量 (按 endpoint 聚合)

明文只在 POST 创建瞬间返回一次,后续接口 (GET/PATCH) 不再返回.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.api_key import (
    generate_key,
    to_public,
    validate_scopes,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/api-keys", tags=["admin-api-keys"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApiKeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_min: int = Field(default=60, ge=1, le=10_000)
    expires_at: str | None = None  # ISO8601

    @field_validator("scopes")
    @classmethod
    def _check_scopes(cls, v: list[str]) -> list[str]:
        return validate_scopes(v)


class ApiKeyUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scopes: list[str] | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=10_000)
    expires_at: str | None = None

    @field_validator("scopes")
    @classmethod
    def _check_scopes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return validate_scopes(v)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_min: int
    expires_at: str | None
    revoked_at: str | None
    last_used_at: str | None
    created_at: str | None


class ApiKeyCreatedOut(ApiKeyOut):
    """仅在创建时返回 plaintext. 仅此一次."""

    plaintext: str


class UsageBucket(BaseModel):
    endpoint: str
    calls: int
    avg_status: float
    last_called_at: str | None


class UsageOut(BaseModel):
    api_key_id: str
    window_days: int
    total_calls: int
    success_rate: float
    per_endpoint: list[UsageBucket]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_id_for(user: CurrentUser) -> str:
    # CurrentUser 当前仅含 id/email/role;若以后扩展 organisation_id 字段优先使用.
    direct = getattr(user, "organisation_id", None)
    if direct:
        return str(direct)
    supabase = get_supabase_admin()
    res = (
        supabase.table("users")
        .select("organisation_id")
        .eq("id", str(user.id))
        .single()
        .execute()
    )
    org = res.data.get("organisation_id") if res.data else None
    if not org:
        org = str(uuid.uuid4())
        supabase.table("users").update({"organisation_id": org}).eq(
            "id", str(user.id)
        ).execute()
    return str(org)


def _to_out(row: dict[str, Any]) -> ApiKeyOut:
    d = to_public(row)
    return ApiKeyOut(**d)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("api_keys")
        .select("*")
        .eq("organisation_id", org)
        .order("created_at", desc=True)
        .execute()
    )
    return [_to_out(r) for r in (res.data or [])]


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_key(
    body: ApiKeyCreateIn,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    gen = generate_key(body.name, organisation_id=org)
    record = {
        "id": gen.id,
        "organisation_id": org,
        "name": body.name,
        "key_hash": gen.key_hash,
        "key_prefix": gen.key_prefix,
        "scopes": body.scopes,
        "rate_limit_per_min": body.rate_limit_per_min,
        "expires_at": body.expires_at,
        "created_by": str(user.id),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    res = get_supabase_admin().table("api_keys").insert(record).execute()
    if not res.data:
        raise HTTPException(500, "create_failed")
    out = _to_out(res.data[0])
    return ApiKeyCreatedOut(**out.model_dump(), plaintext=gen.plaintext)


@router.get("/{key_id}", response_model=ApiKeyOut)
async def get_key(
    key_id: str,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("api_keys")
        .select("*")
        .eq("id", key_id)
        .eq("organisation_id", org)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    return _to_out(res.data)


@router.patch("/{key_id}", response_model=ApiKeyOut)
async def update_key(
    key_id: str,
    body: ApiKeyUpdateIn,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(400, "no_fields_to_update")
    res = (
        get_supabase_admin()
        .table("api_keys")
        .update(patch)
        .eq("id", key_id)
        .eq("organisation_id", org)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    return _to_out(res.data[0])


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    now = datetime.now(tz=timezone.utc).isoformat()
    res = (
        get_supabase_admin()
        .table("api_keys")
        .update({"revoked_at": now})
        .eq("id", key_id)
        .eq("organisation_id", org)
        .is_("revoked_at", "null")
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found_or_already_revoked")
    return None


@router.post("/{key_id}/revoke", status_code=204)
async def revoke_explicit(
    key_id: str,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    return await revoke_key(key_id=key_id, user=user)


# ---------------------------------------------------------------------------
# 用量统计
# ---------------------------------------------------------------------------


@router.get("/{key_id}/usage", response_model=UsageOut)
async def get_usage(
    key_id: str,
    days: int = Query(default=7, ge=1, le=90),
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    sb = get_supabase_admin()
    own = (
        sb.table("api_keys")
        .select("id")
        .eq("id", key_id)
        .eq("organisation_id", org)
        .execute()
    )
    if not own.data:
        raise HTTPException(404, "not_found")

    # 最近 N 天窗口
    res = (
        sb.table("api_key_usage")
        .select("endpoint,status_code,occurred_at")
        .eq("api_key_id", key_id)
        .order("occurred_at", desc=True)
        .limit(10_000)
        .execute()
    )
    rows = res.data or []
    total = len(rows)
    success = sum(1 for r in rows if 200 <= int(r.get("status_code") or 0) < 400)
    success_rate = (success / total) if total else 0.0

    # 按 endpoint 聚合
    bucket: dict[str, dict[str, Any]] = {}
    for r in rows:
        ep = r.get("endpoint") or "unknown"
        b = bucket.setdefault(
            ep, {"calls": 0, "sum_status": 0, "last": None}
        )
        b["calls"] += 1
        b["sum_status"] += int(r.get("status_code") or 0)
        ts = r.get("occurred_at")
        if ts and (b["last"] is None or ts > b["last"]):
            b["last"] = ts

    per_endpoint = [
        UsageBucket(
            endpoint=ep,
            calls=b["calls"],
            avg_status=(b["sum_status"] / b["calls"]) if b["calls"] else 0.0,
            last_called_at=b["last"],
        )
        for ep, b in sorted(
            bucket.items(), key=lambda kv: kv[1]["calls"], reverse=True
        )
    ]

    return UsageOut(
        api_key_id=key_id,
        window_days=days,
        total_calls=total,
        success_rate=round(success_rate, 4),
        per_endpoint=per_endpoint,
    )
