"""v10.0 T5002 — Resilience decorator tests (20+)."""
from __future__ import annotations

import asyncio
import time

import pytest

from services.platform.errors import ServiceError, ServiceErrorCode
from services.platform.retry import (
    Backoff,
    CircuitState,
    Backoff,
    circuit_breaker,
    constant,
    exponential,
    get_circuit,
    linear,
    reset_circuit,
    retry,
    timeout,
    with_resilience,
)


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------
def test_backoff_exponential_grows():
    b = exponential(base_delay=0.1, max_delay=10.0, jitter=0.0)
    assert b.delay_for(1) == pytest.approx(0.1, abs=1e-9)
    assert b.delay_for(2) == pytest.approx(0.2, abs=1e-9)
    assert b.delay_for(3) == pytest.approx(0.4, abs=1e-9)


def test_backoff_capped():
    b = exponential(base_delay=1.0, max_delay=5.0, jitter=0.0)
    assert b.delay_for(10) == 5.0


def test_backoff_linear():
    b = linear(base_delay=0.1, max_delay=10.0, jitter=0.0)
    assert b.delay_for(1) == pytest.approx(0.1, abs=1e-9)
    assert b.delay_for(3) == pytest.approx(0.3, abs=1e-9)


def test_backoff_constant():
    b = constant(0.2, jitter=0.0)
    assert b.delay_for(1) == 0.2
    assert b.delay_for(5) == 0.2


def test_backoff_jitter_window():
    b = exponential(base_delay=1.0, jitter=0.5)
    # attempt=2 → base * 2 = 2.0, jitter ±50% → [1.0, 3.0]
    for _ in range(20):
        d = b.delay_for(2)
        assert 1.0 <= d <= 3.0


def test_backoff_jitter_zero():
    b = exponential(base_delay=1.0, jitter=0.0)
    for n in range(1, 5):
        d = b.delay_for(n)
        assert abs(d - (1.0 * (2 ** (n - 1)))) < 1e-9


# ---------------------------------------------------------------------------
# @retry (sync)
# ---------------------------------------------------------------------------
def test_retry_sync_eventually_succeeds():
    calls = {"n": 0}

    @retry(3, sleep=lambda d: None)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("nope")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_sync_exhausted_raises_service_error():
    @retry(2, sleep=lambda d: None)
    def always():
        raise RuntimeError("nope")

    with pytest.raises(ServiceError) as exc_info:
        always()
    assert exc_info.value.code == ServiceErrorCode.RETRY_EXHAUSTED


def test_retry_does_not_retry_non_retryable_service_error():
    calls = {"n": 0}

    @retry(5, sleep=lambda d: None)
    def notretry():
        calls["n"] += 1
        raise ServiceError(ServiceErrorCode.NOT_FOUND)

    with pytest.raises(ServiceError) as exc_info:
        notretry()
    assert calls["n"] == 1
    assert exc_info.value.code == ServiceErrorCode.NOT_FOUND


def test_retry_give_up_on_short_circuits():
    calls = {"n": 0}

    @retry(5, give_up_on=(KeyError,), sleep=lambda d: None)
    def f():
        calls["n"] += 1
        raise KeyError("x")

    with pytest.raises(KeyError):
        f()
    assert calls["n"] == 1


def test_retry_retry_on_whitelist():
    calls = {"n": 0}

    @retry(3, retry_on=(ValueError,), sleep=lambda d: None)
    def f():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("v")
        raise TypeError("t")

    with pytest.raises(TypeError):
        f()
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# @retry (async)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_async_succeeds():
    calls = {"n": 0}

    @retry(3, sleep=lambda d: None)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("x")
        return "ok"

    assert await flaky() == "ok"


@pytest.mark.asyncio
async def test_retry_async_exhausted():
    @retry(2, sleep=lambda d: None)
    async def f():
        raise ValueError("x")

    with pytest.raises(ServiceError) as exc_info:
        await f()
    assert exc_info.value.code == ServiceErrorCode.RETRY_EXHAUSTED


