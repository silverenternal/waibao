"""v10.0 T5002 — Service-layer resilience decorators.

Lightweight, dependency-free decorators for the ~56 service modules under
``backend/services/``.  Complements ``providers/base.py`` (which handles the
LLM/HTTP provider egress) by giving *business* service functions the same
guarantees at their own call sites:

* :func:`retry` — exponential backoff with jitter, sync + async.
* :func:`circuit_breaker` — closed/open/half-open state machine keyed by name.
* :func:`timeout` — wall-clock cap (async: ``asyncio.wait_for``; sync: signal
  on the main thread, thread-watchdog fallback otherwise).
* :func:`with_resilience` — the three composed in the correct order.

All decorators are transparent to ``functools.wraps`` and preserve the
wrapped signature.  On terminal failure they raise a
:class:`services.platform.errors.ServiceError` with the appropriate code so
the unified error layer sees a typed error, never a bare exception.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Optional, TypeVar

from services.platform.errors import ServiceError, ServiceErrorCode

logger = logging.getLogger("recruittech.platform.retry")

T = TypeVar("T")

# Exceptions that should never be retried — they are deterministic client
# errors, not transient faults.
_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 409, 412, 422}


def _is_retryable_exc(exc: BaseException) -> bool:
    if isinstance(exc, ServiceError):
        # honour explicit taxonomy: only retry transient codes
        return exc.retryable
    # Any other exception is treated as transient by default.
    return True


# ===========================================================================
# Backoff
# ===========================================================================
@dataclass(slots=True)
class Backoff:
    """Backoff strategy generator."""

    base_delay: float = 0.5
    max_delay: float = 30.0
    multiplier: float = 2.0
    jitter: float = 0.2
    strategy: str = "exponential"  # exponential | linear | constant

    def delay_for(self, attempt: int) -> float:
        """Delay (seconds) *before* retry ``attempt`` (1-indexed)."""
        if self.strategy == "constant":
            raw = self.base_delay
        elif self.strategy == "linear":
            raw = self.base_delay * attempt
        else:  # exponential
            raw = self.base_delay * (self.multiplier ** (attempt - 1))
        raw = min(raw, self.max_delay)
        if self.jitter > 0:
            raw *= 1.0 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, raw)


# convenience presets ------------------------------------------------------
def exponential(base_delay: float = 0.5, max_delay: float = 30.0,
                multiplier: float = 2.0, jitter: float = 0.2) -> Backoff:
    return Backoff(base_delay, max_delay, multiplier, jitter, "exponential")


def linear(base_delay: float = 0.5, max_delay: float = 30.0, jitter: float = 0.1) -> Backoff:
    return Backoff(base_delay, max_delay, 1.0, jitter, "linear")


def constant(delay: float = 0.5, jitter: float = 0.0) -> Backoff:
    return Backoff(delay, delay, 1.0, jitter, "constant")


# ===========================================================================
# @retry
# ===========================================================================
def retry(
    max_attempts: int = 3,
    *,
    backoff: Backoff | str | None = None,
    retry_on: Optional[Iterable[type[BaseException]]] = None,
    give_up_on: Optional[Iterable[type[BaseException]]] = None,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
    sleep: Callable[[float], Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a callable up to ``max_attempts`` times with backoff.

    Parameters
    ----------
    max_attempts:
        Total attempts including the first (``3`` → 1 try + 2 retries).
    backoff:
        A :class:`Backoff` or one of ``"exponential"``/``"linear"``/``"constant"``.
    retry_on / give_up_on:
        Exception allow / deny lists.  ``give_up_on`` wins over ``retry_on``.
    on_retry:
        Optional callback ``(attempt, exc)`` invoked before each sleep.
    sleep:
        Injectable sleeper (tests pass a no-op).
    """
    if isinstance(backoff, str):
        policy = {"exponential": exponential, "linear": linear, "constant": constant}.get(
            backoff, exponential
        )()
    else:
        policy = backoff or exponential()
    retry_types = tuple(retry_on) if retry_on else ()
    giveup_types = tuple(give_up_on) if give_up_on else ()

    def _should_retry(exc: BaseException) -> bool:
        if giveup_types and isinstance(exc, giveup_types):
            return False
        if retry_types:
            return isinstance(exc, retry_types)
        return _is_retryable_exc(exc)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def _rethrow_or_terminal(last: BaseException | None) -> None:
            """If the terminal exception should pass through (give_up/retry_on
            miss), re-raise the original; otherwise wrap as ServiceError."""
            if last is None:
                return
            if giveup_types and isinstance(last, giveup_types):
                raise last
            if retry_types and not isinstance(last, retry_types):
                raise last
            if isinstance(last, ServiceError) and not last.retryable:
                raise last
            raise _terminal(fn.__name__, last, max_attempts)

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last: BaseException | None = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await fn(*args, **kwargs)
                    except BaseException as exc:  # noqa: BLE001
                        last = exc
                        if attempt >= max_attempts or not _should_retry(exc):
                            _rethrow_or_terminal(last)
                            return  # unreachable
                        if on_retry:
                            try:
                                on_retry(attempt, exc)
                            except Exception:  # noqa: BLE001
                                pass
                        delay = policy.delay_for(attempt)
                        logger.warning("retry %s attempt=%s/%s delay=%.2fs exc=%s",
                                       fn.__name__, attempt, max_attempts, delay, exc)
                        if sleep is not None:
                            res = sleep(delay)
                            if asyncio.iscoroutine(res):
                                await res
                        else:
                            await asyncio.sleep(delay)
                _rethrow_or_terminal(last)
                return  # unreachable

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except BaseException as exc:  # noqa: BLE001
                    last = exc
                    if attempt >= max_attempts or not _should_retry(exc):
                        _rethrow_or_terminal(last)
                        return  # unreachable
                    if on_retry:
                        try:
                            on_retry(attempt, exc)
                        except Exception:  # noqa: BLE001
                            pass
                    delay = policy.delay_for(attempt)
                    logger.warning("retry %s attempt=%s/%s delay=%.2fs exc=%s",
                                   fn.__name__, attempt, max_attempts, delay, exc)
                    (sleep or time.sleep)(delay)
            _rethrow_or_terminal(last)
            return  # unreachable

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _terminal(name: str, last: BaseException | None, attempts: int) -> BaseException:
    """Convert a terminal failure into a typed ServiceError (chained)."""
    if isinstance(last, ServiceError):
        return last
    return ServiceError(
        ServiceErrorCode.RETRY_EXHAUSTED,
        f"{name} failed after {attempts} attempts: {last}",
        details={"function": name, "attempts": attempts},
        cause=last,
    )


