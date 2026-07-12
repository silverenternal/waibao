"""ATS Provider registry — 工厂模式构造 Provider.

支持:
- mock_ats (默认, 离线)
- greenhouse (T1501)
- lever (T1501)
- workday / icims (预留)
"""
from __future__ import annotations

import logging
from typing import Any

from .base import ATSProvider
from .mock import MockATSProvider

logger = logging.getLogger(__name__)


_PROVIDER_FACTORIES: dict[str, Any] = {
    "mock_ats": lambda **kw: MockATSProvider(),
}


def register(provider_name: str, factory) -> None:
    """注册自定义 Provider 工厂."""
    _PROVIDER_FACTORIES[provider_name] = factory


def _eager_register() -> None:
    """延迟导入第三方 Provider,避免未使用时被加载."""
    if "greenhouse" in _PROVIDER_FACTORIES:
        return
    try:
        from .greenhouse import GreenhouseProvider

        _PROVIDER_FACTORIES["greenhouse"] = lambda **kw: GreenhouseProvider(
            api_key=kw["api_key"],
            base_url=kw.get("base_url", "https://harvest.greenhouse.io/v1"),
            on_behalf_of=kw.get("on_behalf_of"),
            timeout=kw.get("timeout", 30.0),
        )
    except Exception:  # noqa: BLE001
        logger.warning("ats.greenhouse_register_skipped")
    try:
        from .lever import LeverProvider

        _PROVIDER_FACTORIES["lever"] = lambda **kw: LeverProvider(
            api_key=kw["api_key"],
            base_url=kw.get("base_url", "https://api.lever.co/v1"),
            timeout=kw.get("timeout", 30.0),
        )
    except Exception:  # noqa: BLE001
        logger.warning("ats.lever_register_skipped")


def build(provider_name: str, **kwargs: Any) -> ATSProvider:
    """工厂构造 Provider; 缺失时 throw KeyError."""
    _eager_register()
    if provider_name not in _PROVIDER_FACTORIES:
        raise KeyError(
            f"unknown ATS provider {provider_name!r}; "
            f"available={sorted(_PROVIDER_FACTORIES.keys())}"
        )
    return _PROVIDER_FACTORIES[provider_name](**kwargs)


def list_providers() -> list[str]:
    _eager_register()
    return sorted(_PROVIDER_FACTORIES.keys())


__all__ = ["build", "register", "list_providers"]
