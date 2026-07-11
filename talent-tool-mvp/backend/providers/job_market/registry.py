"""JobMarket Provider 注册中心 (T607).

根据 `JOB_MARKET_PROVIDER` 环境变量选择具体实现:
    - mock     → MockJobMarketProvider  (默认,无需凭证)
    - boss     → BossZhipinProvider     (JOB_MARKET_BOSS_APP_KEY)
    - lagou    → LagouProvider          (OAUTH_CLIENT_ID/SECRET)
    - linkedin → LinkedInProvider       (LINKEDIN_CLIENT_ID/SECRET)
    - adzuna   → AdzunaProvider         (ADZUNA_APP_ID/KEY)

所有真实 provider 在缺失凭证 / 上游失败时都会自动 fallback 到 mock.
"""
from __future__ import annotations

import logging
import os
from threading import Lock

from ..exceptions import InvalidRequestError

logger = logging.getLogger(__name__)

_job_market: object | None = None
_lock = Lock()


def get_job_market_provider() -> object:
    """根据 JOB_MARKET_PROVIDER env 返回对应 JobMarketProvider 实例."""
    global _job_market
    if _job_market is not None:
        return _job_market
    with _lock:
        if _job_market is not None:
            return _job_market
        name = (os.getenv("JOB_MARKET_PROVIDER") or "mock").lower()
        provider = _build_provider(name)
        _job_market = provider
        return _job_market


def _build_provider(name: str) -> object:
    if name == "mock":
        from .mock import MockJobMarketProvider

        logger.info("job_market.provider=mock")
        return MockJobMarketProvider()

    # 真实 provider 工厂 — 任何导入失败都返回 mock (永不阻塞业务)
    try:
        if name == "boss":
            from .boss_zhipin import BossZhipinProvider
            logger.info("job_market.provider=boss")
            return BossZhipinProvider()
        if name == "lagou":
            from .lagou import LagouProvider
            logger.info("job_market.provider=lagou")
            return LagouProvider()
        if name == "linkedin":
            from .linkedin import LinkedInProvider
            logger.info("job_market.provider=linkedin")
            return LinkedInProvider()
        if name == "adzuna":
            from .adzuna import AdzunaProvider
            logger.info("job_market.provider=adzuna")
            return AdzunaProvider()
    except Exception as exc:  # pragma: no cover - 防御性
        logger.exception("job_market.provider=%s init failed → mock", exc)
        from .mock import MockJobMarketProvider
        return MockJobMarketProvider()

    raise InvalidRequestError(
        f"unknown JOB_MARKET_PROVIDER={name}",
        details={"supported": ["mock", "boss", "lagou", "linkedin", "adzuna"]},
    )


def reset_job_market_cache() -> None:
    """清空单例,主要用于单元测试."""
    global _job_market
    with _lock:
        _job_market = None