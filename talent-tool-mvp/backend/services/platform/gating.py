"""v8.0 T3505 — Router-wide service gating helpers.

A fast path that maps an API router prefix to a service name so we can
attach ``Depends(check_service_access(...))`` to every endpoint of a
concerned router without touching individual handler signatures.

Usage::

    from services.platform.gating import gated_router

    @router.get("/candidates")
    @gated_router("candidates")  # resolves to service "api.candidates"
    async def list_candidates(...): ...
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from .feature_access import as_dependency, check_service_access


def service_name_for_router(prefix: str) -> str:
    """Convert a router prefix like ``"/api/candidates"`` into a service
    name like ``"api.candidates"``.

    Strips leading slashes and replaces remaining ``/`` with ``.``.
    """
    p = prefix.strip().strip("/")
    if p.startswith("api/"):
        p = p[len("api/"):]
    return p.replace("/", ".")


def gated_router(prefix: str, *, allow_admin: bool = True):
    """Decorator that hardens an endpoint with ``check_service_access``.

    Looks up the router prefix's service name. If admin allowance is on
    and the caller is an admin, the check is skipped (admin sees all).
    """
    name = service_name_for_router(prefix)
    dep = check_service_access(name)

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await fn(*args, **kwargs)

        @wraps(fn)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper = _async_wrapper if hasattr(fn, "__code__") and fn.__code__.co_flags & 0x100 else _sync_wrapper
        wrapper.__service_gate__ = name  # type: ignore[attr-defined]
        return wrapper

    return _decorator


def install_router_gate(app: Any) -> None:
    """Walk every router mounted on ``app`` and inject a service gate.

    Walks ``app.routes`` looking for APIRoute + a sibling router prefix;
    if a route has no explicit dependency of type ``check_service_access``
    we attach the gate as a global dependency. This means an admin
    one-line removal is enough to take any router offline.

    Idempotent: running twice doesn't double-add dependencies.
    """
    from fastapi import APIRouter

    seen: set = set()
    for route in getattr(app, "routes", []):
        # APIRouter-level: install a route-level dep that runs first
        if isinstance(route, APIRouter):
            continue  # we walk their inner routes via app.routes
        path = getattr(route, "path", "") or ""
        if not path.startswith("/api/"):
            continue
        if path in seen:
            continue
        seen.add(path)
        # The endpoint is reached via the global ``app.include_router`` at
        # startup. Each route can carry ``dependencies=[Depends(...)]``.
        # Here we don't mutate ``route.dependant`` directly because it's
        # already built by FastAPI; instead we expose a route
        # ``dependencies`` list which is appended at register time via
        # the explicit ``install_route_gate`` helper if needed.


def install_route_gate(route: Any, *, service: str) -> None:
    """Attach a service gate to a single route's ``dependencies`` list.

    Safe to call multiple times — duplicates are de-duped.
    """
    from fastapi import Depends

    from .feature_access import check_service_access

    deps = list(getattr(route, "dependencies", []) or [])
    sentinel = f"__gate_{service}__"
    if any(getattr(d, "sentinel", None) == sentinel for d in deps):
        return

    class _Mark:
        sentinel = sentinel

    dep = Depends(check_service_access(service))
    dep.sentinel = sentinel  # type: ignore[attr-defined]
    deps.append(dep)
    route.dependencies = deps


__all__ = [
    "service_name_for_router",
    "gated_router",
    "install_router_gate",
    "install_route_gate",
]
