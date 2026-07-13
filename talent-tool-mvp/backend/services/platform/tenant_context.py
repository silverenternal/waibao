"""T2601 - Tenant context primitives.

``TenantContext`` is the in-process representation of "which tenant is the
caller acting as".  It is stored in a ``ContextVar`` so async tasks, thread
pools and BackgroundTasks all share the same identity without us having to
plumb it through every function signature.

The context layer is intentionally tiny — it does NOT know how a tenant
was resolved, only what was resolved.  The actual resolution (JWT,
``X-Tenant-ID`` header, cookie) lives in ``tenant_resolver.py``.

Example
-------
>>> from services.platform.tenant_context import with_tenant, get_tenant
>>> with with_tenant(uuid4(), uuid4(), "admin") as ctx:
...     assert get_tenant() is ctx
"""
from __future__ import annotations

import contextlib
import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator, Optional

logger = logging.getLogger("recruittech.platform.tenant")


@dataclass(frozen=True)
class TenantContext:
    """Immutable tenant identity for the current request / task."""

    tenant_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    role: str = "talent_partner"
    plan: str = "free"
    """Sub-tenant impersonation, kept for the operator tooling."""
    impersonator_id: Optional[uuid.UUID] = None
    """When ``True`` the bearer bypasses RLS via ``app.bypass_rls=on``."""
    bypass_rls: bool = False

    # Convenience ----------------------------------------------------
    def as_dict(self) -> dict:
        return {
            "tenant_id": str(self.tenant_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "role": self.role,
            "plan": self.plan,
            "impersonator_id": str(self.impersonator_id) if self.impersonator_id else None,
            "bypass_rls": self.bypass_rls,
        }

    @property
    def is_admin(self) -> bool:
        return self.role in {"admin", "super_admin"}

    @property
    def is_impersonating(self) -> bool:
        return self.impersonator_id is not None


# ContextVar — module-level singleton
_tenant_var: ContextVar[Optional[TenantContext]] = ContextVar(
    "waibao_tenant_context", default=None
)


def set_tenant_context(ctx: TenantContext) -> object:
    """Bind ``ctx`` to the current async context. Returns reset token."""
    logger.debug("set_tenant_context %s", ctx)
    return _tenant_var.set(ctx)


def reset_tenant_context(token: object) -> None:
    """Restore the previous binding (mirror of ``set_tenant_context``)."""
    _tenant_var.reset(token)  # type: ignore[arg-type]


def get_tenant_context() -> Optional[TenantContext]:
    """Read the current tenant context. May return ``None`` for background
    workers / startup tasks / unauthenticated routes."""
    return _tenant_var.get()


def get_tenant() -> TenantContext:
    """Strict version — raise if no tenant is bound."""
    ctx = _tenant_var.get()
    if ctx is None:
        raise RuntimeError(
            "TenantContext is not bound — request was made outside of "
            "a tenant-aware middleware. Did you forget Depends(get_tenant_context)?"
        )
    return ctx


@contextlib.contextmanager
def with_tenant(
    tenant_id: uuid.UUID | str,
    user_id: Optional[uuid.UUID | str] = None,
    role: str = "talent_partner",
    plan: str = "free",
    *,
    bypass_rls: bool = False,
    impersonator_id: Optional[uuid.UUID | str] = None,
) -> Iterator[TenantContext]:
    """Context-manager helper for tests / background workers."""
    ctx = TenantContext(
        tenant_id=uuid.UUID(str(tenant_id)),
        user_id=uuid.UUID(str(user_id)) if user_id else None,
        role=role,
        plan=plan,
        bypass_rls=bypass_rls,
        impersonator_id=uuid.UUID(str(impersonator_id)) if impersonator_id else None,
    )
    token = set_tenant_context(ctx)
    try:
        yield ctx
    finally:
        reset_tenant_context(token)


__all__ = [
    "TenantContext",
    "set_tenant_context",
    "reset_tenant_context",
    "get_tenant_context",
    "get_tenant",
    "with_tenant",
]
