"""T1002 - Prometheus 指标: business + provider metrics.

暴露对象:
- provider_calls_total{provider,model,status}  Counter
- provider_call_duration_seconds{provider,model} Histogram
- tickets_created_total{priority}  Counter
- matches_computed_total{status}  Counter
- active_users  Gauge (最近 24h 日活)
- llm_cache_hit_ratio  Gauge

通过 /metrics (prometheus_client.make_asgi_app) 暴露.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("waibao.metrics")

_ENABLED = False
_REGISTRY = None
_METRICS: dict[str, object] = {}


def init_metrics() -> bool:
    """初始化全局 metrics. 缺少 prometheus_client 时返回 False."""
    global _ENABLED, _REGISTRY
    try:
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

        _REGISTRY = CollectorRegistry()
        _METRICS["provider_calls_total"] = Counter(
            "provider_calls_total",
            "Provider 调用次数",
            ["provider", "model", "status"],
            registry=_REGISTRY,
        )
        _METRICS["provider_call_duration_seconds"] = Histogram(
            "provider_call_duration_seconds",
            "Provider 调用延迟 (秒)",
            ["provider", "model"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
            registry=_REGISTRY,
        )
        _METRICS["tickets_created_total"] = Counter(
            "tickets_created_total",
            "工单创建总数",
            ["priority"],
            registry=_REGISTRY,
        )
        _METRICS["matches_computed_total"] = Counter(
            "matches_computed_total",
            "匹配计算总数",
            ["status"],
            registry=_REGISTRY,
        )
        _METRICS["active_users"] = Gauge(
            "active_users",
            "最近 24h 日活用户数",
            registry=_REGISTRY,
        )
        _METRICS["llm_cache_hit_ratio"] = Gauge(
            "llm_cache_hit_ratio",
            "LLM 缓存命中率 (0-1)",
            registry=_REGISTRY,
        )
        _ENABLED = True
        logger.info("metrics.init success")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics.init_failed err=%s", exc)
        _ENABLED = False
        return False


def is_enabled() -> bool:
    return _ENABLED


def get_registry():
    return _REGISTRY


def inc_provider_call(provider: str, model: str, status: str) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["provider_calls_total"].labels(
            provider=provider, model=model, status=status
        ).inc()
    except Exception:  # noqa: BLE001
        logger.exception("metrics.inc_provider_call_failed")


def observe_provider_call(provider: str, model: str, duration_s: float) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["provider_call_duration_seconds"].labels(
            provider=provider, model=model
        ).observe(duration_s)
    except Exception:  # noqa: BLE001
        logger.exception("metrics.observe_provider_call_failed")


def inc_ticket_created(priority: str) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["tickets_created_total"].labels(priority=priority).inc()
    except Exception:  # noqa: BLE001
        logger.exception("metrics.inc_ticket_failed")


def inc_match_computed(status: str) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["matches_computed_total"].labels(status=status).inc()
    except Exception:  # noqa: BLE001
        logger.exception("metrics.inc_match_failed")


def set_active_users(count: int) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["active_users"].set(count)
    except Exception:  # noqa: BLE001
        logger.exception("metrics.set_active_users_failed")


def set_cache_hit_ratio(ratio: float) -> None:
    if not _ENABLED:
        return
    try:
        _METRICS["llm_cache_hit_ratio"].set(max(0.0, min(1.0, ratio)))
    except Exception:  # noqa: BLE001
        logger.exception("metrics.set_cache_hit_ratio_failed")


def metrics_asgi_app():
    """返回 prometheus_client.make_asgi_app() 挂载到 /metrics."""
    if not _ENABLED:
        return None
    try:
        from prometheus_client import make_asgi_app

        return make_asgi_app(registry=_REGISTRY)
    except Exception:  # noqa: BLE001
        logger.exception("metrics.make_asgi_app_failed")
        return None


# 启动时立刻初始化
init_metrics()

# 如果环境要求关闭 metrics (例如单测),可设 METRICS_DISABLED=1
if os.getenv("METRICS_DISABLED") == "1":
    _ENABLED = False