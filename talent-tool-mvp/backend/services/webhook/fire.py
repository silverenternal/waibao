"""业务事件 → Webhook 触发的统一入口 (T802).

用法:
    from services.webhook.fire import fire_webhook
    await fire_webhook(WebhookEvent.TICKET_CREATED, organisation_id, {"ticket_id": id})
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .dispatcher import get_webhook_dispatcher, set_webhook_dispatcher
from .types import (
    DeliveryRecord,
    DeliveryStatus,
    WebhookConfig,
    WebhookEvent,
    WebhookPayload,
)

logger = logging.getLogger(__name__)

# 进程内 webhook 配置同步缓存(todo: 生产应改为 watch 模式或 DB sync)
_sync_lock_set = False  # 用来幂等设置一次锁


async def fire_webhook(
    event: WebhookEvent | str,
    organisation_id: str,
    data: dict[str, Any],
) -> list[DeliveryRecord]:
    """异步 fire 一个 webhook 事件;返回本次产生的全部 DeliveryRecord.

    会同步从 Supabase webhooks 表加载该 org 的所有 active 订阅.
    """
    import asyncio
    import uuid
    from services.webhook.signer import SIGNATURE_HEADER, TIMESTAMP_HEADER, compute_signature

    if isinstance(event, str):
        try:
            event = WebhookEvent(event)
        except ValueError:
            logger.warning("fire_webhook 未知事件类型: %s", event)
            return []

    dispatcher = get_webhook_dispatcher()
    await _hydrate_configs(dispatcher, organisation_id)

    payload = WebhookPayload(
        event=event,
        delivery_id=str(uuid.uuid4()),
        tenant_id=organisation_id,
        occurred_at=datetime.now(tz=timezone.utc).isoformat(),
        data=data,
    )

    # 记录到 supabase
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        cfg_rows = (
            sb.table("webhooks")
            .select("id")
            .eq("organisation_id", organisation_id)
            .eq("active", True)
            .contains("events", [event.value])
            .execute()
        )
        rows = cfg_rows.data or []
        for r in rows:
            sb.table("webhook_deliveries").insert(
                {
                    "id": payload.delivery_id,
                    "webhook_id": r["id"],
                    "event_type": event.value,
                    "payload": payload.to_dict(),
                    "status": "pending",
                    "attempts": 0,
                }
            ).execute()
            # 因为多个 webhook 共用 delivery_id,实际生产应 UUID 化单投递.
            # 这里简化为 dispatcher 完成后追加更新.
    except Exception as exc:
        logger.warning("fire_webhook pre-log failed: %r", exc)

    records = await dispatcher.emit(payload)

    # 更新 supabase 的 delivery 状态
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        for rec in records:
            sb.table("webhook_deliveries").update(
                {
                    "attempts": rec.attempt,
                    "status": rec.status.value,
                    "response_code": rec.last_status_code,
                    "response_body": (rec.last_error or "")[:500],
                    "last_attempt_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            ).eq("id", payload.delivery_id).execute()
    except Exception as exc:
        logger.warning("fire_webhook post-log failed: %r", exc)

    return records


async def _hydrate_configs(dispatcher, organisation_id: str) -> None:
    """从 Supabase 同步订阅配置到 dispatcher.

    单线程不会因为并发 fire 触发竞争(只新增/覆盖;active=false 的 unregister).
    """
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        res = (
            sb.table("webhooks")
            .select("*")
            .eq("organisation_id", organisation_id)
            .eq("active", True)
            .execute()
        )
        # 移除旧配置(本租户)
        for cid in list(dispatcher.list_configs()):
            cfg = dispatcher._configs.get(cid)
            if cfg and cfg.tenant_id == organisation_id:
                dispatcher.unregister(cid)
        for r in res.data or []:
            try:
                cfg = WebhookConfig(
                    id=r["id"],
                    tenant_id=r["organisation_id"],
                    url=r["url"],
                    secret=r["secret"],
                    events=[WebhookEvent(e) for e in (r.get("events") or [])],
                    active=r.get("active", True),
                    description=r.get("description", ""),
                )
                dispatcher.register(cfg)
            except Exception as exc:
                logger.warning("hydrate_webhook_cfg failed: %r", exc)
    except Exception as exc:
        logger.warning("hydrate_webhook_db failed: %r", exc)
