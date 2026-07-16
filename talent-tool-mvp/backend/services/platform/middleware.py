"""v8.0 T3505 — Auto-wiring service gates to all API routers.

A monkey-patch of ``FastAPI.include_router`` so every router mounted
under ``/api/`` automatically receives a ``dependencies=`` argument
that ties into ``check_service_access``.

Because ``FastAPI.include_router`` returns ``None`` and mutates the
app in place, we wrap it once at startup with a wrapper that tracks
the prefix → service name mapping and attaches the gate.

Usage in ``main.py``::

    from services.platform.middleware import install_auto_gates
    install_auto_gates(app)   # call once before any include_router()

This is opt-out per prefix by adding the prefix to ``EXEMPT_PREFIXES``.
"""
from __future__ import annotations

from typing import Iterable, Set

from fastapi import Depends, FastAPI
from fastapi.routing import APIRouter


EXEMPT_PREFIXES: Set[str] = {
    # Always-on system endpoints
    "/health",
    "/api/health",
    "/api/users/me",
    "/docs",
    "/redoc",
    "/openapi.json",
    # Admin service toggle needs to be reachable from any admin; the
    # admin-only check is enforced inside the router itself.
    "/api/admin/services",
    # Service catalog and decision endpoints; used by the catalog UI.
    "/api/public/services",
    # T6103: recruitment marketplace is public-browse (talent + job pool).
    # PII on the talent side is gated inside the router via _optional_user.
    "/api/talent-market",
}

# Internal services whose toggle is admin-only and irrelevant to runtime
# access — but we still expose the gate so admins can flip them.
INTERNAL_SERVICE_PREFIXES: Set[str] = {
    "/api/admin/services",
    "/api/admin/feature-flags",
    "/api/admin/config",
    "/api/admin/plugins",
    "/api/admin/audit",
    "/api/admin/notify",
    "/api/admin/api-keys",
    "/api/admin/cost",
    "/api/admin/matching-quality",
    "/api/admin/weights",
    "/api/admin/ab",
    "/api/legal",
    "/api/admin",
}


def service_name_for_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    p = prefix.strip().strip("/")
    if not p:
        return ""
    if p.startswith("api/"):
        p = p[len("api/"):]
    name = p.replace("/", ".").rstrip(".")
    return name or "api"


def install_auto_gates(app: FastAPI, *, exempt: Iterable[str] | None = None) -> None:
    """Wrap ``app.include_router`` so every /api/* router gets gated.

    Idempotent — call it as early as possible, ideally before mounting
    any routers. Repeated calls overwrite the wrapper but the previous
    wrapped routers stay gated (we keep an internal set so a router is
    never double-gated).
    """
    from .feature_access import check_service_access

    exempt_set = set(EXEMPT_PREFIXES)
    if exempt:
        exempt_set.update(exempt)

    seen_services: Set[str] = set()
    original = app.include_router
    wrapped = getattr(app, "_waibao_include_router", None)
    if wrapped is not None:
        original = wrapped.__wrapped__  # type: ignore[attr-defined]

    def _make_dep(service: str, sentinel_attr: str) -> Depends:
        """Create a real ``Depends`` for the gate. The sentinel is
        tracked by external dict because ``Depends`` is a frozen
        dataclass and ``setattr`` is not allowed.
        """
        return Depends(check_service_access(service))

    def _wrapped_include_router(router, *args, **kwargs):
        prefix = kwargs.get("prefix", "")
        # Skip gating for routers that own WebSocket routes: the gate dep is
        # built for HTTP ``Request`` injection and crashes (TypeError) when
        # evaluated for a WebSocket route. WS auth is enforced in-handler.
        has_websocket = any(
            getattr(r, "endpoint", None) is not None
            and "websocket" in str(getattr(r, "__class__", "")).lower()
            for r in (getattr(router, "routes", []) or [])
        ) or any(
            type(r).__name__ == "APIWebSocketRoute"
            for r in (getattr(router, "routes", []) or [])
        )
        if (
            isinstance(prefix, str)
            and prefix
            and prefix not in exempt_set
            and prefix.startswith("/api/")
            and not has_websocket
        ):
            service = service_name_for_prefix(prefix)
            if service and service not in seen_services:
                seen_services.add(service)
                existing_deps = list(kwargs.get("dependencies", []) or [])
                dep = _make_dep(service, f"_waibao_gate_{service}")
                existing_deps.append(dep)
                kwargs["dependencies"] = existing_deps
        return original(router, *args, **kwargs)

    _wrapped_include_router.__wrapped__ = original  # type: ignore[attr-defined]
    _wrapped_include_router.__name__ = original.__name__
    app.include_router = _wrapped_include_router  # type: ignore[assignment]
    app._waibao_include_router = _wrapped_include_router  # type: ignore[attr-defined]
    app._waibao_gated_services = seen_services  # type: ignore[attr-defined]


def gated_service_names(app: FastAPI) -> Set[str]:
    """Return the set of services that have been auto-gated on `app`."""
    return set(getattr(app, "_waibao_gated_services", set()) or set())


__all__ = [
    "EXEMPT_PREFIXES",
    "INTERNAL_SERVICE_PREFIXES",
    "service_name_for_prefix",
    "install_auto_gates",
    "gated_service_names",
]
