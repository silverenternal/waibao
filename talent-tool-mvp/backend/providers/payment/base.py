"""Payment Provider 抽象基类.

T1405 商业化 — 接入 Stripe / 微信支付 / 支付宝 / PayPal.
业务层只依赖 PaymentProvider 接口,通过 registry 选择具体实现.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import (
        CheckoutSession,
        Customer,
        Invoice,
        LineItem,
        Subscription,
        WebhookEvent,
    )


class PaymentProvider(ABC):
    """支付供应商抽象.

    所有方法都是 async,且应通过 base.with_resilience 装饰以获得:
    retry / circuit breaker / rate limit / cost tracker / metrics.
    """

    provider_name: str = "abstract"

    @abstractmethod
    async def create_checkout_session(
        self,
        items: list["LineItem"],
        customer: "Customer",
        success_url: str,
        cancel_url: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> "CheckoutSession":
        """创建一次性结账会话,返回 url 让用户跳转支付."""

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes | str,
        signature: str,
    ) -> "WebhookEvent":
        """验证并解析 webhook 回调.签名无效时抛 AuthError."""

    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> "Subscription":
        """查询订阅当前状态."""

    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        *,
        at_period_end: bool = True,
    ) -> None:
        """取消订阅.

        at_period_end=True 时,本期末仍可访问,之后失效;
        at_period_end=False 时,立即终止.
        """

    @abstractmethod
    async def create_invoice(
        self,
        customer: "Customer",
        items: list["LineItem"],
        *,
        due_days: int = 30,
        metadata: dict[str, str] | None = None,
    ) -> "Invoice":
        """线下开票 / 创建账单(适用于 B2B 应收)."""