# ---------------------------------------------------------------------------
# @circuit_breaker
# ---------------------------------------------------------------------------
def test_circuit_opens_after_threshold():
    reset_circuit()
    cb = get_circuit("t_circuit_1", failure_threshold=2, recovery_time=100)

    @circuit_breaker(failure_threshold=2, recovery_time=100, name="t_circuit_1")
    def bad():
        raise ValueError("x")

    for _ in range(2):
        with pytest.raises(ValueError):
            bad()

    # 3rd call should be short-circuited
    with pytest.raises(ServiceError) as exc_info:
        bad()
    assert exc_info.value.code == ServiceErrorCode.CIRCUIT_OPEN
    assert cb.state == CircuitState.OPEN


def test_circuit_recovery_after_window():
    reset_circuit()
    get_circuit("t_circuit_2", failure_threshold=1, recovery_time=0.05)

    @circuit_breaker(failure_threshold=1, recovery_time=0.05, name="t_circuit_2")
    def f(ok: bool):
        if not ok:
            raise ValueError("x")
        return "y"

    with pytest.raises(ValueError):
        f(False)
    # within recovery — still open
    with pytest.raises(ServiceError):
        f(True)
    time.sleep(0.06)
    # half-open allows a probe
    assert f(True) == "y"


def test_circuit_state_constants():
    assert CircuitState.CLOSED == "closed"
    assert CircuitState.OPEN == "open"
    assert CircuitState.HALF_OPEN == "half_open"


def test_reset_circuit_helper():
    reset_circuit()
    get_circuit("t_circuit_3", failure_threshold=1)
    cb = get_circuit("t_circuit_3")
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    reset_circuit("t_circuit_3")
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# @timeout
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeout_async_raises_service_error():
    @timeout(0.05)
    async def slow():
        await asyncio.sleep(1)

    with pytest.raises(ServiceError) as exc_info:
        await slow()
    assert exc_info.value.code == ServiceErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_timeout_async_passes():
    @timeout(1.0)
    async def fast():
        return 42

    assert await fast() == 42


def test_timeout_sync_raises():
    @timeout(0.05)
    def slow():
        time.sleep(0.5)
        return "no"

    with pytest.raises(ServiceError) as exc_info:
        slow()
    assert exc_info.value.code == ServiceErrorCode.TIMEOUT


# ---------------------------------------------------------------------------
# @with_resilience (composed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_with_resilience_succeeds():
    calls = {"n": 0}

    @with_resilience(max_attempts=3, backoff="exponential", timeout_s=1.0,
                     failure_threshold=5, sleep=lambda d: None)
    async def f():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ServiceError(ServiceErrorCode.UPSTREAM_UNAVAILABLE)
        return "ok"

    assert await f() == "ok"


@pytest.mark.asyncio
async def test_with_resilience_circuit_short_circuits_retries():
    calls = {"n": 0}
    reset_circuit()

    @with_resilience(max_attempts=2, failure_threshold=1,
                     recovery_time=100, name="t_wr_1", sleep=lambda d: None)
    async def bad():
        calls["n"] += 1
        raise ServiceError(ServiceErrorCode.UPSTREAM_UNAVAILABLE)

    with pytest.raises(ServiceError):
        await bad()
    # circuit is open — next call short-circuits
    with pytest.raises(ServiceError) as exc_info:
        await bad()
    assert exc_info.value.code == ServiceErrorCode.CIRCUIT_OPEN


# ---------------------------------------------------------------------------
# Name binding
# ---------------------------------------------------------------------------
def test_circuit_breaker_attaches_circuit_attribute():
    @circuit_breaker(failure_threshold=1, recovery_time=10, name="t_attr_1")
    def f():
        return 1

    assert hasattr(f, "_circuit")
    assert f._circuit.failure_threshold == 1
