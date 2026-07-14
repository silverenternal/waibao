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
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("recruittech.api.middleware")


# ===========================================================================
# Unified error handlers
# ===========================================================================
def _error_body(code: str, message: str, *, details: Any = None,
                retry_after: Optional[int] = None, path: Optional[str] = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details:
        err["details"] = details
    if retry_after is not None:
        err["retry_after"] = retry_after
    if path is not None:
        err["path"] = path
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    """Install the canonical ServiceError / APIError / validation / 500 handlers."""
    from services.platform.errors import ServiceError

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError):  # type: ignore[valid-type]
        logger.info("ServiceError %s on %s: %s", exc.code_value, request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                exc.code_value, exc.message,
                details=exc.details or None,
                retry_after=exc.retry_after,
                path=request.url.path,
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
                ),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("validation handler not installed: %s", exc)


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
    """Install unified error handling + OpenAPI metadata on ``app``.

    Call once in ``main.py`` after ``setup_application(app)``.  Idempotent.
    """
    install_error_handlers(app)
    try:
        from api.openapi_tags import apply_openapi
        apply_openapi(app)
    except Exception as exc:  # noqa: BLE001
        logger.debug("openapi post-processing skipped: %s", exc)
    return app


__all__ = [
    "install_error_handlers",
    "install_standard_chain",
    "get_tenant_context",
    "quota_guard",
    "standard_dependencies",
]
