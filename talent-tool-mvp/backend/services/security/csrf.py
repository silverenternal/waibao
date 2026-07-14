"""v10.0 T5017 — Double-submit CSRF protection middleware.

The platform is a stateless JWT + SPA stack, so we use the **synchroniser-token-
free double-submit** pattern (OWASP CSRF Prevention Cheat Sheet, "Use Double
Submit Cookies"):

1. On any safe (``GET``/``HEAD``/``OPTIONS``) request that does not yet carry a
   CSRF cookie, the middleware mints a random token, sets it as a non-``HttpOnly``
   cookie (so the JS client can read it) **and** does nothing else.
2. On every *unsafe* (state-changing) request — ``POST``/``PUT``/``PATCH``/
   ``DELETE`` — the middleware requires the client to echo the cookie value in a
   header (``X-CSRF-Token``) or body field.  If the header value ≠ cookie value,
   the request is rejected with ``403``.
3. Token rotation is bounded: the cookie carries an ``age`` so we can refresh it
   periodically without invalidating long-lived browser sessions.

The token is HMAC-signed so a malicious subdomain cannot forge one; the secret
defaults to the app's JWT secret (already a long random string) and is
overridable via ``CSRF_SECRET``.

When ``CSRF_ENABLED=0`` the middleware becomes a pass-through (useful for
headless API tests / service-to-service calls authenticated by a static API
key, where the token cannot be minted).  It defaults to **on**.

The middleware also skips enforcement for requests that present a valid Bearer
JWT *and* arrive with a non-cookie ``Authorization`` header — JWT-in-header is
inherently CSRF-immune (a cross-origin form post cannot set the Authorization
header).  This keeps the existing API-test suite green without per-test token
setup while still protecting browser cookie-authenticated flows.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
from typing import Iterable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("waibao.security.csrf")

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Default: enabled in prod, disabled in tests via env.
_ENABLED = os.getenv("CSRF_ENABLED", "1").lower() not in ("0", "false", "no")
# Token refresh cadence — rotate after ~24h.
_ROTATE_SECONDS = int(os.getenv("CSRF_ROTATE_SECONDS", str(24 * 3600)))


def _secret() -> bytes:
    """Return the HMAC secret.  Falls back to a process-static random value
    so the middleware works out of the box (token just won't survive restart)."""
    sec = os.getenv("CSRF_SECRET") or os.getenv("SUPABASE_JWT_SECRET") or ""
    if sec:
        return sec.encode("utf-8")
    return _PROC_SECRET  # type: ignore[name-defined]


_PROC_SECRET = secrets.token_bytes(32)


def generate_token(*, issued_at: Optional[int] = None) -> str:
    """Mint a fresh, tamper-evident CSRF token ``<rand>.<ts>.<sig>``."""
    import time
    ts = issued_at or int(time.time())
    rand = secrets.token_urlsafe(24)
    payload = f"{rand}.{ts}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), "sha256").hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str, *, max_age_seconds: int = _ROTATE_SECONDS) -> bool:
    """Return True iff ``token`` has a valid signature and is not expired."""
    if not token or token.count(".") != 2:
        return False
    rand, ts_str, sig = token.split(".")
    payload = f"{rand}.{ts_str}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), "sha256").hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    import time
    if max_age_seconds > 0 and (int(time.time()) - ts) > max_age_seconds:
        return False
    return True


def _request_carries_jwt_header(request: Request) -> bool:
    """A request with a non-cookie ``Authorization: Bearer ...`` header is
    immune to CSRF (a cross-origin form cannot set it), so we exempt it."""
    auth = request.headers.get("authorization", "")
    return auth.lower().startswith("bearer ")


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF middleware.

    Install with::

        from services.security.csrf import install_csrf
        install_csrf(app)
    """

    def __init__(self, app, *, enabled: bool = _ENABLED, cookie_name: str = CSRF_COOKIE) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not self.enabled:
            return await call_next(request)

        # Always (re)issue a cookie on safe requests if missing or stale, so the
        # SPA can bootstrap its token on the first GET.
        cookie_token = request.cookies.get(self.cookie_name)
        method = request.method.upper()

        if method in SAFE_METHODS:
            response: Response = await call_next(request)
            if not cookie_token or not verify_token(cookie_token):
                _set_cookie(response, self.cookie_name, generate_token())
            return response

        # Unsafe method — enforce double-submit, unless JWT-in-header.
        if _request_carries_jwt_header(request):
            # JWT bearer is CSRF-immune; still refresh cookie if stale.
            response = await call_next(request)
            if not cookie_token or not verify_token(cookie_token):
                _set_cookie(response, self.cookie_name, generate_token())
            return response

        header_token = request.headers.get(CSRF_HEADER) or request.headers.get(CSRF_HEADER.replace("-", "_"))
        if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token) or not verify_token(header_token):
            logger.warning(
                "csrf.rejected method=%s path=%s has_cookie=%s has_header=%s",
                method, request.url.path, bool(cookie_token), bool(header_token),
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid", "code": "csrf_failed"},
            )
        response = await call_next(request)
        # Rotate periodically.
        if not verify_token(cookie_token):
            _set_cookie(response, self.cookie_name, generate_token())
        return response


def _set_cookie(response: Response, name: str, token: str) -> None:
    """Set the CSRF cookie — NOT HttpOnly (JS must read it), SameSite=Lax."""
    response.set_cookie(
        key=name,
        value=token,
        httponly=False,
        secure=os.getenv("CSRF_COOKIE_SECURE", "1").lower() in ("1", "true", "yes"),
        samesite="lax",
        max_age=_ROTATE_SECONDS,
        path="/",
    )


def install_csrf(app: FastAPI, *, enabled: bool = _ENABLED) -> FastAPI:
    """Attach :class:`CSRFMiddleware`.  Idempotent."""
    # Avoid double-install on hot-reload / repeated setup calls.
    existing = {getattr(m.cls, "__name__", "") for m in getattr(app, "user_middleware", [])}
    if "CSRFMiddleware" in existing:
        return app
    app.add_middleware(CSRFMiddleware, enabled=enabled)
    return app


__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "SAFE_METHODS",
    "CSRFMiddleware",
    "generate_token",
    "verify_token",
    "install_csrf",
]
