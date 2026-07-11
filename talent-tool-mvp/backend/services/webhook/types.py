"""Webhook 类型定义 (T802).

事件枚举 + WebhookConfig + WebhookPayload + DeliveryRecord.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class WebhookEvent(str, enum.Enum):
    """所有可订阅的 webhook 事件.

    新增事件请遵循:
        {DOMAIN}_{ACTION_PAST_PARTICIPLE}
    """

    # ---- 工单 ----
    TICKET_CREATED = "ticket.created"
    TICKET_ASSIGNED = "ticket.assigned"
    TICKET_RESOLVED = "ticket.resolved"
    TICKET_ESCALATED = "ticket.escalated"

    # ---- 匹配 ----
    MATCH_PROPOSED = "match.proposed"
    MATCH_ACCEPTED = "match.accepted"
    MATCH_REJECTED = "match.rejected"

    # ---- 情绪/风险 ----
    EMOTION_RISK = "emotion.risk"
    EMOTION_CRISIS = "emotion.crisis"

    # ---- 政策 ----
    POLICY_LEGAL_RISK = "policy.legal_risk"

    # ---- JD ----
    JD_OVERSPEC_WARNING = "jd.overspec_warning"
    JD_BIAS_DETECTED = "jd.bias_detected"

    # ---- 协同房间 ----
    ROOM_MENTION = "room.mention"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED_RETRYING = "failed_retrying"
    FAILED_DEAD_LETTER = "failed_dead_letter"


@dataclass(slots=True)
class WebhookConfig:
    """webhook 订阅配置.

    Attributes:
        id: 配置 ID (UUID).
        tenant_id: 所属租户.
        url: 回调 URL.
        secret: HMAC 签名密钥.
        events: 订阅的事件集合.
        active: 是否启用.
        description: 备注.
        created_at: 创建时间 (UTC ISO8601).
    """

    id: str
    tenant_id: str
    url: str
    secret: str
    events: list[WebhookEvent]
    active: bool = True
    description: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    @classmethod
    def new(
        cls,
        tenant_id: str,
        url: str,
        secret: str,
        events: list[WebhookEvent] | list[str],
        *,
        description: str = "",
    ) -> "WebhookConfig":
        normalized = [
            e if isinstance(e, WebhookEvent) else WebhookEvent(e) for e in events
        ]
        return cls(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            url=url,
            secret=secret,
            events=normalized,
            description=description,
        )


@dataclass(slots=True)
class WebhookPayload:
    """实际发送的事件 payload.

    Attributes:
        event: 事件类型.
        delivery_id: 本次投递 ID (UUID),可用于幂等.
        tenant_id: 所属租户.
        occurred_at: 事件发生时间 (UTC ISO8601).
        data: 业务数据 (自由结构).
    """

    event: WebhookEvent
    delivery_id: str
    tenant_id: str
    occurred_at: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.value,
            "delivery_id": self.delivery_id,
            "tenant_id": self.tenant_id,
            "occurred_at": self.occurred_at,
            "data": self.data,
        }

    @classmethod
    def make(
        cls,
        event: WebhookEvent | str,
        tenant_id: str,
        data: dict[str, Any],
        *,
        delivery_id: str | None = None,
        occurred_at: str | None = None,
    ) -> "WebhookPayload":
        return cls(
            event=event if isinstance(event, WebhookEvent) else WebhookEvent(event),
            delivery_id=delivery_id or str(uuid.uuid4()),
            tenant_id=tenant_id,
            occurred_at=occurred_at or datetime.now(tz=timezone.utc).isoformat(),
            data=data,
        )


@dataclass(slots=True)
class DeliveryRecord:
    """一次投递的审计记录."""

    id: str
    config_id: str
    event: WebhookEvent
    url: str
    status: DeliveryStatus
    attempt: int
    last_status_code: int | None = None
    last_error: str | None = None
    first_attempt_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    last_attempt_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )