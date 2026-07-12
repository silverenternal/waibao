"""T1405 — 计费 (Billing) 业务服务.

封装 3 档定价 + 订阅生命周期 + 与 PaymentProvider 的协作.
数据库写入 Supabase (subscriptions / invoices / payment_methods / webhook_events).

生命周期:
    trial → active → past_due → canceled

业务侧只依赖 BillingService,Provider 实现细节由 services.billing 内部分发.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable

from providers.payment import (
    CheckoutSession,
    Customer,
    Invoice,
    LineItem,
    PaymentProvider,
    Subscription,
    WebhookEvent,
)
from providers.payment.registry import get_payment_provider

logger = logging.getLogger("waibao.billing")


# ---------------------------------------------------------------------------
# 定价 — 三档
# ---------------------------------------------------------------------------
class PlanTier(str, Enum):
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BillingInterval(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


@dataclass(slots=True)
class Plan:
    """产品档位定义."""

    tier: PlanTier
    name: str
    description: str
    monthly_cents: int  # CNY 分
    yearly_cents: int  # CNY 分
    currency: str = "CNY"
    features: list[str] = field(default_factory=list)
    limits: dict[str, Any] = field(default_factory=dict)
    trial_days: int = 14
    is_custom_pricing: bool = False

    def price_for(self, interval: BillingInterval) -> int:
        if self.is_custom_pricing:
            return 0
        if interval == BillingInterval.MONTHLY:
            return self.monthly_cents
        return self.yearly_cents

    def line_item(self, interval: BillingInterval) -> LineItem:
        return LineItem(
            name=f"{self.name} ({interval.value})",
            amount_cents=self.price_for(interval),
            currency=self.currency,
            quantity=1,
            description=self.description,
            metadata={"tier": self.tier.value, "interval": interval.value},
        )


# 3 档定价 (CNY)
PLANS: dict[PlanTier, Plan] = {
    PlanTier.STARTER: Plan(
        tier=PlanTier.STARTER,
        name="Starter",
        description="小型团队入门版",
        monthly_cents=29_900,  # ¥299/月
        yearly_cents=299_000,  # ¥2,990/年 (约 8.3 折)
        currency="CNY",
        trial_days=14,
        features=[
            "5 个 talent partner 席位",
            "200 候选人/月",
            "标准 AI 匹配",
            "邮件工单支持",
        ],
        limits={"seats": 5, "candidates_per_month": 200},
    ),
    PlanTier.PRO: Plan(
        tier=PlanTier.PRO,
        name="Pro",
        description="中型招聘团队推荐",
        monthly_cents=99_900,  # ¥999/月
        yearly_cents=999_000,  # ¥9,990/年
        currency="CNY",
        trial_days=14,
        features=[
            "20 个 talent partner 席位",
            "5,000 候选人/月",
            "混合语义 + 结构化匹配",
            "AI 面试 & 自动调度",
            "优先支持 (4h SLA)",
        ],
        limits={"seats": 20, "candidates_per_month": 5_000},
    ),
    PlanTier.ENTERPRISE: Plan(
        tier=PlanTier.ENTERPRISE,
        name="Enterprise",
        description="企业级定制",
        monthly_cents=0,
        yearly_cents=0,
        currency="CNY",
        trial_days=30,
        is_custom_pricing=True,
        features=[
            "无限席位",
            "无限候选人",
            "SSO/SAML + 审计日志 + DLP",
            "专属客户成功经理",
            "私有化 / 公有云专属租户",
            "SLA 99.95%",
        ],
        limits={"seats": -1, "candidates_per_month": -1},
    ),
}


def list_plans() -> list[Plan]:
    """按推荐顺序返回 3 档."""
    return [PLANS[PlanTier.STARTER], PLANS[PlanTier.PRO], PLANS[PlanTier.ENTERPRISE]]


def get_plan(tier: PlanTier | str) -> Plan:
    if isinstance(tier, str):
        tier = PlanTier(tier.lower())
    return PLANS[tier]


# ---------------------------------------------------------------------------
# 持久化 helper (Supabase)
# ---------------------------------------------------------------------------
class BillingRepo:
    """Supabase billing 表的薄封装.

    表 schema 见 supabase/migrations/024_billing.sql.
    """

    def __init__(self, supabase: Any) -> None:
        self.sb = supabase

    # ---- subscriptions ----
    def upsert_subscription(self, row: dict[str, Any]) -> dict[str, Any]:
        """按 provider+provider_subscription_id upsert,不存在则创建."""
        # 优先按 provider_subscription_id 更新,否则按 organisation 查最新一条
        existing = (
            self.sb.table("subscriptions")
            .select("*")
            .eq("organisation_id", row["organisation_id"])
            .eq("provider", row["provider"])
            .eq("provider_subscription_id", row["provider_subscription_id"])
            .execute()
        )
        if existing.data:
            sid = existing.data[0]["id"]
            self.sb.table("subscriptions").update(row).eq("id", sid).execute()
            merged = {**existing.data[0], **row, "id": sid}
            return merged
        self.sb.table("subscriptions").insert(row).execute()
        created = (
            self.sb.table("subscriptions")
            .select("*")
            .eq("organisation_id", row["organisation_id"])
            .eq("provider", row["provider"])
            .eq("provider_subscription_id", row["provider_subscription_id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return created.data[0] if created.data else row

    def list_subscriptions(self, organisation_id: str) -> list[dict[str, Any]]:
        res = (
            self.sb.table("subscriptions")
            .select("*")
            .eq("organisation_id", organisation_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    def get_subscription_by_id(self, sub_id: str) -> dict[str, Any] | None:
        res = (
            self.sb.table("subscriptions")
            .select("*")
            .eq("id", sub_id)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]

    # ---- invoices ----
    def insert_invoice(self, row: dict[str, Any]) -> dict[str, Any]:
        self.sb.table("invoices").insert(row).execute()
        res = (
            self.sb.table("invoices")
            .select("*")
            .eq("organisation_id", row["organisation_id"])
            .eq("provider_invoice_id", row["provider_invoice_id"])
            .limit(1)
            .execute()
        )
        return (res.data or [row])[0]

    def list_invoices(
        self,
        organisation_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        res = (
            self.sb.table("invoices")
            .select("*")
            .eq("organisation_id", organisation_id)
            .order("issued_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    # ---- payment_methods ----
    def upsert_payment_method(self, row: dict[str, Any]) -> dict[str, Any]:
        existing = (
            self.sb.table("payment_methods")
            .select("*")
            .eq("organisation_id", row["organisation_id"])
            .eq("provider", row["provider"])
            .eq("provider_method_id", row["provider_method_id"])
            .limit(1)
            .execute()
        )
        if existing.data:
            mid = existing.data[0]["id"]
            self.sb.table("payment_methods").update(row).eq("id", mid).execute()
            return {**existing.data[0], **row, "id": mid}
        self.sb.table("payment_methods").insert(row).execute()
        res = (
            self.sb.table("payment_methods")
            .select("*")
            .eq("organisation_id", row["organisation_id"])
            .eq("provider", row["provider"])
            .eq("provider_method_id", row["provider_method_id"])
            .limit(1)
            .execute()
        )
        return (res.data or [row])[0]

    def list_payment_methods(self, organisation_id: str) -> list[dict[str, Any]]:
        res = (
            self.sb.table("payment_methods")
            .select("*")
            .eq("organisation_id", organisation_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    # ---- webhook_events (幂等) ----
    def is_webhook_seen(self, provider: str, event_id: str) -> bool:
        res = (
            self.sb.table("webhook_events")
            .select("id")
            .eq("provider", provider)
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def mark_webhook(self, provider: str, event_id: str, event_type: str, raw: dict[str, Any]) -> None:
        self.sb.table("webhook_events").insert(
            {
                "provider": provider,
                "event_id": event_id,
                "event_type": event_type,
                "received_at": datetime.now(tz=timezone.utc).isoformat(),
                "raw": raw,
            }
        ).execute()


# ---------------------------------------------------------------------------
# Billing Service
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class CheckoutResult:
    """对外暴露的 checkout 启动结果."""

    session_id: str
    url: str
    provider: str
    expires_at: datetime | None = None
    plan: Plan | None = None
    interval: BillingInterval | None = None


class BillingService:
    """计费业务服务.

    - Pricing: list_plans / get_plan
    - Checkout: 用 PaymentProvider 创建结账 session
    - Subscription: 查询 / 取消
    - Webhook: 幂等处理来自 Provider 的回调
    """

    def __init__(
        self,
        supabase: Any,
        provider: PaymentProvider | None = None,
        *,
        tax_company_name: str | None = None,
        tax_id: str | None = None,
    ) -> None:
        self.repo = BillingRepo(supabase)
        self.provider = provider or get_payment_provider()
        # 发票抬头(可配置)
        self.tax_company_name = tax_company_name or os.getenv(
            "INVOICE_COMPANY_NAME", "Waibao Technology Co., Ltd."
        )
        self.tax_id = tax_id or os.getenv("INVOICE_TAX_ID", "")

    # ---------- Pricing ----------
    def plans(self) -> list[dict[str, Any]]:
        return [self._plan_to_dict(p) for p in list_plans()]

    def _plan_to_dict(self, p: Plan) -> dict[str, Any]:
        return {
            "tier": p.tier.value,
            "name": p.name,
            "description": p.description,
            "currency": p.currency,
            "monthly_cents": p.monthly_cents,
            "yearly_cents": p.yearly_cents,
            "trial_days": p.trial_days,
            "features": list(p.features),
            "limits": dict(p.limits),
            "is_custom_pricing": p.is_custom_pricing,
        }

    # ---------- Checkout ----------
    async def create_checkout(
        self,
        organisation_id: str,
        tier: PlanTier | str,
        interval: BillingInterval | str,
        *,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
        customer_name: str | None = None,
    ) -> CheckoutResult:
        plan = get_plan(tier)
        ivl = interval if isinstance(interval, BillingInterval) else BillingInterval(interval)
        if plan.is_custom_pricing:
            raise ValueError("Enterprise 档请走线下 sales,不支持在线 checkout")

        items = [plan.line_item(ivl)]
        customer = Customer(
            customer_id=None,
            email=customer_email,
            name=customer_name,
            metadata={"organisation_id": organisation_id},
        )
        metadata = {
            "organisation_id": organisation_id,
            "tier": plan.tier.value,
            "interval": ivl.value,
            "plan_name": plan.name,
        }
        session: CheckoutSession = await self.provider.create_checkout_session(
            items,
            customer,
            success_url,
            cancel_url,
            metadata=metadata,
        )
        return CheckoutResult(
            session_id=session.session_id,
            url=session.url,
            provider=self.provider.provider_name,
            expires_at=session.expires_at,
            plan=plan,
            interval=ivl,
        )

    # ---------- Subscription ----------
    async def get_subscription_for_org(
        self, organisation_id: str
    ) -> dict[str, Any] | None:
        rows = self.repo.list_subscriptions(organisation_id)
        return rows[0] if rows else None

    async def cancel_subscription(
        self,
        organisation_id: str,
        *,
        at_period_end: bool = True,
    ) -> dict[str, Any]:
        rows = self.repo.list_subscriptions(organisation_id)
        if not rows:
            raise ValueError("no subscription for this organisation")
        sub_row = rows[0]
        provider_sub_id = sub_row.get("provider_subscription_id")
        if provider_sub_id:
            await self.provider.cancel_subscription(
                provider_sub_id, at_period_end=at_period_end
            )
        # 立即反映到本地
        update = {
            "cancel_at_period_end": at_period_end,
            "status": SubscriptionStatus.CANCELED.value if not at_period_end else sub_row.get("status"),
            "canceled_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self.repo.sb.table("subscriptions").update(update).eq("id", sub_row["id"]).execute()
        sub_row.update(update)
        return sub_row

    # ---------- Webhook ----------
    async def handle_webhook(
        self,
        *,
        provider_name: str,
        event: WebhookEvent,
        organisation_id_resolver: Any | None = None,
    ) -> dict[str, Any]:
        """处理 Provider 回调.幂等 by (provider, event_id).

        organisation_id_resolver: 解析 (event.data) -> organisation_id,
        未配置时尝试从 data.metadata.organisation_id 读取.
        """
        if self.repo.is_webhook_seen(provider_name, event.event_id):
            logger.info(
                "billing.webhook.duplicate provider=%s event_id=%s",
                provider_name,
                event.event_id,
            )
            return {"status": "duplicate", "event_id": event.event_id}

        org_id = self._resolve_org_id(event, organisation_id_resolver)
        self.repo.mark_webhook(
            provider_name, event.event_id, event.event_type, event.raw or {}
        )

        # 订阅相关
        if event.event_type in {
            "checkout.session.completed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.deleted",
            "customer.subscription.trial_will_end",
        }:
            await self._apply_subscription_event(org_id, provider_name, event)

        # 订阅状态变更触发 webhook (T802)
        try:
            from services.webhook.fire import fire_webhook
            from services.webhook.types import WebhookEvent as T802Event

            if event.event_type == "checkout.session.completed":
                await fire_webhook(
                    T802Event.TICKET_CREATED.value,
                    org_id,
                    {
                        "domain": "billing",
                        "event": "checkout.completed",
                        "provider": provider_name,
                        "data": event.data,
                    },
                )
            elif event.event_type in {
                "customer.subscription.created",
                "customer.subscription.updated",
            }:
                await fire_webhook(
                    T802Event.MATCH_ACCEPTED.value,
                    org_id,
                    {
                        "domain": "billing",
                        "event": event.event_type,
                        "provider": provider_name,
                        "data": event.data,
                    },
                )
            elif event.event_type in {
                "invoice.paid",
                "invoice.payment_failed",
            }:
                await fire_webhook(
                    T802Event.TICKET_RESOLVED.value,
                    org_id,
                    {
                        "domain": "billing",
                        "event": event.event_type,
                        "provider": provider_name,
                        "data": event.data,
                    },
                )
        except Exception:  # noqa: BLE001
            logger.exception("billing.webhook.fire_t802_failed")

        return {
            "status": "processed",
            "event_id": event.event_id,
            "type": event.event_type,
            "organisation_id": org_id,
        }

    async def _apply_subscription_event(
        self, organisation_id: str, provider_name: str, event: WebhookEvent
    ) -> None:
        data = event.data or {}
        sub = data.get("subscription") or data.get("object") or {}
        if not sub:
            # checkout.session.completed: subscription 通常在 data 里
            sub = data.get("object") or {}
        if not isinstance(sub, dict):
            return
        provider_sub_id = sub.get("id") or sub.get("subscription_id") or data.get("subscription_id")
        if not provider_sub_id:
            logger.info(
                "billing.webhook.no_subscription_id event=%s data_keys=%s",
                event.event_type,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return
        tier = (sub.get("metadata") or {}).get("tier") or data.get("tier") or PlanTier.STARTER.value
        interval = (sub.get("metadata") or {}).get("interval") or data.get("interval") or BillingInterval.MONTHLY.value
        status = self._map_status(sub.get("status") or "active")
        plan = get_plan(tier)
        period_start = sub.get("current_period_start")
        period_end = sub.get("current_period_end")
        row = {
            "organisation_id": organisation_id,
            "provider": provider_name,
            "provider_subscription_id": str(provider_sub_id),
            "plan_tier": tier,
            "plan_name": plan.name,
            "interval": interval,
            "status": status,
            "current_period_start": self._iso(period_start),
            "current_period_end": self._iso(period_end),
            "cancel_at_period_end": bool(sub.get("cancel_at_period_end", False)),
            "canceled_at": self._iso(sub.get("canceled_at")),
            "trial_end": self._iso(sub.get("trial_end")),
            "metadata": sub.get("metadata") or {},
        }
        self.repo.upsert_subscription(row)

        # 发票同步
        if event.event_type == "invoice.paid":
            invoice_obj = sub  # 在我们简化的结构里,sub 字段其实是 invoice
            inv = self._invoice_from_payload(invoice_obj, organisation_id, provider_name, tier)
            if inv:
                self.repo.insert_invoice(inv)

    def _invoice_from_payload(
        self,
        payload: dict[str, Any],
        organisation_id: str,
        provider_name: str,
        tier: str,
    ) -> dict[str, Any] | None:
        inv_id = payload.get("id") or payload.get("invoice_id")
        if not inv_id:
            return None
        amount = int(payload.get("amount_paid") or payload.get("amount_due") or 0)
        currency = (payload.get("currency") or "cny").upper()
        return {
            "organisation_id": organisation_id,
            "provider": provider_name,
            "provider_invoice_id": str(inv_id),
            "amount_cents": amount,
            "currency": currency,
            "status": (payload.get("status") or "paid"),
            "issued_at": self._iso(payload.get("created")) or datetime.now(tz=timezone.utc).isoformat(),
            "due_at": self._iso(payload.get("due_date")),
            "paid_at": self._iso(payload.get("paid_at")) or datetime.now(tz=timezone.utc).isoformat(),
            "hosted_url": payload.get("hosted_invoice_url") or payload.get("url"),
            "plan_tier": tier,
            "pdf_url": payload.get("invoice_pdf"),
            "metadata": {
                "company_name": self.tax_company_name,
                "tax_id": self.tax_id,
                "raw": payload,
            },
        }

    def _resolve_org_id(self, event: WebhookEvent, resolver: Any | None) -> str:
        if resolver is not None:
            try:
                v = resolver(event.data or {})
                if v:
                    return str(v)
            except Exception:  # noqa: BLE001
                logger.exception("billing.webhook.org_resolver_failed")
        # fallback: metadata.organisation_id
        md = (event.data or {}).get("metadata") or {}
        if isinstance(md, dict) and md.get("organisation_id"):
            return str(md["organisation_id"])
        # 兜底: 写到 webhook_events,允许重放
        return f"unresolved-{event.event_id}"

    @staticmethod
    def _map_status(raw: str) -> str:
        raw = (raw or "").lower()
        if raw in {"trialing", "trial"}:
            return SubscriptionStatus.TRIAL.value
        if raw in {"past_due", "unpaid", "incomplete", "failed"}:
            return SubscriptionStatus.PAST_DUE.value
        if raw in {"canceled", "cancelled", "terminated"}:
            return SubscriptionStatus.CANCELED.value
        return SubscriptionStatus.ACTIVE.value

    @staticmethod
    def _iso(value: Any) -> str | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        if isinstance(value, str):
            try:
                # 数字字符串 → 时间戳
                return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            except ValueError:
                pass
            return value
        return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def format_cny(cents: int) -> str:
    """¥299.00 风格展示."""
    if cents <= 0:
        return "定制"
    return f"¥{cents / 100:.2f}"


__all__ = [
    "BillingService",
    "BillingRepo",
    "BillingInterval",
    "CheckoutResult",
    "Plan",
    "PlanTier",
    "SubscriptionStatus",
    "format_cny",
    "get_plan",
    "list_plans",
]