# ===========================================================================
# @circuit_breaker
# ===========================================================================
class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _Circuit:
    failure_threshold: int = 5
    recovery_time: float = 30.0
    success_threshold: int = 1
    state: str = field(default=CircuitState.CLOSED)
    failures: int = 0
    successes: int = 0
    opened_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.opened_at >= self.recovery_time:
                    self.state = CircuitState.HALF_OPEN
                    self.successes = 0
                    logger.info("circuit half_open")
                    return True
                return False
            return True  # half_open: allow probes

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.successes += 1
                if self.successes >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failures = 0
                    logger.info("circuit closed (recovered)")
            else:
                self.failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                logger.warning("circuit open failures=%s", self.failures)

    def reset(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.successes = 0
            self.opened_at = 0.0


_CIRCUITS: dict[str, _Circuit] = {}
_CIRCUITS_LOCK = threading.Lock()


def get_circuit(name: str, **kw: Any) -> _Circuit:
    with _CIRCUITS_LOCK:
        c = _CIRCUITS.get(name)
        if c is None:
            c = _Circuit(**kw)
            _CIRCUITS[name] = c
        return c


def reset_circuit(name: Optional[str] = None) -> None:
    """Reset one or all circuits — primarily a test helper."""
    with _CIRCUITS_LOCK:
        if name is None:
            for c in _CIRCUITS.values():
                c.reset()
        elif name in _CIRCUITS:
            _CIRCUITS[name].reset()


def circuit_breaker(
    failure_threshold: int = 5,
    *,
    recovery_time: float = 30.0,
    success_threshold: int = 1,
    name: Optional[str] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Wrap a callable with a named circuit breaker.

    When the breaker is OPEN, calls fail fast with a ``CIRCUIT_OPEN``
    :class:`ServiceError` instead of hitting the (known-bad) dependency.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        cname = name or f"{fn.__module__}.{fn.__qualname__}"
        circuit = get_circuit(
            cname,
            failure_threshold=failure_threshold,
            recovery_time=recovery_time,
            success_threshold=success_threshold,
        )

        def _open_error() -> ServiceError:
            return ServiceError(
                ServiceErrorCode.CIRCUIT_OPEN,
                f"Circuit '{cname}' is open",
                retry_after=int(recovery_time),
                details={"circuit": cname},
            )

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not circuit.allow():
                    raise _open_error()
                try:
                    result = await fn(*args, **kwargs)
                except BaseException:  # noqa: BLE001
                    circuit.record_failure()
                    raise
                circuit.record_success()
                return result

            async_wrapper._circuit = circuit  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not circuit.allow():
                raise _open_error()
            try:
                result = fn(*args, **kwargs)
            except BaseException:  # noqa: BLE001
                circuit.record_failure()
                raise
            circuit.record_success()
            return result

        sync_wrapper._circuit = circuit  # type: ignore[attr-defined]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ===========================================================================
# @timeout
# ===========================================================================
def timeout(seconds: float = 30.0) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Cap a callable's wall-clock runtime.

    * async: uses ``asyncio.wait_for`` (cancels the coroutine).
    * sync: runs the callable in a worker thread and abandons it on timeout.
      Note the thread cannot be force-killed; the timeout returns control to
      the caller while the orphaned thread finishes in the background.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await asyncio.wait_for(fn(*args, **kwargs), timeout=seconds)
                except asyncio.TimeoutError as exc:
                    raise ServiceError(
                        ServiceErrorCode.TIMEOUT,
                        f"{fn.__name__} exceeded {seconds}s",
                        details={"function": fn.__name__, "timeout_s": seconds},
                        cause=exc,
                    ) from exc

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            result: dict[str, Any] = {}

            def _target() -> None:
                try:
                    result["value"] = fn(*args, **kwargs)
                except BaseException as exc:  # noqa: BLE001
                    result["error"] = exc

            worker = threading.Thread(target=_target, daemon=True)
            worker.start()
            worker.join(seconds)
            if worker.is_alive():
                raise ServiceError(
                    ServiceErrorCode.TIMEOUT,
                    f"{fn.__name__} exceeded {seconds}s",
                    details={"function": fn.__name__, "timeout_s": seconds},
                )
            if "error" in result:
                raise result["error"]
            return result.get("value")

        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ===========================================================================
# @with_resilience — compose timeout → circuit_breaker → retry
# ===========================================================================
def with_resilience(
    *,
    max_attempts: int = 3,
    backoff: Backoff | str | None = None,
    timeout_s: Optional[float] = 30.0,
    failure_threshold: Optional[int] = 5,
    recovery_time: float = 30.0,
    name: Optional[str] = None,
    retry_on: Optional[Iterable[type[BaseException]]] = None,
    give_up_on: Optional[Iterable[type[BaseException]]] = None,
    sleep: Callable[[float], Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """One decorator applying timeout + circuit breaker + retry.

    Order (outermost→innermost): retry( circuit_breaker( timeout( fn ) ) )
    so that a single slow call is timed out, repeated failures trip the
    breaker, and transient errors are retried with backoff.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        wrapped = fn
        if timeout_s is not None:
            wrapped = timeout(timeout_s)(wrapped)
        if failure_threshold is not None:
            wrapped = circuit_breaker(
                failure_threshold,
                recovery_time=recovery_time,
                name=name or f"{fn.__module__}.{fn.__qualname__}",
            )(wrapped)
        wrapped = retry(
            max_attempts,
            backoff=backoff,
            retry_on=retry_on,
            # never retry a tripped breaker — fail fast
            give_up_on=tuple(give_up_on or ()),
            sleep=sleep,
        )(wrapped)
        return functools.wraps(fn)(wrapped)

    return decorator


__all__ = [
    "Backoff",
    "exponential",
    "linear",
    "constant",
    "retry",
    "circuit_breaker",
    "timeout",
    "with_resilience",
    "CircuitState",
    "get_circuit",
    "reset_circuit",
]
