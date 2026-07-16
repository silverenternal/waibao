"""T1001 - OpenTelemetry 全链路追踪.

提供 init_telemetry(service_name, otlp_endpoint) 入口,挂载到 FastAPI / SQLAlchemy /
AsyncPG / Redis / HTTPX. 默认采样率 10%(可通过环境变量 OTEL_SAMPLER_ARG 调整).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("waibao.telemetry")

# 让 otel 在缺失依赖时不抛错(开发环境)
_TRACER = None  # 延迟初始化


def _build_tracer_provider(
    service_name: str,
    otlp_endpoint: Optional[str],
    sample_ratio: float,
):
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(sample_ratio),
    )
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("telemetry.otlp_exporter_configured endpoint=%s", otlp_endpoint)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telemetry.otlp_exporter_failed err=%s", exc)
    else:
        # 本地开发无 endpoint,使用 ConsoleSpanExporter 便于调试
        try:
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("telemetry.console_exporter_configured")
        except Exception:  # noqa: BLE001
            pass
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def init_telemetry(
    service_name: str = "waibao-backend",
    otlp_endpoint: Optional[str] = None,
    sample_ratio: Optional[float] = None,
) -> Optional[object]:
    """初始化 OpenTelemetry. 应在 FastAPI app 创建前调用.

    - service_name: 服务名,resource 属性
    - otlp_endpoint: OTLP gRPC endpoint (如 "http://otel-collector:4317");
                     None 表示只输出到 console
    - sample_ratio: 默认 0.1 (10%);可通过 OTEL_SAMPLER_ARG 环境变量覆盖
    """
    global _TRACER
    if sample_ratio is None:
        try:
            sample_ratio = float(os.getenv("OTEL_SAMPLER_ARG", "0.1"))
        except ValueError:
            sample_ratio = 0.1
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None
    try:
        _TRACER = _build_tracer_provider(service_name, otlp_endpoint, sample_ratio)
        logger.info(
            "telemetry.init service=%s sample_ratio=%s endpoint=%s",
            service_name,
            sample_ratio,
            otlp_endpoint or "console",
        )
        return _TRACER
    except Exception as exc:  # noqa: BLE001
        logger.warning("telemetry.init_failed err=%s", exc)
        return None


def instrument_app(app) -> None:
    """挂载 FastAPIInstrumentor + 常见客户端 instrumentation."""
    # OTel's FastAPIInstrumentor (0.63b1) walks app.routes and crashes on the
    # nested ``_IncludedRouter`` wrappers produced by FastAPI's include_router
    # (no ``.path`` on a PARTIAL match — see OTel fastapi/__init__.py). That
    # span-generation middleware then 500s every request it instruments.
    # Allow opting out (e.g. in tests / local dev) without touching prod tracing.
    import os

    if os.environ.get("WAIBAO_DISABLE_OTEL") == "1":
        logger.info("telemetry.fastapi_instrumentation_skipped (WAIBAO_DISABLE_OTEL=1)")
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("telemetry.fastapi_instrumented")
    except Exception as exc:  # noqa: BLE001
        logger.warning("telemetry.fastapi_instrumentation_failed err=%s", exc)

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
        logger.info("telemetry.sqlalchemy_instrumented")
    except Exception as exc:  # noqa: BLE001
        logger.warning("telemetry.sqlalchemy_instrumentation_failed err=%s", exc)

    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        AsyncPGInstrumentor().instrument()
        logger.info("telemetry.asyncpg_instrumented")
    except Exception as exc:  # noqa: BLE001
        logger.debug("telemetry.asyncpg_instrumentation_skipped err=%s", exc)

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("telemetry.redis_instrumented")
    except Exception as exc:  # noqa: BLE001
        logger.debug("telemetry.redis_instrumentation_skipped err=%s", exc)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.info("telemetry.httpx_instrumented")
    except Exception as exc:  # noqa: BLE001
        logger.debug("telemetry.httpx_instrumentation_skipped err=%s", exc)


def get_tracer(name: str = "waibao"):
    """获取 Tracer,用于业务代码内手动 span."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:  # noqa: BLE001
        return None


def span(name: str = "operation", **attributes):
    """上下文管理器: tracer.start_as_current_span(name, attributes=...).

    用法:
        with span("llm_call", provider="openai", model="gpt-4o"):
            ...
    """
    tracer = get_tracer()
    if tracer is None:
        from contextlib import nullcontext

        return nullcontext()

    return tracer.start_as_current_span(name, attributes=attributes or None)


def _otel_span(name: str, attributes: dict | None = None):
    """兼容调用: services/telemetry._otel_span (供 providers.base 调用).

    接受 dict attributes;返回 context manager.
    """
    return span(name, **(attributes or {}))