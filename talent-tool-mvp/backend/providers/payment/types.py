"""Payment Provider 统一数据类型.

所有支付供应商 (Stripe / 微信支付 / 支付宝 / PayPal) 都使用这一组 dataclass,
业务层不感知具体供应商差异.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class LineItem:
    """订单单项."""

    name: str
    amount_cents: int  # 金额(分);避免浮点
    currency: str = "USD"
    quantity: int = 1
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Customer:
    """支付客户."""

    customer_id: str | None = None  # 已存在的客户 ID;None 时由 provider 创建
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CheckoutSession:
    """结账会话.

    客户端使用 url 跳转支付,内部跟踪 session_id 校验回调.
    """

    session_id: str
    url: str  # 支付页面 URL
    expires_at: datetime | None = None
    provider: str = "mock"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WebhookEvent:
    """Webhook 事件标准化结构."""

    event_id: str
    event_type: str  # checkout.session.completed / invoice.paid / ...
    provider: str
    occurred_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Subscription:
    """订阅状态."""

    subscription_id: str
    customer_id: str
    status: str  # active / trialing / past_due / canceled / unpaid / incomplete
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None
    plan_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Invoice:
    """发票/账单."""

    invoice_id: str
    customer_id: str
    amount_cents: int
    currency: str
    status: str  # draft / open / paid / void / uncollectible
    issued_at: datetime | None = None
    due_at: datetime | None = None
    paid_at: datetime | None = None
    hosted_url: str | None = None  # 在线查看发票 URL
    line_items: list[LineItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)