"""API v2 namespace — T2904.

v2 is the **recommended** target for new integrations.  It carries:

* Refactored endpoints from v1 that adopted stricter contracts, better
  error envelopes, or RFC 7807 ``application/problem+json`` responses.
* New platform surfaces (e.g. the T2902 Developer Portal is exposed
  under ``/api/developer/...`` and back-compatible with both versions).
* A :func:`VersionMeta` endpoint that surfaces the version registry so
  client SDKs can discover the currently recommended version.

This module exposes a single ``router`` (FastAPI ``APIRouter``) that
unifies everything under ``/api/v2/*``.  ``api.versioning`` mounts it
automatically.

Existing v2 modules in the canonical ``api/`` directory (e.g.
``api.gdpr_v2``, ``api.analytics_v2``, ``api.realtime_v2``,
``api.ai_interview_v2``) are **re-mounted** under ``/api/v2`` instead
of their original ``/api/<x>-v2/`` prefixes; this keeps the URL
hierarchy tidy without breaking the underlying code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("recruittech.v2")

router = APIRouter(tags=["api-v2"])


# ---------------------------------------------------------------------------
# Version metadata + introspection
# ---------------------------------------------------------------------------


class VersionInfo(BaseModel):
    version: str
    status: str
    sunset_at: str | None = None
    successor: str | None = None
    is_recommended: bool


class VersionManifest(BaseModel):
    current: str
    recommended: str
    deprecated: list[str]
    sunset_iso: str
    versions: list[VersionInfo]


@router.get("/version", response_model=VersionManifest)
async def version_manifest() -> VersionManifest:
    """Surface the version registry so SDKs can pick the right target.

    Returns ``X-API-Version: v2`` automatically (added by the
    deprecation middleware).
    """
    # Import here to avoid an import cycle at module load time.
    from api.versioning import VERSION_REGISTRY, current_version

    recommended = current_version()
    deprecated = [
        v for v, spec in VERSION_REGISTRY.items() if spec.status != "current"
    ]
    return VersionManifest(
        current=recommended,
        recommended=recommended,
        deprecated=deprecated,
        sunset_iso=datetime.now(tz=timezone.utc).isoformat(),
        versions=[
            VersionInfo(
                version=v,
                status=spec.status,
                sunset_at=spec.sunset_at,
                successor=spec.successor,
                is_recommended=(v == recommended),
            )
            for v, spec in VERSION_REGISTRY.items()
        ],
    )


# ---------------------------------------------------------------------------
# Re-export the existing v2-flavored routers as canonical v2 endpoints.
# We register them without their original prefixes so the v2 namespace
# owns the URL.
# ---------------------------------------------------------------------------


def _include(r: APIRouter, prefixes_to_strip: tuple[str, ...] = ()) -> APIRouter:
    """Make a copy of the router's routes with adjusted prefixes so they
    live cleanly under ``/api/v2``.

    Routers imported below already carry their legacy prefixes
    (``/api/gdpr-v2``, ``/api/analytics-v2`` …) — when mounted under
    ``/api/v2`` the URL would be ``/api/v2/api/gdpr-v2/...`` which is
    wrong.  We rebuild the routes so the final prefix is exactly
    ``/api/v2``.
    """
    out = APIRouter()
    for route in r.routes:
        path = route.path
        for pfx in prefixes_to_strip:
            if path.startswith(pfx):
                path = path[len(pfx):]
                break
        if not path.startswith("/"):
            path = "/" + path
        # Re-attach using FastAPI's add_api_route via transfer.
        try:
            out.add_api_route(
                path,
                route.endpoint,
                methods=list(route.methods or []),
                response_model=getattr(route, "response_model", None),
                name=route.name,
            )
        except Exception:  # noqa: BLE001
            # Skip duplicate/malformed routes silently — VersionManifest always wins.
            logger.debug("skip route %s in v2 re-mount: %s", path, route.name)
    return out


# ---------------------------------------------------------------------------
# Compose v2 router set
# ---------------------------------------------------------------------------

# New developer portal (T2902) — also re-exposed under v2
try:
    from api.developer_portal import router as developer_portal_router
    # The developer portal router already has /api/developer prefix; strip it
    r = APIRouter()
    for route in developer_portal_router.routes:
        new_path = route.path
        if new_path.startswith("/api/developer"):
            new_path = new_path[len("/api/developer"):]
        if not new_path.startswith("/"):
            new_path = "/" + new_path
        try:
            r.add_api_route(
                new_path or "/",
                route.endpoint,
                methods=list(route.methods or []),
                name=route.name,
            )
        except Exception:  # noqa: BLE001
            logger.debug("skip developer route %s", route.name)
    router.include_router(r, prefix="/developer")
except Exception as exc:  # noqa: BLE001
    logger.info("developer portal not re-mounted under v2: %s", exc)

# Existing v2-flavored canonical modules
_v2_specs: list[tuple[str, tuple[str, ...]]] = [
    ("api.gdpr_v2", ("/api/gdpr-v2",)),
    ("api.analytics_v2", ("/api/analytics-v2",)),
    ("api.realtime_v2", ()),
    ("api.ai_interview_v2", ()),
]


def _register_v2_modules() -> None:
    for mod_name, strip in _v2_specs:
        try:
            mod = __import__(mod_name, fromlist=["router"])
            v2_router = mod.router  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.info("v2 module %s unavailable: %s", mod_name, exc)
            continue
        rebuilt = _include(v2_router, strip)
        # Each module becomes a v2 sub-prefix so URLs stay ordered:
        #   /api/v2/gdpr/...
        #   /api/v2/analytics/...
        #   /api/v2/realtime/...
        #   /api/v2/ai-interview/...
        slug = mod_name.split(".")[-1].replace("_v2", "").replace("_", "-")
        router.include_router(rebuilt, prefix=f"/{slug}")


_register_v2_modules()

__all__ = ["router"]
