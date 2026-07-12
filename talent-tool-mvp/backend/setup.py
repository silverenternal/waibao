"""Application setup & central initialization (T1606).

Consolidates lifespan startup/shutdown, telemetry, middleware and exception
handlers into one entry point so that `main.py` only wires the FastAPI app
together.  Keeping a single `setup_application(app)` callable makes the
order of operations deterministic and easy to test.

Importing this module is side-effect free; only calling
``setup_application(app)`` will mutate the app instance.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings

logger = logging.getLogger("recruittech.setup")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events for the Mothership API.

    Order matters:
    1. ``init_adapters`` — register CRM/ATS adapters (mocked in dev)
    2. ``init_all_agents`` — register 16 agents (P0 infra)
    Any failure is logged but never blocks startup (graceful degradation).
    """
    logger.info("RecruitTech API starting up")

    try:
        from adapters.registry import init_adapters
        init_adapters()
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_adapters failed: %s", exc)

    try:
        from api.deps import get_supabase_admin
        from agents.boot import init_all_agents
        init_all_agents(supabase=get_supabase_admin())
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_all_agents failed: %s", exc)

    try:
        yield
    finally:
        logger.info("RecruitTech API shutting down")


# ---------------------------------------------------------------------------
# Telemetry / Sentry / Metrics
# ---------------------------------------------------------------------------

def init_observability() -> None:
    """Best-effort init for OTel + Sentry + Prometheus metrics."""
    try:
        from services.telemetry import init_telemetry
        init_telemetry(service_name="waibao-backend")
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_telemetry skipped: %s", exc)

    try:
        from services.sentry import init_sentry
        init_sentry()
    except Exception as exc:  # noqa: BLE001
        logger.warning("init_sentry skipped: %s", exc)


def instrument_app(app: FastAPI) -> None:
    """Attach OTel FastAPI instrumentation and Prometheus /metrics endpoint."""
    try:
        from services.telemetry import instrument_app as _otel_instrument_app
        _otel_instrument_app(app)
    except Exception as exc:  # noqa: BLE001
        logger.warning("otel instrument_app skipped: %s", exc)

    try:
        from services.metrics import metrics_asgi_app
        metrics_app = metrics_asgi_app()
        if metrics_app is not None:
            app.mount("/metrics", metrics_app)
            logger.info("metrics endpoint mounted at /metrics")
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics mount skipped: %s", exc)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def install_middleware(app: FastAPI) -> None:
    """Install CORS + request logging middleware in canonical order."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Any]]):
        request_id = str(uuid.uuid4())[:8]
        start = time.time()
        logger.info("[%s] %s %s started", request_id, request.method, request.url.path)
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "[%s] %s %s completed %s in %.1fms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

def install_exception_handlers(app: FastAPI) -> None:
    """Install centralised JSON exception handlers.

    Order: APIError (custom) → FastAPI 422 / 404 / 500 defaults.
    """

    from exceptions import APIError

    @app.exception_handler(APIError)
    async def api_error_handler(_: Request, exc: APIError):  # type: ignore[valid-type]
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": exc.code.value if hasattr(exc.code, "value") else str(exc.code),
                "path": _.url.path,
            },
            headers=exc.headers or None,
        )

    @app.exception_handler(422)
    async def validation_error_handler(request: Request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation error", "path": request.url.path},
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return JSONResponse(
            status_code=404,
            content={"detail": "Resource not found", "path": request.url.path},
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        logger.error("Internal error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def setup_application(
    app: FastAPI,
    *,
    with_middleware: bool = True,
    with_handlers: bool = True,
) -> FastAPI:
    """Centralised app setup. Returns the same instance for chaining.

    Usage::

        app = FastAPI(lifespan=lifespan)
        setup_application(app)

    Parameters
    ----------
    app:
        The FastAPI app to configure.
    with_middleware:
        Install CORS + request logging middleware.
    with_handlers:
        Install centralised exception handlers (APIError, 422, 404, 500).
    """
    if with_middleware:
        install_middleware(app)
    if with_handlers:
        install_exception_handlers(app)
    instrument_app(app)
    return app