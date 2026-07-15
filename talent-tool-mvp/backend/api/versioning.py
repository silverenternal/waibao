"""API versioning facade — T2904.

Implements:
* Mount the existing routers under ``/api/v1/*`` (legacy/canonical)
* Provide a parallel ``/api/v2/*`` namespace where new features /
  refactors land.
* Add an HTTP middleware that maps ``/api/<path>`` -> ``/api/v1/<path>``
  with a 301/308 redirect, preserving query strings.
* Emit RFC 8594 ``Sunset`` + ``Deprecation`` + ``X-API-Deprecated`` headers
  on responses served from deprecated versions.
* Single source of truth via :data:`VERSION_REGISTRY`.

Usage in ``main.py``::

    from api.versioning import install_versioning
    install_versioning(app)

When the v1 router collection is moved into ``api/v1/__init__.py`` the
v1 namespace is automatically populated by an import side-effect.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

from fastapi import FastAPI, Request
from fastapi.routing import APIRouter
from starlette.responses import RedirectResponse

logger = logging.getLogger("recruittech.versioning")


# ---------------------------------------------------------------------------
# Version metadata
# ---------------------------------------------------------------------------

CURRENT_VERSION = "v1"
NEXT_VERSION = "v2"


@dataclass(slots=True)
class VersionSpec:
    """Per-version metadata.

    Attributes:
        version:    ``v1`` / ``v2`` / etc.
        status:     ``"current"`` / ``"deprecated"`` / ``"sunset"``.
        sunset_at:  Optional ISO date when the version is retired.
        successor:  Recommended replacement version (``v2`` for v1 etc).
        router_module: Python path to the package exposing ``router``.
    """

    version: str
    status: str = "current"
    sunset_at: str | None = None
    successor: str | None = None
    router_module: str = ""
    routers: list[APIRouter] = field(default_factory=list)

    @property
    def deprecated(self) -> bool:
        return self.status in {"deprecated", "sunset"}

    def headers(self) -> dict[str, str]:
        out: dict[str, str] = {"X-API-Version": self.version}
        if self.deprecated:
            out["X-API-Deprecated"] = "true"
            out["Deprecation"] = "true"  # RFC 9745
            if self.sunset_at:
                # RFC 8594: Sunset header
                out["Sunset"] = self.sunset_at
            if self.successor:
                out["Link"] = (
                    f'</api/{self.successor}>; rel="successor-version"'
                )
                out["X-API-Successor-Version"] = self.successor
        return out


# ---------------------------------------------------------------------------
# Version registry
# ---------------------------------------------------------------------------

VERSION_REGISTRY: dict[str, VersionSpec] = {
    "v1": VersionSpec(
        version="v1",
        status="deprecated",
        sunset_at="2027-01-01T00:00:00Z",
        successor="v2",
        router_module="api.v1",
    ),
    "v2": VersionSpec(
        version="v2",
        status="current",
        successor="v2",
        router_module="api.v2",
    ),
}

# Routes that should NEVER be redirected (system / already-versioned).
# Each entry is matched as a complete path OR ``<prefix>/...``.
NEVER_REDIRECT_PREFIXES = (
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1",
    "/api/v2",
    "/api/developer",  # developer portal owns its own versioning
    # v8.1 fix: routers mounted at legacy /api/<x>/... that are NOT in the
    # v1 namespace.  Sending them through /api/v1/... gives 404 because
    # only the curated routers in api/v1/__init__.py are mounted there.
    "/api/auth",       # wechat mini-program + SSO + JWT
    "/api/uploads",    # signed-URL upload service (legacy mount)
    "/api/realtime",   # realtime v1 websocket (separate namespace)
    "/api/realtime-v2",
    "/api/webhooks",
    "/api/calendar",
    "/api/push",       # push engine
    "/api/billing",
    "/api/bff",
    "/api/notify",
    "/api/notifications",
    "/api/onboarding",
    "/api/insights",
    "/api/pilot",
    "/api/learning",
    "/api/rediscovery",
    "/api/discovery",
    "/api/recommendations",
    "/api/marketplace",
    "/api/talent-market",  # T6103 recruitment marketplace (talent + job pool)
    "/api/hr-assistant",   # T6108 HR assistant (resume compare + interview questions)
    "/api/recruitment",    # T6109 recruitment flow (contact logs + interview schedule)
    "/api/feature-flags",
    "/api/feature_flags",
    "/api/admin/feature",
    "/api/admin/plugins",
    "/api/admin/services",
    "/api/admin/ab",
    "/api/admin/audit",
    "/api/admin/notifications",
    "/api/admin/config",
    "/api/admin/notify",
    "/api/admin/cost",
    "/api/admin/weights",
    "/api/admin/matching-quality",
    "/api/admin/matching_quality",
    "/api/public",
)


def _is_never_redirect(path: str) -> bool:
    """Segment-aware prefix check: ``/api/version`` matches
    ``/api/version-info`` only when both are bound by the rule.  We
    match exact path or ``<prefix>/...`` but never a prefix substring
    that does not share the segment boundary.
    """
    for pfx in NEVER_REDIRECT_PREFIXES:
        if path == pfx or path.startswith(pfx + "/"):
            return True
    return False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def install_versioning(app: FastAPI) -> None:
    """Mount both ``/api/v1/...`` and ``/api/v2/...`` and install the
    legacy ``/api/...`` -> ``/api/v1/...`` redirect middleware.

    Idempotent — calling twice is safe (the second call skips the
    middleware install).
    """
    if getattr(app.state, "_versioning_installed", False):
        return

    _ensure_routers_loaded()
    _mount_version_routers(app)
    _install_deprecation_middleware(app)
    _install_legacy_redirect_middleware(app)

    app.state._versioning_installed = True
    logger.info(
        "API versioning installed: %s",
        {v: spec.status for v, spec in VERSION_REGISTRY.items()},
    )


def get_version_for_path(path: str) -> str | None:
    """Return the version segment (e.g. ``v1``) if ``path`` carries one."""
    m = re.match(r"^/api/(v\d+)(/|$)", path)
    return m.group(1) if m else None


def current_version() -> str:
    for v, spec in VERSION_REGISTRY.items():
        if spec.status == "current":
            return v
    return CURRENT_VERSION


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _ensure_routers_loaded() -> None:
    """Best-effort import of v1 + v2 router namespaces.

    v2 may not exist yet — we tolerate ImportError and only mount the
    ones that import successfully.
    """
    for key, spec in VERSION_REGISTRY.items():
        if spec.routers:
            continue  # already populated (manual injection in tests)
        try:
            mod = __import__(spec.router_module, fromlist=["router"])
        except Exception as exc:  # noqa: BLE001
            logger.info("version %s has no router package yet: %s", key, exc)
            continue
        router = getattr(mod, "router", None)
        if router is None:
            continue
        if isinstance(router, Iterable):
            for r in router:
                if isinstance(r, APIRouter):
                    spec.routers.append(r)
        elif isinstance(router, APIRouter):
            spec.routers.append(router)


def _mount_version_routers(app: FastAPI) -> None:
    """Mount v1 + v2 routers under their respective prefixes.

    Existing routers (registered before this is called) keep their
    ``/api/...`` paths — we add deprecation headers at response time.
    """
    for key, spec in VERSION_REGISTRY.items():
        for router in spec.routers:
            try:
                app.include_router(router, prefix=f"/api/{key}")
                logger.info("mounted router under /api/%s", key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("mount /api/%s failed: %s", key, exc)


def _install_deprecation_middleware(app: FastAPI) -> None:
    """Tag every response that originates from a deprecated version."""
    @app.middleware("http")
    async def _deprecation_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ):
        response = await call_next(request)
        version = get_version_for_path(request.url.path)
        if version and version in VERSION_REGISTRY:
            spec = VERSION_REGISTRY[version]
            for header, value in spec.headers().items():
                if header not in response.headers:
                    response.headers[header] = value
        return response


def _install_legacy_redirect_middleware(app: FastAPI) -> None:
    """Redirect ``/api/<x>`` -> ``/api/v1/<x>`` (308 = permanent, method preserved)."""

    def _should_redirect(path: str) -> bool:
        if not path.startswith("/api/"):
            return False
        if _is_never_redirect(path):
            return False
        # Skip nested versioned paths
        if re.match(r"^/api/v\d+(/|$)", path):
            return False
        return True

    @app.middleware("http")
    async def _legacy_redirect_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ):
        if _should_redirect(request.url.path):
            qs = request.url.query
            target = f"/api/v1{request.url.path[len('/api'):]}"
            target += f"?{qs}" if qs else ""
            return RedirectResponse(url=target, status_code=308)
        return await call_next(request)


# ---------------------------------------------------------------------------
# Versioned subpackage init shims
# ---------------------------------------------------------------------------
#
# The legacy ``api/*.py`` modules remain the single source of truth for
# the canonical behaviour.  v1 simply re-exports them under a stable
# name so that ``app.include_router(v1.router)`` works.  v2 lives in
# ``api/v2/`` and is where *new* endpoints / refactors land.

# `api/v1/__init__.py` and `api/v2/__init__.py` are concrete files in
# the repository; this module only consumes their `router` attribute.
