"""base.py 共享中间件单测.

覆盖目标:
    - RetryPolicy 指数退避 + jitter 范围
    - CircuitBreaker: closed/open/half_open 状态机
    - TokenBucket: 突发 + 限流
    - CostTracker: 超 BudgetExceeded
    - with_resilience: 重试 / 熔断打开 / ProviderError retryable 决定
"""
from __future__ import annotations

import asyncio
import time

import pytest

from backend.providers import exceptions
from backend.providers.base import (
    CircuitBreaker,
    CircuitState,
    CostTracker,
    ProviderMetrics,
    RetryPolicy,
    TokenBucket,
    get_circuit,
    get_metrics,
    with_resilience,
)


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------
def test_retry_policy_delay_grows_exponentially():
    p = RetryPolicy(max_retries=4, base_delay=1.0, max_delay=30.0, jitter=0.0)
    d1 = p.delay_for(1)
    d2 = p.delay_for(2)
    d3 = p.delay_for(3)
    assert d1 == 1.0
    assert d2 == 2.0
    assert d3 == 4.0


def test_retry_policy_respects_max_delay():
    p = RetryPolicy(max_retries=10, base_delay=1.0, max_delay=5.0, jitter=0.0)
    assert p.delay_for(20) == 5.0


def test_retry_policy_jitter_in_range():
    p = RetryPolicy(max_retries=3, base_delay=1.0, max_delay=30.0, jitter=0.5)
    for n in range(1, 4):
        d = p.delay_for(n)
        base = min(1.0 * (2 ** (n - 1)), 30.0)
        assert base * 0.5 <= d <= base * 1.5


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------
def test_circuit_breaker_starts_closed_and_allows():
    cb = CircuitBreaker(failure_threshold=2, recovery_window=10.0)
    assert cb._state == CircuitState.CLOSED
    assert cb.allow() is True


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_window=60.0)
    for _ in range(3):
        cb.record_failure()
    assert cb._state == CircuitState.OPEN
    assert cb.allow() is False


def test_circuit_breaker_recovery_transitions_to_half_open():
    cb = CircuitBreaker(failure_threshold=2, recovery_window=0.0)
    cb.record_failure()
    cb.record_failure()
    assert cb._state == CircuitState.OPEN
    # 立刻 transition
    assert cb.allow() is True
    assert cb._state == CircuitState.HALF_OPEN


def test_circuit_breaker_success_resets_failures():
    cb = CircuitBreaker(failure_threshold=5, recovery_window=10.0)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb._failures == 0
    assert cb._state == CircuitState.CLOSED


def test_circuit_breaker_global_named_instance():
    cb1 = get_circuit("test_global_breaker_x")
    cb2 = get_circuit("test_global_breaker_x")
    assert cb1 is cb2


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------
def test_token_bucket_initial_burst_consumable():
    b = TokenBucket(rate_per_sec=10.0, burst=5)
    for _ in range(5):
        assert b.acquire() == 0.0
    # 第 6 个必须等待
    wait = b.acquire()
    assert wait > 0.0


def test_token_bucket_refills_over_time():
    b = TokenBucket(rate_per_sec=1000.0, burst=1)
    b.acquire()
    # 等 0.01s 应该补回 ~10 个 token
    time.sleep(0.01)
    assert b.acquire() == 0.0


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------
def test_cost_tracker_records_under_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "10.0")
    monkeypatch.delenv("TENANT_DAILY_BUDGET_USD_A", raising=False)
    t = CostTracker()
    t.record("A", 1.0)
    t.record("A", 2.0)
    assert t.spent("A") == pytest.approx(3.0)


def test_cost_tracker_raises_on_over_budget(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "1.0")
    monkeypatch.delenv("TENANT_DAILY_BUDGET_USD_B", raising=False)
    t = CostTracker()
    t.record("B", 0.5)
    with pytest.raises(exceptions.BudgetExceeded):
        t.record("B", 1.0)


def test_cost_tracker_negative_cost_ignored(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "10.0")
    monkeypatch.delenv("TENANT_DAILY_BUDGET_USD_C", raising=False)
    t = CostTracker()
    t.record("C", -5.0)
    assert t.spent("C") == 0.0


