"""v8.0 T3503 — Feature Access (3-layer integration).

Public surface::

    check(name, org_id, plan, role, user_id) -> bool
    batch_check(names, ...) -> Dict[name, bool]
    require(name, ...) -> None                 # raises on deny
    as_dependency(name) -> Callable            # FastAPI dep returning bool
    check_service_access(name) -> Callable     # FastAPI dep raising 403
    check_context(name, **kw) -> bool          # imperative helper for agents
    guard(name)                                # decorator

The three layers (in evaluated order, any one can deny):

    1. **Config Center**   — runtime per-tenant tunables (set/get KV)
    2. **Service Toggle**  — global status + plan + role + per-org override
    3. **Feature Flag**    — v6.0 rollout / cohort / experiment gating

If any one layer blocks, the request is denied. Cache TTL is 60 s (set
in service_toggle); the other layers keep their own TTLs.

See ``docs/v8/SERVICE_VS_FLAG.md`` for guidance on which layer to pick.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("recruittech.platform.feature_access")


def check(
    name: str,
    org_id: Optional[str],
    plan: str = "free",
    role: str = "",
    user_id: Optional[str] = None,
) -> bool:
    """Return True iff every layer says the feature is reachable."""
    # Layer A: config center may explicitly disable by tenant
    try:
        from services.platform.config_service import get as cfg_get

        cfg_block = cfg_get("service_toggle", name, default=None)
        if isinstance(cfg_block, bool) and cfg_block is False:
            return False
    except Exception as exc:  # pragma: no cover
        logger.debug("feature_access config layer skipped: %s", exc)

    # Layer B: service toggle (primary)
    try:
        from services.platform.service_toggle import service_toggle

        if not service_toggle.is_enabled(name, org_id, plan, role):
            return False
    except Exception as exc:
        logger.warning("feature_access service_toggle failed: %s", exc)
        return False

    # Layer C: feature flag rollout / cohort
    try:
        from services.platform.feature_flag import is_enabled as ff_enabled, get_flag

        # If a flag named after `name` exists, it must also be enabled for
        # this user. Missing flag => assume on (don't gate on absence).
        flag = None
        try:
            flag = get_flag(name)
        except Exception:
            flag = None
        if flag is not None:
            decision = ff_enabled(name, user_id=user_id, org_id=org_id)
            if decision is False:
                return False
    except Exception as exc:  # pragma: no cover
        logger.debug("feature_access feature_flag layer skipped: %s", exc)

    return True


def require(
    name: str,
    org_id: Optional[str],
    plan: str = "free",
    role: str = "",
    user_id: Optional[str] = None,
) -> None:
    """Raise PermissionError-style exception when denied."""
    if not check(name, org_id, plan, role, user_id):
        raise PermissionError(f"Service {name!r} is not available for this context")


# ---------------------------------------------------------------------------
# Batch evaluation (T3503)
# ---------------------------------------------------------------------------
def batch_check(
    names: Iterable[str],
    org_id: Optional[str],
    plan: str = "free",
    role: str = "",
    user_id: Optional[str] = None,
) -> Dict[str, bool]:
    """Evaluate a batch of service names; returns ``{name: bool}``.

    Config Center and Feature Flag lookups are batched to amortize import
    cost. Service Toggle remains per-call (each service has its own
    Supabase row + cache key) but is cheap.
    """
    name_list = list(names)
    config_ok = _config_batch_ok(name_list, org_id)
    flag_ok = _flag_batch_ok(name_list, user_id=user_id, org_id=org_id)
    out: Dict[str, bool] = {}
    for name in name_list:
        if not config_ok.get(name, True):
            out[name] = False
            continue
        if not _service_layer_ok(name, org_id, plan, role):
            out[name] = False
            continue
        if not flag_ok.get(name, True):
            out[name] = False
            continue
        out[name] = True
    return out


def _config_batch_ok(names: List[str], org_id: Optional[str]) -> Dict[str, bool]:
    try:
        from services.platform.config_service import get as cfg_get

        out: Dict[str, bool] = {}
        for n in names:
            block = cfg_get("service_toggle", n, default=None)
            out[n] = not (isinstance(block, bool) and block is False)
        if org_id:
            for n in names:
                tenant_block = cfg_get("service_toggle", f"{org_id}:{n}", default=None)
                if isinstance(tenant_block, bool) and tenant_block is False:
                    out[n] = False
        return out
    except Exception:
        return {n: True for n in names}


def _service_layer_ok(
    name: str,
    org_id: Optional[str],
    plan: str,
    role: str,
) -> bool:
    """Single check against the service_toggle primary layer."""
    try:
        from services.platform.service_toggle import service_toggle

        return bool(service_toggle.is_enabled(name, org_id, plan, role))
    except Exception:
        return False


def _flag_batch_ok(
    names: List[str], *, user_id: Optional[str], org_id: Optional[str]
) -> Dict[str, bool]:
    try:
        from services.platform.feature_flag import get_flag, is_enabled as ff_enabled

        out: Dict[str, bool] = {}
        for n in names:
            flag = None
            try:
                flag = get_flag(n)
            except Exception:
                flag = None
            if flag is None:
                out[n] = True
                continue
            try:
                out[n] = bool(ff_enabled(n, user_id=user_id, org_id=org_id))
            except Exception:
                out[n] = True
        return out
    except Exception:
        return {n: True for n in names}


# ---------------------------------------------------------------------------
# Cache invalidation helper — delegates to the service_toggle cache so a
# single call clears the primary layer's local + Redis caches.
# ---------------------------------------------------------------------------
def invalidate_cache(prefix: Optional[str] = None) -> None:
    try:
        from services.platform import service_toggle as _st

        _st.invalidate_cache(prefix)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Imperative / decorator helpers (T3503) — for agents + services
# ---------------------------------------------------------------------------
def check_context(
    name: str,
    *,
    org_id: Optional[str] = None,
    plan: str = "free",
    role: str = "",
    user_id: Optional[str] = None,
) -> bool:
    """Functional helper for non-HTTP call sites (agents, batch jobs)."""
    return check(name, org_id, plan=plan, role=role, user_id=user_id)


def guard(name: str, *, fallback_message: str = ""):
    """Decorator that wraps a callable, raising ``PermissionError`` on deny.

    Looks for ``ctx`` (kwarg or first positional arg) and reads
    ``org_id`` / ``plan`` / ``role`` / ``user_id`` attributes from it.
    """

    def _decorator(fn):
        import functools
        import inspect

        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            _ctx = kwargs.get("ctx") or (args[0] if args else None)
            if not check(
                name,
                org_id=getattr(_ctx, "org_id", None),
                plan=getattr(_ctx, "plan", "free"),
                role=getattr(_ctx, "role", ""),
                user_id=getattr(_ctx, "user_id", None),
            ):
                raise PermissionError(
                    fallback_message or f"service {name!r} is not available"
                )
            return await fn(*args, **kwargs)

        @functools.wraps(fn)
        def _sync_wrapper(*args, **kwargs):
            _ctx = kwargs.get("ctx") or (args[0] if args else None)
            if not check(
                name,
                org_id=getattr(_ctx, "org_id", None),
                plan=getattr(_ctx, "plan", "free"),
                role=getattr(_ctx, "role", ""),
                user_id=getattr(_ctx, "user_id", None),
            ):
                raise PermissionError(
                    fallback_message or f"service {name!r} is not available"
                )
            return fn(*args, **kwargs)

        return _async_wrapper if inspect.iscoroutinefunction(fn) else _sync_wrapper

    return _decorator


# ---------------------------------------------------------------------------
# FastAPI dependency helpers (T3503)
# ---------------------------------------------------------------------------
def _extract_request_context(request: Any) -> Dict[str, Any]:
    headers = getattr(request, "headers", {}) or {}
    return {
        "org_id": headers.get("X-Org-Id") or None,
        "role": headers.get("X-Role") or "",
        "user_id": headers.get("X-User-Id") or None,
        "plan": headers.get("X-Plan") or "free",
    }


def as_dependency(name: str):
    """Build a FastAPI Depends()-able that returns True/False.

    Usage::

        from services.platform.feature_access import as_dependency

        @app.get("/api/foo")
        async def foo(enabled: bool = Depends(as_dependency("api.foo"))):
            ...
    """
    from fastapi import Request

    def _dep(request: Request) -> bool:
        ctx = _extract_request_context(request)
        return check(name, **ctx)

    return _dep


def check_service_access(name: str):
    """FastAPI dependency that 403s when the service is disabled.

    Drop into any API endpoint::

        @app.get("/api/foo")
        async def foo(_: None = Depends(check_service_access("api.foo"))):
            ...
    """
    from fastapi import HTTPException, Request

    def _dep(request: Request) -> None:
        ctx = _extract_request_context(request)
        if not check(name, **ctx):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "service_disabled",
                    "service": name,
                    "message": f"Service {name!r} is currently disabled",
                },
            )

    return _dep
