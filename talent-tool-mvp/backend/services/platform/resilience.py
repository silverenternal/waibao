"""v10.0 T5005 — Distributed state resilience + observability gate.

This module layers distributed-state semantics on top of the existing
``feature_flag`` / ``service_toggle`` / ``config_service`` modules without
rewriting them (they are large and heavily tested). It provides:

* :class:`RedisCAS` — atomic compare-and-set over Redis (the primitive that
  makes flag/toggle mutations safe under concurrent writers). Falls back to
  an in-process lock when Redis is unavailable.
* :func:`fail_open` / :func:`fail_closed` — explicit degradation postures.
  ``fail_open`` lets a request through when the state store is unreachable
  (availability); ``fail_closed`` blocks it (safety). Every degraded
  decision increments ``service_degraded_total``.
* :func:`validate_config_schema` — JSON-Schema-style validation for
  ``config_service`` writes, so a bad operator payload can't corrupt a
  service.
* :func:`redact_secrets` — recursively redact secret-looking keys before
  logging / auditing a config value.
* :func:`init_production_observability` — the production **fail-fast** gate:
  in production, telemetry / metrics must initialise; if they can't, we fail
  fast instead of running blind.
* :func:`new_trace_id` / :func:`scrub_pii` — a per-request trace id and a
  PII scrubber for log payloads.

Design note: everything here degrades to a *deterministic* in-process
fallback so unit tests run without Redis / Supabase. The fallbacks are
clearly labelled in metric ``reason`` labels so operators can see when the
fleet is running degraded.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("recruittech.platform.resilience")

# ===========================================================================
# Redis connection (shared, lazy, optional)
# ===========================================================================
_REDIS = None
_REDIS_LOCK = threading.Lock()


def _get_redis():
    """Return a redis client or None.

    Cached after first successful ping. Reads ``WAIBAO_REDIS_URL`` /
    ``REDIS_URL``.
    """
    global _REDIS
    if _REDIS is not None:
        return _REDIS
    url = os.environ.get("WAIBAO_REDIS_URL") or os.environ.get("REDIS_URL")
    if not url:
        return None
    with _REDIS_LOCK:
        if _REDIS is not None:
            return _REDIS
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            _REDIS = client
            logger.info("resilience.redis.connected url=%s", url)
            return _REDIS
        except Exception as exc:  # noqa: BLE001
            logger.warning("resilience.redis.unavailable err=%s", exc)
            return None


def reset_redis_for_tests() -> None:
    """Drop the cached Redis client (tests flip env vars)."""
    global _REDIS
    _REDIS = None


# ===========================================================================
# Compare-And-Set (atomic) — the distributed-state primitive
# ===========================================================================
@dataclass
class CASResult:
    """Outcome of a compare-and-set."""

    success: bool
    key: str
    value: Any
    reason: str = ""


class RedisCAS:
    """Atomic compare-and-set over Redis with an in-process fallback.

    Usage::

        cas = RedisCAS()
        ok = cas.set_if_absent("lock:flag:rollout", owner, ttl_s=30)
        ...
        cas.release("lock:flag:rollout", owner)

    When Redis is unavailable, a process-local :class:`threading.Lock` is
    used so the contract holds within a single process (good enough for
    tests / single-replica dev). Multi-replica correctness requires Redis.
    """

    def __init__(self, prefix: str = "cas:") -> None:
        self.prefix = prefix
        self._local_locks: Dict[str, threading.Lock] = {}
        self._local_values: Dict[str, Tuple[str, float]] = {}  # key -> (owner, expires)

    def _k(self, key: str) -> str:
        return f"{self.prefix}{key}"

    # ---- set_if_absent (acquire) ----------------------------------------
    def set_if_absent(self, key: str, value: str, *, ttl_s: float = 30.0) -> bool:
        """Atomically set ``key`` only if it does not exist.

        Returns True if the lock was acquired. Uses Redis ``SET NX PX`` when
        available, else a process-local dict guarded by a lock.
        """
        r = _get_redis()
        if r is not None:
            try:
                # SET key value NX PX ttl  -> True if set, None otherwise
                return bool(r.set(self._k(key), value, nx=True, px=int(ttl_s * 1000)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("cas.redis.set_failed key=%s err=%s", key, exc)
                _inc_degraded("cas", "redis_set_failed")
        # in-process fallback
        lock = self._local_locks.setdefault(key, threading.Lock())
        with lock:
            now = time.monotonic()
            existing = self._local_values.get(key)
            if existing and existing[1] > now:
                return False
            self._local_values[key] = (value, now + ttl_s)
            return True

    # ---- compare_and_set (optimistic update) ----------------------------
    def compare_and_set(self, key: str, expected: str, new_value: str,
                        *, ttl_s: Optional[float] = None) -> CASResult:
        """Set ``key`` to ``new_value`` only if its current value equals
        ``expected``. Returns a :class:`CASResult`.
        """
        r = _get_redis()
        if r is not None:
            try:
                # atomic via Lua: GET == expected then SET
                script = """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                  redis.call('SET', KEYS[1], ARGV[2])
                  return 1
                else
                  return 0
                end
                """
                if r.eval(script, 1, self._k(key), expected, new_value):
                    return CASResult(True, key, new_value, "redis.cas_ok")
                cur = r.get(self._k(key))
                return CASResult(False, key, cur, "redis.cas_mismatch")
            except Exception as exc:  # noqa: BLE001
                logger.warning("cas.redis.cas_failed key=%s err=%s", key, exc)
                _inc_degraded("cas", "redis_cas_failed")
        # in-process fallback
        lock = self._local_locks.setdefault(key, threading.Lock())
        with lock:
            cur_owner = self._local_values.get(key, (None, 0.0))[0]
            if cur_owner == expected or (cur_owner is None and expected == ""):
                self._local_values[key] = (
                    new_value,
                    time.monotonic() + (ttl_s or 3600),
                )
                return CASResult(True, key, new_value, "local.cas_ok")
            return CASResult(False, key, cur_owner, "local.cas_mismatch")

    # ---- release --------------------------------------------------------
    def release(self, key: str, owner: str) -> bool:
        """Release a previously acquired lock, but only if we still own it."""
        r = _get_redis()
        if r is not None:
            try:
                script = """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                  return redis.call('DEL', KEYS[1])
                else
                  return 0
                end
                """
                return bool(r.eval(script, 1, self._k(key), owner))
            except Exception as exc:  # noqa: BLE001
                logger.warning("cas.redis.release_failed key=%s err=%s", key, exc)
        lock = self._local_locks.get(key)
        if lock is None:
            return False
        with lock:
            cur = self._local_values.get(key)
            if cur and cur[0] == owner:
                self._local_values.pop(key, None)
                return True
            return False


# Singleton CAS used by the flag/toggle helpers below.
_cas = RedisCAS()


# ===========================================================================
# Fail-open / fail-closed postures
# ===========================================================================
class DegradedDecision(RuntimeError):
    """Raised internally when a fail-closed store is unreachable."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def fail_open(name: str, *, check: Callable[[], bool], default: bool = True) -> bool:
    """Evaluate ``check``; on any exception, return ``default`` (availability).

    Increments ``service_degraded_total`` with reason ``fail_open`` so the
    silent degrade is observable. Use this when *availability* matters more
    than correctness (e.g. showing a non-critical UI feature).
    """
    try:
        return bool(check())
    except Exception as exc:  # noqa: BLE001
        logger.warning("fail_open.degraded name=%s err=%s", name, exc)
        _inc_degraded(name, "fail_open")
        return default