def test_cost_tracker_tenant_specific_budget(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "10.0")
    monkeypatch.setenv("TENANT_DAILY_BUDGET_USD_VIP", "100.0")
    t = CostTracker()
    t.record("VIP", 50.0)  # 不到 VIP 自己的 100 限额
    assert t.spent("VIP") == 50.0


# ---------------------------------------------------------------------------
# ProviderMetrics
# ---------------------------------------------------------------------------
def test_provider_metrics_observe_does_not_raise():
    m = ProviderMetrics()
    # 即使 prometheus_client 缺失,observe 也不应抛错
    m.observe("test-provider", "chat", "ok", 0.123)
    m.observe("test-provider", "chat", "error", 0.5)


# ---------------------------------------------------------------------------
# with_resilience 装饰器
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_with_resilience_retries_retryable_errors():
    attempts = {"n": 0}

    @with_resilience(provider="test_retry_retryable", method="do", retry=RetryPolicy(max_retries=2, base_delay=0.001, jitter=0.0))
    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise exceptions.RateLimitError("429", provider="x")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert attempts["n"] == 3  # 2 次失败 + 第 3 次成功


@pytest.mark.asyncio
async def test_with_resilience_does_not_retry_non_retryable():
    attempts = {"n": 0}

    @with_resilience(provider="test_retry_no_retry", method="do", retry=RetryPolicy(max_retries=5, base_delay=0.001, jitter=0.0))
    async def auth_fail():
        attempts["n"] += 1
        raise exceptions.AuthError("401", provider="x")

    with pytest.raises(exceptions.AuthError):
        await auth_fail()
    assert attempts["n"] == 1


@pytest.mark.asyncio
async def test_with_resilience_opens_circuit_after_failures(monkeypatch: pytest.MonkeyPatch):
    """连续多次失败后,熔断器打开,直接拒绝."""
    name = "test_with_resilience_open_circuit_unique"
    get_circuit(name).__init__(failure_threshold=2, recovery_window=60.0)
    cb = get_circuit(name)

    @with_resilience(
        provider=name,
        method="always_fail",
        retry=RetryPolicy(max_retries=0, base_delay=0.001, jitter=0.0),
    )
    async def always_fail():
        raise exceptions.UpstreamUnavailableError("503", provider="x")

    # 第一次失败 (1 次尝试)
    with pytest.raises(exceptions.UpstreamUnavailableError):
        await always_fail()
    # 第二次失败
    with pytest.raises(exceptions.UpstreamUnavailableError):
        await always_fail()
    # 此时熔断已开
    assert cb._state == CircuitState.OPEN
    # 第三次直接被 CircuitOpenError 拒绝
    with pytest.raises(exceptions.CircuitOpenError):
        await always_fail()


@pytest.mark.asyncio
async def test_with_resilience_records_cost_when_provided():
    captured = {"cost": 0.0}

    def cost_calc(_result):
        captured["cost"] = 0.5
        return 0.5

    @with_resilience(
        provider="test_cost_calc",
        method="do",
        retry=RetryPolicy(max_retries=0, base_delay=0.001, jitter=0.0),
        cost_calculator=cost_calc,
    )
    async def cheap_op():
        return "result"

    result = await cheap_op()
    assert result == "result"
    assert captured["cost"] == 0.5


@pytest.mark.asyncio
async def test_with_resilience_exhausts_retries_then_raises():
    attempts = {"n": 0}

    @with_resilience(
        provider="test_exhaust",
        method="do",
        retry=RetryPolicy(max_retries=2, base_delay=0.001, jitter=0.0),
    )
    async def never_succeeds():
        attempts["n"] += 1
        raise exceptions.UpstreamUnavailableError("nope", provider="x")

    with pytest.raises(exceptions.UpstreamUnavailableError):
        await never_succeeds()
    # 1 + max_retries 次尝试
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_with_resilience_wraps_non_provider_exception(monkeypatch: pytest.MonkeyPatch):
    name = "test_wrap_exception_unique"
    get_circuit(name).__init__(failure_threshold=10, recovery_window=60.0)

    @with_resilience(
        provider=name,
        method="do",
        retry=RetryPolicy(max_retries=1, base_delay=0.001, jitter=0.0),
    )
    async def raises_plain():
        raise ValueError("boom")

    with pytest.raises(exceptions.UpstreamUnavailableError):
        await raises_plain()