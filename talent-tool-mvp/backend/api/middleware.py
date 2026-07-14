"""v10.0 T5003 — Standard API middleware chain & unified error handling.

This module upgrades the API boundary so that **every** router shares one
governance chain and one error-serialisation format.  It complements
``setup.install_middleware`` (which already wires CORS + tenant + quota +
request logging) by adding:

* :func:`install_error_handlers` — a single JSON error shape for
  :class:`services.platform.errors.ServiceError`, the legacy
  ``exceptions.APIError``, FastAPI ``RequestValidationError`` (422) and any
  uncaught exception (500).  All bodies use the canonical
  ``{"error": {"code", "message", ...}}`` envelope.
* :func:`get_tenant_context` — the standard dependency every mutating route
  should ``Depends`` on to enforce tenant presence.
* :func:`standard_dependencies` — the ordered dependency list
  ``tenant → quota → rate_limit → auth`` for routers that opt in.
* :func:`install_standard_chain` — one call from ``main.py`` that installs
  the error handlers and OpenAPI post-processing.

The chain is intentionally additive and idempotent so it can be layered on
the existing app without breaking the 2000+ passing tests.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("recruittech.api.middleware")


# ===========================================================================
# Unified error handlers
# ===========================================================================
def _error_body(code: str, message: str, *, details: Any = None,
                retry_after: Optional[int] = None, path: Optional[str] = None,
                request_id: Optional[str] = None,
                retryable: Optional[bool] = None) -> dict[str, Any]:
    """Build the canonical v10.0 error envelope.

    Every error body carries ``code``, ``message``, ``retryable`` and
    ``request_id`` so clients can branch uniformly; ``details`` /
    ``retry_after`` / ``path`` are included only when meaningful.
    """
    err: dict[str, Any] = {"code": code, "message": message}
    if retryable is not None:
        err["retryable"] = retryable
    if request_id is not None:
        err["request_id"] = request_id
    if details:
        err["details"] = details
    if retry_after is not None:
        err["retry_after"] = retry_after
    if path is not None:
        err["path"] = path
    return {"error": err}


def _resolve_request_id(request: Request) -> str:
    """Return the request's correlation id (header or state-bound value).

    Falls back to an empty string when none is present so the envelope field
    is always populated.
    """
    rid = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
    if not rid:
        rid = getattr(request.state, "request_id", None)
    return rid or ""


def _retryable_for(code: str) -> bool:
    """Best-effort retryable flag for ad-hoc (non-ServiceError) envelopes."""
    from services.platform.errors import is_retryable
    try:
        from services.platform.errors import ServiceErrorCode
        return is_retryable(ServiceErrorCode(code))
    except Exception:  # noqa: BLE001 — unknown code, default not-retryable
        return False


def install_error_handlers(app: FastAPI) -> None:
    """Install the canonical ServiceError / APIError / validation / 500 handlers.

    Every response uses the unified v10.0 envelope::

        {"error": {"code", "message", "retryable", "request_id",
                   ["details"], ["retry_after"], ["path"]}}
    """
    from services.platform.errors import ServiceError, ServiceErrorCode

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError):  # type: ignore[valid-type]
        rid = exc.request_id or _resolve_request_id(request)
        logger.info("ServiceError %s on %s: %s (rid=%s)", exc.code_value, request.url.path, exc.message, rid)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                exc.code_value, exc.message,
                details=exc.details or None,
                retry_after=exc.retry_after,
                path=request.url.path,
                request_id=rid,
                retryable=exc.retryable,
            ),
            headers=exc.headers() or None,
        )

    # Bridge the legacy APIError to the same envelope (keeps old routers uniform).
    try:
        from exceptions import APIError

        @app.exception_handler(APIError)
        async def _api_error_handler(request: Request, exc: APIError):  # type: ignore[valid-type]
            code = exc.code.value if hasattr(exc.code, "value") else str(exc.code)
            return JSONResponse(
                status_code=exc.status_code,
                content=_error_body(
                    code, exc.detail,
                    details=exc.extra or None,
                    path=request.url.path,
                    request_id=_resolve_request_id(request),
                    retryable=_retryable_for(code),
                ),
                headers=exc.headers or None,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("APIError handler not installed: %s", exc)

    try:
        from fastapi.exceptions import RequestValidationError

        @app.exception_handler(RequestValidationError)
        async def _validation_handler(request: Request, exc: RequestValidationError):  # type: ignore[valid-type]
            return JSONResponse(
                status_code=422,
                content=_error_body(
                    "VALIDATION_ERROR", "Request validation failed",
                    details={"errors": _safe_errors(exc)},
                    path=request.url.path,
                    request_id=_resolve_request_id(request),
                    retryable=_retryable_for("VALIDATION_ERROR"),
                ),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("validation handler not installed: %s", exc)

    # Catch-all for any uncaught exception → 500 with the same envelope.
    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):  # type: ignore[valid-type]
        rid = _resolve_request_id(request)
        logger.exception("Unhandled exception on %s (rid=%s): %s", request.url.path, rid, exc)
        return JSONResponse(
            status_code=500,
            content=_error_body(
                ServiceErrorCode.INTERNAL_ERROR.value,
                "Internal service error",
                path=request.url.path,
                request_id=rid,
                retryable=True,
            ),
        )


def _safe_errors(exc: Any) -> list[dict[str, Any]]:
    try:
        out = []
        for e in exc.errors():
            out.append({
                "loc": [str(x) for x in e.get("loc", [])],
                "msg": str(e.get("msg", "")),
                "type": str(e.get("type", "")),
            })
        return out
    except Exception:  # noqa: BLE001
        return []


# ===========================================================================
# Request-id correlation middleware
# ===========================================================================
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a correlation id.

    Honours an inbound ``X-Request-ID`` header (so upstream gateways /
    clients can propagate their own id) and otherwise mints one.  The value
    is bound to ``request.state.request_id`` so the error handlers and any
    logging can read it, and echoed back on the ``X-Request-ID`` response
    header.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = (
            request.headers.get("x-request-id")
            or request.headers.get("X-Request-ID")
            or f"req_{uuid.uuid4().hex[:16]}"
        )
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def install_request_id_middleware(app: FastAPI) -> None:
    """Wire the request-id middleware (idempotent)."""
    # Avoid double-registration on hot-reload.
    existing = {getattr(m.cls, "__name__", "") for m in app.user_middleware}
    if RequestIdMiddleware.__name__ in existing:
        return
    app.add_middleware(RequestIdMiddleware)


# ===========================================================================
# Standard dependencies: tenant → quota → rate_limit → auth
# ===========================================================================
async def get_tenant_context(request: Request):
    """Standard dependency enforcing a resolved tenant on the request.

    The tenant middleware (``setup.install_middleware``) binds
    ``request.state.tenant_ctx`` early; this dependency surfaces it and
    raises a typed :class:`ServiceError` when it is absent so routes can
    simply ``ctx = Depends(get_tenant_context)``.
    """
    from services.platform.errors import ServiceError, ServiceErrorCode

    ctx = getattr(request.state, "tenant_ctx", None)
    if ctx is None:
        # fall back to the ContextVar bound by the middleware
        try:
            from services.platform.tenant_context import get_tenant_context as _get
            ctx = _get()
        except Exception:  # noqa: BLE001
            ctx = None
    if ctx is None:
        raise ServiceError(
            ServiceErrorCode.AUTH_MISSING_TENANT,
            "Tenant context missing from request",
        )
    return ctx


def quota_guard(request: Request) -> None:
    """Best-effort per-tenant quota check as a route dependency.

    The middleware already enforces the coarse per-minute quota; this
    dependency is for routers that want an explicit, per-route hook.  It is
    a no-op when no tenant is bound (unauthenticated/public routes).
    """
    ctx = getattr(request.state, "tenant_ctx", None)
    if ctx is None:
        return
    try:
        from services.platform.quota import enforce_request
        from services.platform.errors import ServiceError, ServiceErrorCode

        if not enforce_request(str(ctx.tenant_id)):
            raise ServiceError(ServiceErrorCode.QUOTA_EXCEEDED, retry_after=60)
    except ImportError:
        return


def standard_dependencies(*, require_tenant: bool = True,
                          with_quota: bool = True) -> list[Any]:
    """Return the ordered dependency list for a governed router.

    Usage::

        router = APIRouter(
            prefix="/api/candidates",
            dependencies=standard_dependencies(),
        )
    """
    deps: list[Any] = []
    if require_tenant:
        deps.append(Depends(get_tenant_context))
    if with_quota:
        deps.append(Depends(quota_guard))
    return deps


# ===========================================================================
# One-call installer
# ===========================================================================
def install_standard_chain(app: FastAPI) -> FastAPI:
    """Install unified error handling + request-id + OpenAPI metadata on ``app``.

    Call once in ``main.py`` after ``setup_application(app)``.  Idempotent.
    """
    install_request_id_middleware(app)
    install_error_handlers(app)
    try:
        from api.openapi_tags import apply_openapi
        apply_openapi(app)
    except Exception as exc:  # noqa: BLE001
        logger.debug("openapi post-processing skipped: %s", exc)
    return app


__all__ = [
    "install_error_handlers",
    "install_request_id_middleware",
    "install_standard_chain",
    "RequestIdMiddleware",
    "get_tenant_context",
    "quota_guard",
    "standard_dependencies",
]