def fail_closed(name: str, *, check: Callable[[], bool]) -> bool:
    """Evaluate ``check``; on any exception, return False (safety).

    Increments ``service_degraded_total`` with reason ``fail_closed``. Use
    this when *safety* matters more than availability (e.g. a data-export
    gate that must not leak when the flag store is down).
    """
    try:
        return bool(check())
    except Exception as exc:  # noqa: BLE001
        logger.warning("fail_closed.degraded name=%s err=%s", name, exc)
        _inc_degraded(name, "fail_closed")
        return False


def distributed_flag_enabled(name: str, *, user_id: Optional[str] = None,
                             org_id: Optional[str] = None,
                             posture: str = "fail_open") -> bool:
    """Read a feature flag with an explicit degradation posture.

    Wraps ``services.platform.feature_flag.is_enabled`` so the rest of the
    platform gets a single, observable distributed-state read path. When the
    underlying store (Redis/Supabase) is unreachable:

    * ``fail_open`` (default) returns True — availability.
    * ``fail_closed`` returns False — safety.
    """
    from services.platform import feature_flag

    def _read() -> bool:
        return bool(feature_flag.is_enabled(name, user_id=user_id, org_id=org_id))

    if posture == "fail_closed":
        return fail_closed(f"flag:{name}", check=_read)
    return fail_open(f"flag:{name}", check=_read, default=True)


