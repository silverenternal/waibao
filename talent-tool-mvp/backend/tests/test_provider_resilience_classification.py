"""v10.0 T5027 — Provider resilience classification tests."""
from __future__ import annotations

import asyncio

import pytest

from providers.base import (
    ResilienceClass,
    RetryPolicy,
    _default_mock_fallback,
    get_circuit,
    with_resilience,
)
from providers.exceptions import UpstreamUnavailableError


@pytest.fixture(autouse=True)
def _reset_circuits():
    # fresh circuit per test so failures don't leak across tests
    from providers import base as _base
    _base._GLOBAL_CIRCUITS.clear()
    _base._GLOBAL_BUCKETS.clear()
    yield
    _base._GLOBAL_CIRCUITS.clear()
    _base._GLOBAL_BUCKETS.clear()


def _make_always_fail(provider="test-prov"):
    @with_resilience(provider=provider, method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000)
    async def call(**kw):
        raise UpstreamUnavailableError("boom", provider=provider)

    return call


# ---------------------------------------------------------------------------
# CRITICAL — propagates
# ---------------------------------------------------------------------------
def test_critical_propagates_after_retries():
    call = _make_always_fail("crit-prov")
    call = _reapply_criticality(call, "crit-prov", ResilienceClass.CRITICAL)
    with pytest.raises(UpstreamUnavailableError):
        asyncio.run(call())


# ---------------------------------------------------------------------------
# DEGRADE — returns mock fallback, no raise
# ---------------------------------------------------------------------------
def test_degrade_returns_mock_fallback():
    call = _make_always_fail("deg-prov")
    call = _reapply_criticality(call, "deg-prov", ResilienceClass.DEGRADE)
    result = asyncio.run(call())
    assert isinstance(result, dict)
    assert result["degraded"] is True
    assert result["provider"] == "deg-prov"


def test_degrade_uses_custom_mock_fallback():
    @with_resilience(provider="deg-custom", method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000,
                     criticality=ResilienceClass.DEGRADE,
                     mock_fallback=lambda p, m: {"content": "cached", "degraded": True})
    async def call(**kw):
        raise UpstreamUnavailableError("boom", provider="deg-custom")

    result = asyncio.run(call())
    assert result["content"] == "cached"
    assert result["degraded"] is True


# ---------------------------------------------------------------------------
# OPTIONAL — silently returns mock
# ---------------------------------------------------------------------------
def test_optional_returns_mock_fallback():
    @with_resilience(provider="opt-prov", method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000,
                     criticality=ResilienceClass.OPTIONAL)
    async def call(**kw):
        raise UpstreamUnavailableError("boom", provider="opt-prov")

    result = asyncio.run(call())
    assert result["degraded"] is True


# ---------------------------------------------------------------------------
# happy path still works for all classes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cls", [ResilienceClass.CRITICAL, ResilienceClass.DEGRADE,
                                  ResilienceClass.OPTIONAL])
def test_success_path_returns_real_result(cls):
    @with_resilience(provider="ok-prov", method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000,
                     criticality=cls)
    async def call(**kw):
        return {"content": "real answer", "degraded": False}

    result = asyncio.run(call())
    assert result["content"] == "real answer"
    assert result["degraded"] is False


# ---------------------------------------------------------------------------
# circuit-open interaction with DEGRADE
# ---------------------------------------------------------------------------
def test_degrade_falls_back_when_circuit_open():
    # pre-open the circuit
    circuit = get_circuit("circ-deg")
    for _ in range(10):
        circuit.record_failure()

    @with_resilience(provider="circ-deg", method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000,
                     criticality=ResilienceClass.DEGRADE)
    async def call(**kw):
        return {"content": "should not reach"}

    result = asyncio.run(call())
    assert result["degraded"] is True


# ---------------------------------------------------------------------------
# default mock fallback shape
# ---------------------------------------------------------------------------
def test_default_mock_fallback_shape():
    fb = _default_mock_fallback("foo", "embed")
    assert fb["degraded"] is True
    assert fb["provider"] == "foo"
    assert "usage" in fb


def test_resilience_class_constants():
    assert ResilienceClass.CRITICAL == "critical"
    assert ResilienceClass.DEGRADE == "degrade"
    assert ResilienceClass.OPTIONAL == "optional"


# ---------------------------------------------------------------------------
# helper to re-apply criticality to the always-fail fixture (which was built
# with the default CRITICAL class)
# ---------------------------------------------------------------------------
def _reapply_criticality(call, provider, cls):
    @with_resilience(provider=provider, method="chat",
                     retry=RetryPolicy(max_retries=0, base_delay=0.0),
                     rate_per_sec=1000, burst=1000,
                     criticality=cls)
    async def wrapped(**kw):
        raise UpstreamUnavailableError("boom", provider=provider)

    return wrapped
