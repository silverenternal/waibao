"""T3002: Sourcing Provider 注册中心.

根据 SOURCING_PROVIDER 环境变量选择实现:
    mock    → MockSourcingProvider (默认, 无需凭证)
    github  → GitHubSourcingProvider (GITHUB_TOKEN, 匿名亦可)

github 在缺 token 触发 rate limit / 上游失败时, 由调用方回退到 mock。
"""
from __future__ import annotations

import logging
import os
from threading import Lock

from .base import SourcingProvider
from .github import GitHubSourcingProvider
from .mock import MockSourcingProvider

logger = logging.getLogger("recruittech.providers.sourcing.registry")

_provider: SourcingProvider | None = None
_lock = Lock()


def get_sourcing_provider() -> SourcingProvider:
    """根据 SOURCING_PROVIDER env 返回对应 SourcingProvider 单例。"""
    global _provider
    if _provider is not None:
        return _provider
    with _lock:
        if _provider is not None:
            return _provider
        name = (os.getenv("SOURCING_PROVIDER") or "mock").lower()
        if name == "github":
            logger.info("sourcing.provider=github")
            _provider = GitHubSourcingProvider()
        else:
            logger.info("sourcing.provider=mock")
            _provider = MockSourcingProvider()
        return _provider


def reset_sourcing_cache() -> None:
    """清空单例, 主要用于单元测试。"""
    global _provider
    with _lock:
        _provider = None
