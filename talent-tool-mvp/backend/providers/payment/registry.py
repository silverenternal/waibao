"""Payment Provider 注册中心.

环境变量: PAYMENT_PROVIDER=mock | stripe | wechat | alipay
未启用真实供应商时,fallback 到 MockPaymentProvider (CI / 本地).
"""
from __future__ import annotations

import os
from threading import Lock

from ..exceptions import InvalidRequestError

_lock = Lock()
_instance = None


def _build_provider(name: str):
    name = name.lower()
    if name == "mock":
        from .mock import MockPaymentProvider

        return MockPaymentProvider()
    # 真实供应商后续 T1405 任务实现,目前 fallback mock 并记日志
    import logging

    logging.getLogger(__name__).warning(
        "payment provider %s not yet implemented, fallback to mock", name,
    )
    from .mock import MockPaymentProvider

    return MockPaymentProvider()


def get_payment_provider():
    """懒加载单例 PaymentProvider.

    PAYMENT_PROVIDER 默认 mock.
    """
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        name = (os.getenv("PAYMENT_PROVIDER") or "mock").lower()
        if name not in {"mock", "stripe", "wechat", "alipay"}:
            raise InvalidRequestError(
                f"unknown PAYMENT_PROVIDER={name}",
                details={"supported": ["mock", "stripe", "wechat", "alipay"]},
            )
        _instance = _build_provider(name)
    return _instance


def reset_cache() -> None:
    """测试用:清空单例."""
    global _instance
    with _lock:
        _instance = None