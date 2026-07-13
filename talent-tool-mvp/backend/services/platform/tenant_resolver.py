"""T2601 - Tenant resolver.

Pulls the tenant identity from a request:

  1. JWT  ``tenant_id`` claim (preferred — most trustworthy).
  2. ``X-Tenant-ID`` header (browser fallback / explicit override).
  3. ``waibao_tenant`` cookie (legacy SPA session storage).

Returns ``None`` when none of the three sources are present — the caller is
responsible for rejecting unauthenticated cross-tenant requests.

The module keeps no I/O dependencies so it can be unit-tested offline.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Mapping, Optional

from fastapi import Request

from .tenant_context import TenantContext

logger = logging.getLogger("recruittech.platform.tenant_resolver")


@dataclass(frozen=True)
class TenantResolver:
    """Ordered chain of resolver strategies."""

    cookie_name: str = "waibao_tenant"

    # ---- public API -----------------------------------------------
    def resolve(
        self,
        request: Request,
        *,
        jwt_claims: Optional[Mapping[str, object]] = None,
        plan: str = "free",
        bypass_rls: bool = False,
    ) -> Optional[TenantContext]:
        """Build a ``TenantContext`` from any combination of sources.

        Resolution order (first match wins):
            1. JWT ``tenant_id`` claim (and ``sub`` for user_id)
            2. ``X-Tenant-ID`` request header
            3. ``waibao_tenant`` cookie

        ``bypass_rls`` flips on only when the JWT's ``role`` claim is
        ``admin``/``super_admin``.
        """
        ctx = self._from_jwt(jwt_claims, plan=plan, bypass=bypass_rls)
        if ctx:
            return ctx

        ctx = self._from_header(request, plan=plan)
        if ctx:
            return ctx

        ctx = self._from_cookie(request, plan=plan)
        return ctx

    # ---- strategies -----------------------------------------------
    def _from_jwt(
        self,
        claims: Optional[Mapping[str, object]],
        *,
        plan: str,
        bypass: bool,
    ) -> Optional[TenantContext]:
        if not claims:
            return None
        tid = claims.get("tenant_id") or claims.get("organisation_id")
        if not tid:
            return None
        try:
            tenant_uuid = uuid.UUID(str(tid))
        except (ValueError, TypeError):
            logger.warning("JWT contained malformed tenant_id=%r", tid)
            return None

        sub = claims.get("sub")
        try:
            user_uuid: Optional[uuid.UUID] = uuid.UUID(str(sub)) if sub else None
        except (ValueError, TypeError):
            user_uuid = None
        role = str(claims.get("role") or claims.get("user_metadata", {}).get("role", "talent_partner"))
        impersonator = claims.get("impersonator_id")
        try:
            imp_uuid = uuid.UUID(str(impersonator)) if impersonator else None
        except (ValueError, TypeError):
            imp_uuid = None

        return TenantContext(
            tenant_id=tenant_uuid,
            user_id=user_uuid,
            role=role,
            plan=plan,
            bypass_rls=bypass or role in {"admin", "super_admin"},
            impersonator_id=imp_uuid,
        )

    def _from_header(self, request: Request, *, plan: str) -> Optional[TenantContext]:
        raw = request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-ID")
        if not raw:
            return None
        try:
            tid = uuid.UUID(raw)
        except ValueError:
            return None
        return TenantContext(
            tenant_id=tid,
            user_id=None,
            role="talent_partner",
            plan=plan,
        )

    def _from_cookie(self, request: Request, *, plan: str) -> Optional[TenantContext]:
        raw = request.cookies.get(self.cookie_name)
        if not raw:
            return None
        try:
            tid = uuid.UUID(raw)
        except ValueError:
            return None
        return TenantContext(
            tenant_id=tid,
            user_id=None,
            role="talent_partner",
            plan=plan,
        )


# -------------------------------------------------------------------------
# FastAPI dependency helpers
# -------------------------------------------------------------------------

def get_tenant_resolver() -> TenantResolver:
    """Return a process-singleton resolver.  Injected into routes."""
    return _RESOLVER


_RESOLVER = TenantResolver()


def get_tenant_context_dep(request: Request) -> TenantContext:
    """FastAPI dependency.

    Resolves the tenant and binds it to the ``ContextVar`` for the remainder
    of the request.  Raises ``403`` when no tenant can be located so
    unauthenticated requests can't accidentally hit business tables.
    """
    from fastapi import HTTPException  # local to keep dep optional

    jwt_claims = getattr(request.state, "jwt_claims", None)
    plan = str(getattr(request.state, "plan", "free"))
    bypass = bool(getattr(request.state, "bypass_rls", False))
    ctx = _RESOLVER.resolve(
        request,
        jwt_claims=jwt_claims,
        plan=plan,
        bypass_rls=bypass,
    )
    if ctx is None:
        raise HTTPException(
            status_code=403,
            detail="Tenant identity could not be resolved (missing tenant_id claim / header / cookie)",
        )
    request.state.tenant_id = ctx.tenant_id
    request.state.tenant_role = ctx.role
    request.state.tenant_plan = ctx.plan
    request.state.tenant_ctx = ctx
    from .tenant_context import set_tenant_context  # avoid cycle at import
    set_tenant_context(ctx)
    return ctx


__all__ = ["TenantResolver", "get_tenant_context_dep", "get_tenant_resolver"]
