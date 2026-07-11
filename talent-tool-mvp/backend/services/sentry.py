"""T1003 - Sentry 错误追踪.

- init_sentry(dsn, traces_sample_rate=0.1, profiles_sample_rate=0.1)
- 仅在生产启用 (ENV=production 且 SENTRY_DSN 非空)
- 关联 OTel trace_id
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("waibao.sentry")

_INITIALIZED = False


def init_sentry(
    dsn: Optional[str] = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
    environment: Optional[str] = None,
) -> bool:
    """初始化 Sentry. 返回是否真的初始化了.

    - dsn: Sentry DSN;缺省从 SENTRY_DSN 环境变量读
    - traces_sample_rate: 默认 0.1 (10%)
    - profiles_sample_rate: 默认 0.1
    - environment: 缺省从 ENVIRONMENT/APP_ENV 读
    """
    global _INITIALIZED
    if _INITIALIZED:
        return True
    env = (environment or os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    # dev / test 环境默认关闭
    if env not in {"production", "prod", "staging"}:
        logger.info("sentry.disabled reason=non_production_env env=%s", env)
        return False
    if dsn is None:
        dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("sentry.disabled reason=no_dsn env=%s", env)
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            # PII 默认关闭
            send_default_pii=False,
        )
        _INITIALIZED = True
        logger.info(
            "sentry.init env=%s traces_sample_rate=%s", env, traces_sample_rate
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentry.init_failed err=%s", exc)
        return False


def capture_exception(exc: BaseException, **extra) -> None:
    """主动上报一个异常. 若 Sentry 未初始化则 noop."""
    if not _INITIALIZED:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            # 关联 OTel trace_id (如果有)
            trace_id = _current_trace_id()
            if trace_id:
                scope.set_tag("otel_trace_id", trace_id)
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        logger.exception("sentry.capture_exception_failed")


def capture_message(message: str, level: str = "info", **extra) -> None:
    if not _INITIALIZED:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for k, v in extra.items():
                scope.set_extra(k, v)
            trace_id = _current_trace_id()
            if trace_id:
                scope.set_tag("otel_trace_id", trace_id)
            sentry_sdk.capture_message(message, level=level)
    except Exception:  # noqa: BLE001
        logger.exception("sentry.capture_message_failed")


def _current_trace_id() -> Optional[str]:
    """尝试从当前 OTel span 提取 trace_id (32 hex chars)."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return None
        ctx = span.get_span_context()
        if not ctx or not ctx.is_valid:
            return None
        return f"{ctx.trace_id:032x}"
    except Exception:  # noqa: BLE001
        return None