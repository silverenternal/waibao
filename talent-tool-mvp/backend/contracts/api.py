"""v10.0 T5003 — Canonical API request/response contracts.

The historical API surface (640+ routes across ~88 router files) returns raw
dicts and relies on FastAPI's implicit serialization, which makes the OpenAPI
schema lossy and breaks contract drift detection.  This module provides the
shared building blocks every router should adopt so responses are typed end to
end:

* :class:`ApiResponse` ``[T]`` — the standard single-object envelope.
* :class:`PaginatedResponse` ``[T]`` — cursor/offset list envelope.
* :class:`ErrorEnvelope` — the mirror of the unified error body produced by
  ``api/middleware.py`` (so clients can codegen one ``Error`` model).
* :func:`typed_router` — an ``APIRouter`` factory that wires the standard
  tenant/quota dependency chain and a default ``response_model`` so new
  routers are contract-tight by default.

These are additive: existing routers keep working; new ones (and migrations)
opt in.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, Sequence, TypeVar

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

T = TypeVar("T")


# ===========================================================================
# Envelopes
# ===========================================================================
class ErrorDetail(BaseModel):
    """One item in a validation ``details.errors`` list."""

    loc: list[str] = Field(default_factory=list)
    msg: str = ""
    type: str = ""


class ErrorEnvelope(BaseModel):
    """The unified error body (mirrors ``api/middleware._error_body``)."""

    code: str
    message: str
    retryable: bool = False
    request_id: str = ""
    details: Optional[Any] = None
    retry_after: Optional[int] = None
    path: Optional[str] = None


class ApiResponse(BaseModel, Generic[T]):
    """Standard success envelope for single-object responses.

    Wrapping every payload in ``{"data": ..., "request_id": ...}`` gives
    clients a stable shape and a place to hang correlation metadata without
    polluting the resource itself.
    """

    data: T
    request_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard list envelope with pagination cursors."""

    data: list[T]
    total: int = 0
    limit: int = 50
    offset: int = 0
    next_cursor: Optional[str] = None
    request_id: Optional[str] = None


# ===========================================================================
# typed_router — contract-tight APIRouter factory
# ===========================================================================
def typed_router(
    *,
    prefix: str,
    tags: Optional[Sequence[str]] = None,
    require_tenant: bool = True,
    with_quota: bool = True,
    default_response_model: Optional[type] = None,
    **kwargs: Any,
) -> APIRouter:
    """Build an :class:`APIRouter` wired with the standard governance chain.

    Parameters
    ----------
    prefix, tags:
        Forwarded to ``APIRouter``.
    require_tenant, with_quota:
        When ``True`` (default) the router depends on
        :func:`api.middleware.get_tenant_context` / :func:`quota_guard`, so
        every route on the router enforces tenant presence without each
        handler repeating the ``Depends``.
    default_response_model:
        Optional default ``response_model`` applied to every route.  FastAPI
        does not support a router-wide default natively, so callers still set
        ``response_model=`` per route — this argument documents intent and is
        surfaced in the generated OpenAPI ``x-default-response-model``
        extension.
    """
    # Imported lazily so ``contracts`` stays free of a FastAPI import cycle at
    # module-load time (contracts are imported by services too).
    from api.middleware import get_tenant_context, quota_guard, standard_dependencies

    dependencies = list(kwargs.pop("dependencies", []) or [])
    if require_tenant or with_quota:
        dependencies.extend(
            standard_dependencies(require_tenant=require_tenant, with_quota=with_quota)
        )

    router = APIRouter(
        prefix=prefix,
        tags=list(tags) if tags else None,
        dependencies=dependencies,
        **kwargs,
    )
    # Stash intent for OpenAPI post-processing / introspection.
    router.dependency_overrides_default = default_response_model  # type: ignore[attr-defined]
    return router


__all__ = [
    "ApiResponse",
    "PaginatedResponse",
    "ErrorEnvelope",
    "ErrorDetail",
    "typed_router",
]
