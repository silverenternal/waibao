"""T1001 - 验证 OpenTelemetry span 被 emit.

使用 opentelemetry-sdk 内置的 InMemorySpanExporter.
"""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)


def _find_exporter(provider):
    """Walk the span processor tree to locate InMemorySpanExporter."""
    proc = getattr(provider, "_active_span_processor", None)
    if proc is None:
        return None
    # 新版 OTel: SynchronousMultiSpanProcessor -> _span_processors list
    inner = getattr(proc, "_span_processors", None)
    if inner:
        for p in inner:
            ex = getattr(p, "span_exporter", None) or getattr(p, "_exporter", None)
            if isinstance(ex, InMemorySpanExporter):
                return ex
    # 旧版
    ex = getattr(proc, "_span_exporter", None) or getattr(proc, "span_exporter", None)
    if isinstance(ex, InMemorySpanExporter):
        return ex
    return None


@pytest.fixture(autouse=True)
def _reset_tracer_provider():
    """每个测试使用独立的 InMemorySpanExporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "waibao-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # OTel SDK v1.x 起 set_tracer_provider 是 once-only,通过 _TRACER_PROVIDER_SET_ONCE 保护。
    # 重置 sentinel + 直接覆盖内部 provider,让 fixture 每次都生效。
    original_once = getattr(trace, "_TRACER_PROVIDER_SET_ONCE", None)
    original_provider = getattr(trace, "_TRACER_PROVIDER", None)
    try:
        if hasattr(trace, "_TRACER_PROVIDER_SET_ONCE"):
            trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
        trace.set_tracer_provider(provider)
    except Exception:
        # 退而求其次,直接覆盖内部 provider
        trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    yield exporter
    # 不还原 — 让下一个 fixture 接管,避免与 Once sentinel 状态打架


def _exporter():
    exp = _find_exporter(trace.get_tracer_provider())
    assert exp is not None
    exp.clear()  # 清掉上一个 test 的 span
    return exp


def test_span_is_emitted_via_helper():
    """services.telemetry.span 应该 emit 一个 span."""
    from services.telemetry import span

    exporter = _exporter()
    with span("test_op", provider="openai", model="gpt-4o"):
        pass

    spans = exporter.get_finished_spans()
    assert any(s.name == "test_op" for s in spans)


def test_span_attributes_recorded():
    """span attributes 应被正确记录."""
    from services.telemetry import span

    exporter = _exporter()
    with span("llm_call", provider="anthropic", model="claude-3"):
        pass

    spans = exporter.get_finished_spans()
    target = next(s for s in spans if s.name == "llm_call")
    assert target.attributes["provider"] == "anthropic"
    assert target.attributes["model"] == "claude-3"


@pytest.mark.asyncio
async def test_with_resilience_emits_llm_call_span():
    """with_resilience 装饰器应包裹一层 llm_call span."""
    import asyncio

    from providers.base import with_resilience

    exporter = _exporter()

    @with_resilience(provider="mock_provider", method="mock_method")
    async def fake_call(messages, model=None):
        await asyncio.sleep(0)
        return {"ok": True, "model": model}

    result = await fake_call(messages=["hi"], model="mock-1")
    assert result["ok"] is True

    spans = exporter.get_finished_spans()
    assert any(s.name == "llm_call" for s in spans)
    target = next(s for s in spans if s.name == "llm_call")
    assert target.attributes["provider"] == "mock_provider"
    assert target.attributes["method"] == "mock_method"
    assert target.attributes["model"] == "mock-1"


def test_init_telemetry_does_not_raise_in_dev(monkeypatch):
    """init_telemetry 在没装 otel exporter 时不应抛错."""
    from services.telemetry import init_telemetry

    init_telemetry(service_name="waibao-test", otlp_endpoint=None)