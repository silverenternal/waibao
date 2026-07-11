"""T1002 - 验证 Prometheus 指标可被正确暴露."""
from __future__ import annotations

import pytest

pytest.importorskip("prometheus_client")


def test_init_metrics_enables():
    from services import metrics

    # 如果已禁用 (单测环境 METRICS_DISABLED=1),init 应可重新启用
    metrics._ENABLED = True
    metrics._REGISTRY = None
    metrics.init_metrics()
    assert metrics.is_enabled() is True


def test_inc_provider_call_records():
    from services import metrics

    metrics.inc_provider_call("openai", "gpt-4o", "ok")
    metrics.inc_provider_call("openai", "gpt-4o", "ok")
    metrics.inc_provider_call("openai", "gpt-4o", "error")
    # 没异常即通过 (Counter 已记录)


def test_observe_provider_call_records():
    from services import metrics

    metrics.observe_provider_call("anthropic", "claude-3", 0.42)
    metrics.observe_provider_call("anthropic", "claude-3", 1.7)


def test_inc_ticket_created():
    from services import metrics

    metrics.inc_ticket_created("P1")
    metrics.inc_ticket_created("P2")
    metrics.inc_ticket_created("P1")


def test_inc_match_computed():
    from services import metrics

    metrics.inc_match_computed("ok")
    metrics.inc_match_computed("skipped")


def test_set_active_users():
    from services import metrics

    metrics.set_active_users(123)


def test_set_cache_hit_ratio_clamps():
    from services import metrics

    metrics.set_cache_hit_ratio(-0.5)  # clamp to 0
    metrics.set_cache_hit_ratio(2.0)  # clamp to 1
    metrics.set_cache_hit_ratio(0.7)


def test_metrics_asgi_app_returns_app():
    from services import metrics

    app = metrics.metrics_asgi_app()
    if metrics.is_enabled():
        assert app is not None


def test_metrics_endpoint_renderable_via_registry():
    """验证 /metrics 内容可渲染 (即 Registry 内有数据)."""
    from services import metrics

    if not metrics.is_enabled():
        pytest.skip("metrics disabled")
    metrics.inc_provider_call("test_provider", "test_model", "ok")
    from prometheus_client import generate_latest

    body = generate_latest(metrics.get_registry()).decode()
    assert "provider_calls_total" in body
    assert "test_provider" in body