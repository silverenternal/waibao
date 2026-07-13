"""T2602 - Rate limiter using slowapi + Redis backend.

Wraps slowapi's ``Limiter`` so the rest of the codebase can:

  * install a single ``SlowAPIMiddleware`` in :pymod:`main`
  * call :func:`enforce_request` from a per-tenant middleware that overrides
    the slowapi key function (``tenant:user:route``)
  * receive a 429 with ``Retry-After`` + ``X-RateLimit-*`` headers (handled in
    :func:`rate_limit_exceeded_handler`).

The limiter is **process-singleton** but the storage URI is configurable so
unit-tests can fall back to ``memory://`` and prod can use Redis.

All limits are derived from the tenant's plan (see :pymod:`quota`).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

logger = logging.getLogger("recruittech.platform.rate_limiter")


# -------------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------------

def _default_key_func(request: Request) -> str:
    """Key by tenant > user > ip when available, else just ip."""
    from .tenant_context import get_tenant_context

    ctx = get_tenant_context()
    if ctx is not None:
        who = str(ctx.user_id) if ctx.user_id else "anon"
        return f"{ctx.tenant_id}:{who}:{request.url.path}"
    return get_remote_address(request)


def _build_storage_uri() -> str:
    """Pick a Redis URL when configured, in-memory otherwise."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        return redis_url
    return "memory://"


_storage_uri = _build_storage_uri()
_limiter: Optional[Limiter] = None


def get_limiter() -> Limiter:
    """Lazy singleton."""
    global _limiter
    if _limiter is None:
        _limiter = Limiter(
            key_func=_default_key_func,
            storage_uri=_storage_uri,
            strategy="moving-window",
            headers_enabled=True,
            default_limits=["1000/minute"],
        )
    return _limiter


def set_limiter(limiter: Limiter) -> None:
    """Test hook — replace the singleton (e.g. with an in-memory stub)."""
    global _limiter
    _limiter = limiter


# -------------------------------------------------------------------------
# Per-route enforcement
# -------------------------------------------------------------------------

def per_route_limit(value: str):
    """Decorator: ``@per_route_limit(\"30/minute\")``."""
    return get_limiter().limit(value)


# -------------------------------------------------------------------------
# 429 handler — adds Retry-After + JSON body
# -------------------------------------------------------------------------

def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """JSON 429 with retry hints + standard ``Retry-After`` header."""
    retry_after = _retry_after_seconds(exc)
    limit_text = _limit_description(exc)
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "limit": limit_text,
            "retry_after_seconds": retry_after,
            "path": request.url.path,
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Limit"] = limit_text
    return response


def _limit_description(exc: RateLimitExceeded) -> str:
    """Best-effort text representation of the offending limit."""
    for attr in ("limit_str", "limit_string", "limit_text"):
        v = getattr(exc.limit, attr, None)
        if isinstance(v, str):
            return v
    inner = getattr(exc.limit, "limit", None)
    if inner is not None and hasattr(inner, "__class__"):
        return inner.__class__.__name__
    return str(getattr(exc.limit, "detail", ""))


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    try:
        window = int(getattr(exc.limit.limit, "GRANULARITY", {}).get("seconds", 60))
    except Exception:  # noqa: BLE001
        window = 60
    return max(1, window)


# -------------------------------------------------------------------------
# Middleware builders
# -------------------------------------------------------------------------

def install_slowapi(app) -> None:
    """Attach state + handler + middleware in one shot."""
    limiter = get_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


__all__ = [
    "get_limiter",
    "set_limiter",
    "per_route_limit",
    "rate_limit_exceeded_handler",
    "install_slowapi",
    "SlowAPIMiddleware",
]