# ===========================================================================
# Config schema validation + secret redaction
# ===========================================================================
class ConfigValidationError(ValueError):
    """Raised when a config value fails schema validation."""


# Keys whose values are treated as secrets and redacted everywhere.
SECRET_KEY_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|private[_-]?key|client[_-]?secret)"),
)


def validate_config_schema(value: Any, schema: Optional[Dict[str, Any]] = None) -> Any:
    """Validate / coerce a config value against a tiny JSON-Schema subset.

    Supported schema fields::

        {"type": "object",
         "required": ["endpoint"],
         "properties": {"endpoint": {"type": "string"},
                        "timeout": {"type": "number", "minimum": 0}},
         "additionalProperties": false}

    Only the subset we actually need is implemented (no external jsonschema
    dependency). Returns the (possibly coerced) value. Raises
    :class:`ConfigValidationError` on any violation.
    """
    if not schema:
        return value
    return _validate_node(value, schema, path="$")


def _validate_node(value: Any, schema: Dict[str, Any], path: str) -> Any:
    expected = schema.get("type")
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    if expected:
        py_type = type_map.get(expected)
        if py_type is None:
            raise ConfigValidationError(f"{path}: unknown type {expected!r}")
        # note: bool is a subclass of int — exclude it for integer/number
        if expected in ("integer", "number") and isinstance(value, bool):
            raise ConfigValidationError(f"{path}: expected {expected}, got bool")
        if not isinstance(value, py_type):
            raise ConfigValidationError(
                f"{path}: expected {expected}, got {type(value).__name__}"
            )

    # numeric bounds
    if expected in ("number", "integer") and isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            raise ConfigValidationError(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ConfigValidationError(f"{path}: {value} > maximum {schema['maximum']}")

    # string constraints
    if expected == "string" and isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ConfigValidationError(f"{path}: too short")
        if "pattern" in schema and not re.match(schema["pattern"], value):
            raise ConfigValidationError(f"{path}: pattern mismatch")

    # array items
    if expected == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            value = [_validate_node(v, item_schema, f"{path}[{i}]")
                     for i, v in enumerate(value)]

    # object properties
    if expected == "object" and isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                raise ConfigValidationError(f"{path}: missing required {req!r}")
        result: Dict[str, Any] = {}
        for k, v in value.items():
            if k in props:
                result[k] = _validate_node(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                raise ConfigValidationError(f"{path}: unexpected property {k!r}")
            else:
                result[k] = v
        return result

    return value


def redact_secrets(value: Any, *, replacement: str = "***REDACTED***") -> Any:
    """Recursively redact any key that looks like a secret.

    Used before logging / auditing a config value. Returns a deep copy with
    secret values replaced. Lists and nested dicts are traversed.
    """
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if _is_secret_key(k):
                out[k] = replacement
            else:
                out[k] = redact_secrets(v, replacement=replacement)
        return out
    if isinstance(value, list):
        return [redact_secrets(v, replacement=replacement) for v in value]
    return value


def _is_secret_key(key: str) -> bool:
    return any(p.search(key) for p in SECRET_KEY_PATTERNS)


# ===========================================================================
# Production observability fail-fast gate
# ===========================================================================
def is_production_env() -> bool:
    """True when the process is running in production.

    Reads ``ENV`` / ``ENVIRONMENT`` / ``APP_ENV``; treats ``prod*`` /
    ``production`` as production.
    """
    env = (
        os.environ.get("ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or "development"
    ).strip().lower()
    return env.startswith("prod")


def init_production_observability(*, service_name: str = "waibao-backend",
                                  require_metrics: bool = True,
                                  require_telemetry: bool = False) -> None:
    """Production fail-fast gate for observability.

    In production we MUST be able to see what the system is doing. If
    metrics (or telemetry, when required) cannot initialise, this function
    raises rather than letting the process run blind. In non-production
    environments it logs a warning and continues.

    Call this once at startup, after ``init_metrics`` / ``init_telemetry``.
    """
    prod = is_production_env()
    from services.observability import metrics as _metrics

    if require_metrics and not _metrics.is_enabled():
        msg = "metrics subsystem failed to initialise (prometheus_client)"
        if prod:
            logger.error("observability.fail_fast: %s", msg)
            raise RuntimeError(f"observability fail-fast: {msg}")
        logger.warning("observability.degraded (non-prod): %s", msg)
        _inc_degraded("metrics", "init_failed")

    if require_telemetry:
        from services.observability import telemetry as _telemetry

        if _telemetry.get_tracer(service_name) is None:
            msg = "telemetry tracer unavailable (opentelemetry)"
            if prod:
                logger.error("observability.fail_fast: %s", msg)
                raise RuntimeError(f"observability fail-fast: {msg}")
            logger.warning("observability.degraded (non-prod): %s", msg)
            _inc_degraded("telemetry", "init_failed")


# ===========================================================================
# trace_id + PII scrubber
# ===========================================================================
_TRACE_ID_CTX = threading.local()


def new_trace_id() -> str:
    """Generate and stash a per-thread trace id (UUIDv4 hex).

    Falls back to a short random id if uuid is unavailable. The id is also
    stored in thread-local context so log formatters can pick it up via
    :func:`current_trace_id`.
    """
    tid = uuid.uuid4().hex
    _TRACE_ID_CTX.value = tid
    return tid


def current_trace_id() -> Optional[str]:
    """Return the trace id for the current thread, or None."""
    return getattr(_TRACE_ID_CTX, "value", None)


def set_trace_id(tid: str) -> None:
    """Attach an externally-generated trace id (e.g. from an HTTP header)."""
    _TRACE_ID_CTX.value = tid


def clear_trace_id() -> None:
    """Drop the trace id (call at request teardown)."""
    if hasattr(_TRACE_ID_CTX, "value"):
        del _TRACE_ID_CTX.value


# PII patterns — deliberately conservative; extend as new shapes appear.
_PII_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    # PRC resident identity card (18 digits, last may be X)
    ("id_card", re.compile(r"\b\d{17}[\dXx]\b")),
    # PRC mobile phone (11 digits starting with 1)
    ("phone", re.compile(r"\b1[3-9]\d{9}\b")),
    # email
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # credit card (13-19 digits)
    ("card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    # bearer token
    ("token", re.compile(r"(?i)\b(bearer|token)[\s:=]+([A-Za-z0-9._\-]{20,})\b")),
)


def scrub_pii(value: Any, *, replacement: str = "***") -> Any:
    """Scrub PII from a value before it is logged / shipped off-host.

    * Strings are run through :data:`_PII_PATTERNS`.
    * Dicts are traversed recursively; keys that look like PII
      (``email``, ``phone``, ``id_card``…) have their whole value replaced.
    * Lists are mapped.
    """
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            lk = str(k).lower()
            if any(t in lk for t in ("email", "phone", "mobile", "id_card", "idcard", "card", "token", "password")):
                out[k] = replacement
            else:
                out[k] = scrub_pii(v, replacement=replacement)
        return out
    if isinstance(value, list):
        return [scrub_pii(v, replacement=replacement) for v in value]
    if isinstance(value, str):
        return _scrub_string(value, replacement=replacement)
    return value


def _scrub_string(text: str, *, replacement: str) -> str:
    out = text
    # token handled specially: keep the label, redact the secret part
    out = _PII_PATTERNS[4][1].sub(
        lambda m: f"{m.group(1)}={replacement}", out, count=0
    )
    for _, pat in _PII_PATTERNS[:4]:
        out = pat.sub(replacement, out)
    return out


# ===========================================================================
# Metrics helper (local import to avoid cycles)
# ===========================================================================
def _inc_degraded(service: str, reason: str) -> None:
    try:
        from services.observability.metrics import inc_degraded

        inc_degraded(service, reason)
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "RedisCAS",
    "CASResult",
    "DegradedDecision",
    "ConfigValidationError",
    "fail_open",
    "fail_closed",
    "distributed_flag_enabled",
    "validate_config_schema",
    "redact_secrets",
    "is_production_env",
    "init_production_observability",
    "new_trace_id",
    "current_trace_id",
    "set_trace_id",
    "clear_trace_id",
    "scrub_pii",
    "reset_redis_for_tests",
]
