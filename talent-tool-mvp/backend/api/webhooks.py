"""Webhook 管理 API (T802).

Endpoints:
  GET    /api/webhooks                  列表
  POST   /api/webhooks                  新建
  GET    /api/webhooks/{id}             详情
  PATCH  /api/webhooks/{id}             更新
  DELETE /api/webhooks/{id}             删除
  GET    /api/webhooks/{id}/deliveries  投递历史
  POST   /api/webhooks/{id}/test        测试发送

签名头:
  X-Webhook-Signature: sha256=<hex hmac>
  X-Webhook-Timestamp: ISO8601 UTC
  X-Webhook-Event: webhook.event.type

URL 必须 HTTPS(后端校验),失败重试 3 次后入 dead_letter.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from api.auth import get_current_user, CurrentUser
from api.deps import get_supabase_admin
from services.webhook import (
    WebhookDispatcher,
    WebhookEvent,
    WebhookPayload,
    generate_secret,
)
from services.webhook.signer import compute_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

VALID_EVENTS = {e.value for e in WebhookEvent}
MAX_ATTEMPTS = 3


class WebhookUpsert(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=8, max_length=2048)
    events: list[str] = Field(default_factory=list)
    active: bool = True
    description: str | None = None

    @field_validator("url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("webhook url 必须 https:// 开头(安全要求)")
        return v

    @field_validator("events")
    @classmethod
    def _valid_events(cls, v: list[str]) -> list[str]:
        bad = [e for e in v if e not in VALID_EVENTS]
        if bad:
            raise ValueError(f"未知事件类型: {bad}; 合法值: {sorted(VALID_EVENTS)}")
        if not v:
            raise ValueError("events 不能为空,至少订阅一个事件")
        return v


class WebhookOut(BaseModel):
    id: str
    organisation_id: str
    name: str
    url: str
    events: list[str]
    active: bool
    secret: str | None = None  # 仅在创建 / test 时返回
    description: str | None = None
    created_at: str


def _to_out(row: dict[str, Any], secret: str | None = None) -> WebhookOut:
    return WebhookOut(
        id=row["id"],
        organisation_id=row["organisation_id"],
        name=row["name"],
        url=row["url"],
        events=row.get("events") or [],
        active=row.get("active", True),
        secret=secret or row.get("secret"),
        description=row.get("description"),
        created_at=row.get("created_at")
        or datetime.now(tz=timezone.utc).isoformat(),
    )


def _org_id_for(user: CurrentUser) -> str:
    if user.organisation_id:
        return str(user.organisation_id)
    # Fallback: 拉一次 user 表
    supabase = get_supabase_admin()
    res = supabase.table("users").select("organisation_id").eq(
        "id", str(user.id)
    ).single().execute()
    org = res.data.get("organisation_id") if res.data else None
    if not org:
        org = str(uuid.uuid4())
        supabase.table("users").update({"organisation_id": org}).eq(
            "id", str(user.id)
        ).execute()
    return str(org)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[WebhookOut])
async def list_webhooks(user: CurrentUser = Depends(get_current_user)):
    org_id = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("webhooks")
        .select("*")
        .eq("organisation_id", org_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_to_out(r) for r in (res.data or [])]


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(
    body: WebhookUpsert,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    secret = generate_secret()
    record = {
        "id": str(uuid.uuid4()),
        "organisation_id": org_id,
        "name": body.name,
        "url": body.url,
        "secret": secret,
        "events": body.events,
        "active": body.active,
        "description": body.description or "",
    }
    res = get_supabase_admin().table("webhooks").insert(record).execute()
    if not res.data:
        raise HTTPException(500, "webhook 创建失败")
    return _to_out(res.data[0], secret=secret)


@router.get("/{webhook_id}", response_model=WebhookOut)
async def get_webhook(
    webhook_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("webhooks")
        .select("*")
        .eq("id", webhook_id)
        .eq("organisation_id", org_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "webhook 不存在")
    return _to_out(res.data)


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpsert,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    patch = body.model_dump(exclude_unset=True)
    res = (
        get_supabase_admin()
        .table("webhooks")
        .update(patch)
        .eq("id", webhook_id)
        .eq("organisation_id", org_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "webhook 不存在")
    return _to_out(res.data[0])


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("webhooks")
        .delete()
        .eq("id", webhook_id)
        .eq("organisation_id", org_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "webhook 不存在")
    return None


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------

class DeliveryOut(BaseModel):
    id: str
    webhook_id: str
    event_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    last_attempt_at: str | None
    response_code: int | None
    response_body: str | None
    last_error: str | None
    created_at: str


def _delivery_to_out(r: dict[str, Any]) -> DeliveryOut:
    return DeliveryOut(
        id=r["id"],
        webhook_id=r["webhook_id"],
        event_type=r["event_type"],
        payload=r.get("payload") or {},
        status=r.get("status", "pending"),
        attempts=r.get("attempts", 0),
        last_attempt_at=r.get("last_attempt_at"),
        response_code=r.get("response_code"),
        response_body=r.get("response_body"),
        last_error=r.get("last_error"),
        created_at=r.get("created_at")
        or datetime.now(tz=timezone.utc).isoformat(),
    )


@router.get("/{webhook_id}/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    webhook_id: str,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    sb = get_supabase_admin()
    own = (
        sb.table("webhooks").select("id").eq("id", webhook_id)
        .eq("organisation_id", org_id).execute()
    )
    if not own.data:
        raise HTTPException(404, "webhook 不存在")
    res = (
        sb.table("webhook_deliveries").select("*")
        .eq("webhook_id", webhook_id)
        .order("created_at", desc=True)
        .limit(min(max(limit, 1), 200))
        .execute()
    )
    return [_delivery_to_out(r) for r in (res.data or [])]


# ---------------------------------------------------------------------------
# Test send
# ---------------------------------------------------------------------------

class TestSendIn(BaseModel):
    event: str = "test.ping"
    data: dict[str, Any] = Field(default_factory=dict)


class TestSendOut(BaseModel):
    ok: bool
    status_code: int | None
    response_body: str | None
    signature: str
    timestamp: str
    delivery_id: str


@router.post("/{webhook_id}/test", response_model=TestSendOut)
async def test_send(
    webhook_id: str,
    body: TestSendIn,
    user: CurrentUser = Depends(get_current_user),
):
    org_id = _org_id_for(user)
    sb = get_supabase_admin()
    res = (
        sb.table("webhooks").select("*")
        .eq("id", webhook_id).eq("organisation_id", org_id).single().execute()
    )
    if not res.data:
        raise HTTPException(404, "webhook 不存在")
    cfg = res.data

    delivery_id = str(uuid.uuid4())
    ts = datetime.now(tz=timezone.utc).isoformat()
    payload = WebhookPayload(
        event=WebhookEvent.TICKET_CREATED
        if body.event == "test.ping"
        else WebhookEvent(body.event),
        delivery_id=delivery_id,
        tenant_id=org_id,
        occurred_at=ts,
        data={"ping": True, "echo": body.data},
    )
    body_bytes = payload.to_dict().__repr__().encode("utf-8")  # deterministic
    sig = compute_signature(cfg["secret"], body_bytes)

    # 写入 dead-letter/test 记录
    sb.table("webhook_deliveries").insert(
        {
            "id": delivery_id,
            "webhook_id": webhook_id,
            "event_type": payload.event.value,
            "payload": payload.to_dict(),
            "status": "pending",
            "attempts": 0,
        }
    ).execute()

    # 真实发送(交给 dispatcher)
    dispatcher: WebhookDispatcher
    try:
        from services.webhook import (
            get_webhook_dispatcher,
            set_webhook_dispatcher,
        )
        from services.webhook.types import WebhookConfig

        cfg_obj = WebhookConfig(
            id=cfg["id"],
            tenant_id=org_id,
            url=cfg["url"],
            secret=cfg["secret"],
            events=[WebhookEvent(e) for e in (cfg.get("events") or [])]
            or [payload.event],
        )
        dispatcher = get_webhook_dispatcher()
        dispatcher.register(cfg_obj)
        records = await dispatcher.emit(payload)
        rec = records[0] if records else None
    except Exception as exc:
        logger.warning("test_send dispatcher failed: %r", exc)
        rec = None

    # 更新 delivery 记录
    sb.table("webhook_deliveries").update(
        {
            "attempts": rec.attempt if rec else 1,
            "status": rec.status.value if rec else "failed_dead_letter",
            "response_code": rec.last_status_code if rec else None,
            "response_body": (rec.last_error or "")[:500] if rec else "dispatch-error",
            "last_attempt_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    ).eq("id", delivery_id).execute()

    return TestSendOut(
        ok=bool(rec and rec.status.value == "success"),
        status_code=rec.last_status_code if rec else None,
        response_body=(rec.last_error if rec else "no-transport")[:500],
        signature=sig,
        timestamp=ts,
        delivery_id=delivery_id,
    )


# ---------------------------------------------------------------------------
# Dead-letter replay
# ---------------------------------------------------------------------------

class ReplayOut(BaseModel):
    queued: int
    delivery_ids: list[str]


@router.post("/{webhook_id}/replay", response_model=ReplayOut)
async def replay_dead_letters(
    webhook_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """手动重发所有 dead_letter 投递."""
    org_id = _org_id_for(user)
    sb = get_supabase_admin()
    own = (
        sb.table("webhooks").select("*")
        .eq("id", webhook_id).eq("organisation_id", org_id).single().execute()
    )
    if not own.data:
        raise HTTPException(404, "webhook 不存在")
    cfg = own.data

    res = (
        sb.table("webhook_deliveries").select("*")
        .eq("webhook_id", webhook_id)
        .eq("status", "dead_letter")
        .execute()
    )
    deliveries = res.data or []
    queued: list[str] = []
    from services.webhook import get_webhook_dispatcher
    from services.webhook.types import WebhookConfig

    cfg_obj = WebhookConfig(
        id=cfg["id"],
        tenant_id=org_id,
        url=cfg["url"],
        secret=cfg["secret"],
        events=[WebhookEvent(e) for e in (cfg.get("events") or [])]
        or [WebhookEvent.TICKET_CREATED],
    )
    dispatcher = get_webhook_dispatcher()
    dispatcher.register(cfg_obj)

    for d in deliveries:
        p = d.get("payload") or {}
        ev = p.get("event")
        if not ev:
            continue
        new_payload = WebhookPayload(
            event=WebhookEvent(ev),
            delivery_id=str(uuid.uuid4()),
            tenant_id=org_id,
            occurred_at=datetime.now(tz=timezone.utc).isoformat(),
            data=p.get("data") or {},
        )
        # 重发 = 新 delivery 记录
        new_id = str(uuid.uuid4())
        sb.table("webhook_deliveries").insert(
            {
                "id": new_id,
                "webhook_id": webhook_id,
                "event_type": ev,
                "payload": new_payload.to_dict(),
                "status": "pending",
                "attempts": 0,
            }
        ).execute()
        queued.append(new_id)

        records = await dispatcher.emit(new_payload)
        rec = records[0] if records else None
        sb.table("webhook_deliveries").update(
            {
                "attempts": rec.attempt if rec else 0,
                "status": rec.status.value if rec else "failed_retrying",
                "response_code": rec.last_status_code if rec else None,
                "response_body": (rec.last_error or "")[:500] if rec else "",
                "last_attempt_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).eq("id", new_id).execute()

    return ReplayOut(queued=len(queued), delivery_ids=queued)
