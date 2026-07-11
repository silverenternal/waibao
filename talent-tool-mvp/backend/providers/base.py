"""共享中间件: retry / circuit breaker / cost tracker / rate limit / metrics.

所有 Provider 的外部调用都必须包在 @with_resilience 装饰器中。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar

from .exceptions import (
    AuthError,
    BudgetExceeded,
    CircuitOpenError,
    ProviderError,
    RateLimitError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _otel_span(name: str, attributes: dict | None = None):
    """T1001: 返回 OTel span context manager; 依赖缺失时返回 nullcontext."""
    try:
        from services.telemetry import span as _span

        return _span(name, **(attributes or {}))
    except Exception:  # noqa: BLE001
        return nullcontext()


# ---------------------------------------------------------------------------
# Cache step config (T806) — 供 with_resilience 用
# ---------------------------------------------------------------------------
@dataclass
class CacheConfig:
    """启用 LLM cache 时的 key 构造与开关."""

    enabled: bool = False
    key_builder: Optional[Callable[[str, str, tuple, dict], str]] = None
    ttl_seconds: Optional[int] = None  # None 用 cache 默认

    @classmethod
    def default_llm(cls) -> "CacheConfig":
        """默认 LLM cache 配置: 复用 services.llm_cache.LLMCache.make_key 风格."""
        from services.llm_cache import LLMCache as _LLMCache

        def _key(provider: str, method: str, args: tuple, kwargs: dict) -> str:
            messages = kwargs.get("messages") or (args[0] if args else [])
            model = kwargs.get("model") or "unknown"
            temperature = kwargs.get("temperature")
            return _LLMCache.make_key(provider, model, messages, temperature)

        return cls(enabled=True, key_builder=_key)


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RetryPolicy:
    """指数退避重试策略."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.2

    def delay_for(self, attempt: int) -> float:
        """计算第 N 次重试前的等待秒数."""
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter > 0:
            import random

            delay *= 1.0 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, delay)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """closed/open/half_open 三态熔断器."""

    failure_threshold: int = 5
    recovery_window: float = 60.0
    _state: str = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)

    def allow(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_window:
                self._state = CircuitState.HALF_OPEN
                logger.info("circuit_breaker.half_open")
                return True
            return False
        # half_open: 仅允许一个探测请求
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("circuit_breaker.open failures=%s", self._failures)


# ---------------------------------------------------------------------------
# Rate Limiter (token bucket, per provider)
# ---------------------------------------------------------------------------
@dataclass
class TokenBucket:
    """单 provider 维度的 token bucket."""

    rate_per_sec: float = 10.0
    burst: int = 20
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()

    def acquire(self, tokens: float = 1.0) -> float:
        """尝试取令牌,返回需要等待的秒数 (0 表示立即可取)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_sec)
        self._last_refill = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return 0.0
        deficit = tokens - self._tokens
        return deficit / self.rate_per_sec


# ---------------------------------------------------------------------------
# Cost Tracker (per tenant per day) — T806 升级: tenant + provider + model 维度聚合
# ---------------------------------------------------------------------------
class CostTracker:
    """内存级多维度成本累计 + 异步持久化到 Supabase.

    生产环境推荐使用 services.cost_tracker.py 的 CostTrackerService;
    本类作为 with_resilience 内 fast path 的最小可用实现。
    """

    def __init__(self) -> None:
        self._spent: dict[str, float] = {}  # tenant:date -> amount
        self._by_provider_model: dict[str, float] = {}  # tenant:date:provider:model -> amount
        self._limits: dict[str, float] = self._load_limits()
        # Async persistence hook (setter 由 main.py 启动时注入,默认 no-op)
        self._persist_cb: Optional[Callable[[dict], None]] = None

    def set_persistence(self, cb: Optional[Callable[[dict], None]]) -> None:
        """注入持久化 callback (例如写 Supabase). 失败必须由 callback 内部捕获,不抛出."""
        self._persist_cb = cb

    def _load_limits(self) -> dict[str, float]:
        """从环境变量加载租户预算,格式: TENANT_DAILY_BUDGET_USD_<tenant>=<float>."""
        limits: dict[str, float] = {"_default": float(os.getenv("DAILY_BUDGET_USD", "50.0"))}
        for key, value in os.environ.items():
            if key.startswith("TENANT_DAILY_BUDGET_USD_"):
                tenant = key.removeprefix("TENANT_DAILY_BUDGET_USD_").lower()
                try:
                    limits[tenant] = float(value)
                except ValueError:
                    logger.warning("cost_tracker.invalid_budget tenant=%s value=%s", tenant, value)
        return limits

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _key(self, tenant: str) -> str:
        return f"{tenant}:{self._today()}"

    def _pm_key(self, tenant: str, provider: str, model: str) -> str:
        return f"{tenant}:{self._today()}:{provider}:{model}"

    def record(
        self,
        tenant: str,
        cost_usd: float,
        provider: str = "unknown",
        model: str = "unknown",
    ) -> None:
        """记录一次外部调用成本.

        provider/model 供 dashboard by-provider 聚合用;不传则用 unknown.
        """
        if cost_usd <= 0:
            return
        key = self._key(tenant)
        self._spent[key] = self._spent.get(key, 0.0) + cost_usd
        pm_key = self._pm_key(tenant, provider, model)
        self._by_provider_model[pm_key] = self._by_provider_model.get(pm_key, 0.0) + cost_usd
        limit = self._limits.get(tenant.lower(), self._limits["_default"])
        if self._spent[key] > limit:
            raise BudgetExceeded(
                f"tenant={tenant} daily cost {self._spent[key]:.4f} > limit {limit:.2f} USD",
                details={"tenant": tenant, "spent": self._spent[key], "limit": limit},
            )
        # 异步持久化 (non-blocking,失败不影响业务)
        if self._persist_cb is not None:
            try:
                self._persist_cb(
                    {
                        "tenant": tenant,
                        "provider": provider,
                        "model": model,
                        "cost_usd": float(cost_usd),
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception:  # noqa: BLE001
                logger.exception("cost_tracker.persist_failed")

    def spent(self, tenant: str) -> float:
        return self._spent.get(self._key(tenant), 0.0)

    def by_provider_model(self, since_days: int = 30) -> dict[str, float]:
        """聚合内存内 by-provider-model (最近 N 天)."""
        return dict(self._by_provider_model)


# ---------------------------------------------------------------------------
# Metrics (Prometheus client, no-op if 不可用)
# ---------------------------------------------------------------------------
class ProviderMetrics:
    """成功率 / p50/p95 延迟 / 调用次数."""

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Histogram  # type: ignore[import-not-found]

            self._counter = Counter(
                "provider_calls_total",
                "Provider 调用次数",
                ["provider", "method", "status"],
            )
            self._latency = Histogram(
                "provider_latency_seconds",
                "Provider 调用延迟 (秒)",
                ["provider", "method"],
                buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
            )
            self._enabled = True
        except Exception:  # pragma: no cover - 可选依赖
            self._enabled = False
            logger.info("provider_metrics.disabled reason=prometheus_client_missing")

    def observe(self, provider: str, method: str, status: str, latency: float) -> None:
        if not self._enabled:
            return
        try:
            self._counter.labels(provider=provider, method=method, status=status).inc()
            self._latency.labels(provider=provider, method=method).observe(latency)
        except Exception:  # pragma: no cover
            logger.exception("provider_metrics.observe_failed")


# ---------------------------------------------------------------------------
# 全局单例 (进程内)
# ---------------------------------------------------------------------------
_GLOBAL_CIRCUITS: dict[str, CircuitBreaker] = {}
_GLOBAL_BUCKETS: dict[str, TokenBucket] = {}
_COST_TRACKER = CostTracker()
_METRICS = ProviderMetrics()


def get_circuit(name: str) -> CircuitBreaker:
    return _GLOBAL_CIRCUITS.setdefault(name, CircuitBreaker())


def get_bucket(name: str, rate: float, burst: int) -> TokenBucket:
    if name not in _GLOBAL_BUCKETS:
        _GLOBAL_BUCKETS[name] = TokenBucket(rate_per_sec=rate, burst=burst)
    return _GLOBAL_BUCKETS[name]


def get_cost_tracker() -> CostTracker:
    return _COST_TRACKER


def get_metrics() -> ProviderMetrics:
    return _METRICS


# ---------------------------------------------------------------------------
# 装饰器: with_resilience
# ---------------------------------------------------------------------------
def with_resilience(
    *,
    provider: str,
    method: str,
    retry: RetryPolicy | None = None,
    rate_per_sec: float = 10.0,
    burst: int = 20,
    cost_calculator: Callable[[Any], float] | None = None,
    tenant_arg: str | None = None,
    cache_config: "CacheConfig | None" = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """统一为外部调用加上: cache -> rate limit -> circuit breaker -> retry -> cost -> metrics."""
    policy = retry or RetryPolicy()
    circuit = get_circuit(provider)
    bucket = get_bucket(provider, rate_per_sec, burst)
    cost_tracker = get_cost_tracker()
    metrics = get_metrics()

    # Lazy import 避免循环依赖
    if cache_config is not None:
        from services.llm_cache import get_cache as _get_cache
        cache = _get_cache()
    else:
        cache = None

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # T1001: OpenTelemetry span,记录 provider / method / model.
            model_name = kwargs.get("model") or provider
            with _otel_span(
                "llm_call",
                {
                    "provider": provider,
                    "method": method,
                    "model": str(model_name),
                },
            ):
                return await _run(args, kwargs, fn)

        return wrapper

    async def _run(args: tuple, kwargs: dict, fn: Callable[..., Awaitable[T]]) -> T:
        # cache step: 只对 cache_config.enabled 的调用起作用
        cache_key: str | None = None
        if cache is not None and cache_config is not None and cache_config.enabled:
            try:
                cache_key = cache_config.key_builder(provider, method, args, kwargs)
                hit = cache.get(cache_key)
                if hit is not None:
                    metrics.observe(
                        provider,
                        method,
                        "cache_hit",
                        0.0,
                    )
                    return hit
            except Exception:  # noqa: BLE001 - cache 不能阻塞业务
                logger.warning("cache.read_failed provider=%s method=%s", provider, method)
                cache_key = None

        if not circuit.allow():
            raise CircuitOpenError(
                f"provider={provider} circuit is open",
                provider=provider,
            )

        wait = bucket.acquire()
        if wait > 0:
            await asyncio.sleep(wait)

        last_exc: Exception | None = None
        for attempt in range(1, policy.max_retries + 2):  # 1 + max_retries
            start = time.monotonic()
            status = "ok"
            try:
                result = await fn(*args, **kwargs)
                circuit.record_success()
                metrics.observe(
                    provider,
                    method,
                    "ok",
                    time.monotonic() - start,
                )
                # cache store step — 失败只 warn 不抛
                if cache is not None and cache_key is not None:
                    try:
                        cache.set(cache_key, result)
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "cache.write_failed provider=%s method=%s",
                            provider,
                            method,
                        )
                if cost_calculator is not None:
                    try:
                        cost = cost_calculator(result)
                        tenant = (
                            kwargs.get(tenant_arg) if tenant_arg else "default"
                        ) or "default"
                        model_name = kwargs.get("model") or provider
                        cost_tracker.record(
                            tenant, cost, provider=provider, model=model_name
                        )
                    except ProviderError:
                        raise
                    except Exception:
                        logger.exception("cost_tracker.error provider=%s", provider)
                return result
            except ProviderError as exc:
                last_exc = exc
                status = "error"
                metrics.observe(
                    provider,
                    method,
                    "error",
                    time.monotonic() - start,
                )
                if not exc.retryable or attempt > policy.max_retries:
                    circuit.record_failure()
                    raise
                delay = policy.delay_for(attempt)
                logger.warning(
                    "retry provider=%s attempt=%s delay=%.2fs exc=%s",
                    provider,
                    attempt,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
            except Exception as exc:  # 非 ProviderError 视为可重试
                last_exc = exc
                status = "error"
                metrics.observe(
                    provider,
                    method,
                    "error",
                    time.monotonic() - start,
                )
                if attempt > policy.max_retries:
                    circuit.record_failure()
                    raise UpstreamUnavailableError(
                        str(exc), provider=provider
                    ) from exc
                delay = policy.delay_for(attempt)
                await asyncio.sleep(delay)

        # 理论不会到这里
        if last_exc is not None:
            raise last_exc
        raise UpstreamUnavailableError("exhausted retries", provider=provider)

    return decorator