"""v8.0 T3501 — Service Toggle core.

Responsibilities:
    * Register / deregister services in the catalog
    * Enable / disable / override / rollback operations
    * Multi-dimension access check (status + plan + role + per-org override)
    * 60-second Redis cache (falls back to in-process LRU if no Redis)
    * Emit `service.changed` EventBus events on every mutation
    * Persist all mutations to `services` / `service_overrides` / `service_audit`
    * 1-key rollback that restores the previous state from audit history

This is a thin layer over Supabase. It is safe to import from anywhere;
no DB call is made until an action is performed.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .service_catalog import (
    PlanTier,
    Service,
    ServiceCategory,
    ServiceOverride,
    ServiceStatus,
    plan_covers,
)

logger = logging.getLogger("recruittech.platform.service_toggle")


# ---------------------------------------------------------------------------
# Cache TTL (60s per spec)
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 60
_LOCAL_CACHE: Dict[str, Any] = {}
_LOCAL_TS: Dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_str_to_iso(s: Optional[str]) -> Optional[str]:
    return s


# ---------------------------------------------------------------------------
# Cache helpers (Redis with in-memory fallback)
# ---------------------------------------------------------------------------
def _redis_client():
    """Lazy import; return None if Redis not available."""
    try:
        import redis  # type: ignore

        url = os.environ.get("REDIS_URL")
        if not url:
            return None
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


_RC = None


def _get_redis():
    global _RC
    if _RC is None:
        _RC = _redis_client()
    return _RC


def _cache_get(key: str) -> Optional[Any]:
    rc = _get_redis()
    if rc is not None:
        try:
            raw = rc.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception as exc:  # pragma: no cover
            logger.debug("Redis GET failed for %s: %s", key, exc)
    # local fallback
    ts = _LOCAL_TS.get(key)
    if ts is not None and (time.time() - ts) < CACHE_TTL_SECONDS:
        return _LOCAL_CACHE.get(key)
    return None


def _cache_set(key: str, value: Any) -> None:
    rc = _get_redis()
    payload = json.dumps(value, default=str)
    if rc is not None:
        try:
            rc.setex(key, CACHE_TTL_SECONDS, payload)
            return
        except Exception as exc:  # pragma: no cover
            logger.debug("Redis SETEX failed for %s: %s", key, exc)
    _LOCAL_CACHE[key] = value
    _LOCAL_TS[key] = time.time()


def invalidate_cache(prefix: Optional[str] = None) -> None:
    """Bust cache — either one prefix or everything."""
    rc = _get_redis()
    if rc is not None:
        try:
            if prefix:
                for k in rc.scan_iter(match=f"{prefix}*"):
                    rc.delete(k)
            else:
                for k in rc.scan_iter(match="service_toggle:*"):
                    rc.delete(k)
        except Exception as exc:  # pragma: no cover
            logger.debug("Redis invalidate failed: %s", exc)
    if prefix:
        for k in list(_LOCAL_CACHE.keys()):
            if k.startswith(prefix):
                _LOCAL_CACHE.pop(k, None)
                _LOCAL_TS.pop(k, None)
    else:
        _LOCAL_CACHE.clear()
        _LOCAL_TS.clear()


# ---------------------------------------------------------------------------
# Supabase helper (lazy)
# ---------------------------------------------------------------------------
def _supabase():
    from api.deps import get_supabase_admin

    return get_supabase_admin()


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------
def _key_catalog(plan: str, role: str) -> str:
    return f"service_toggle:catalog:{plan}:{role}"


def _key_service(name: str) -> str:
    return f"service_toggle:service:{name}"


def _key_override(org_id: str, name: str) -> str:
    return f"service_toggle:override:{org_id}:{name}"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ServiceToggleError(Exception):
    """Base error."""


class ServiceNotFoundError(ServiceToggleError):
    pass


class DependencyError(ServiceToggleError):
    """Raised when disabling a service that another service depends on."""


# ---------------------------------------------------------------------------
# EventBus emit helper (best effort)
# ---------------------------------------------------------------------------
def _emit(topic: str, payload: Dict[str, Any]) -> None:
    try:
        from eventbus import emit  # type: ignore

        emit(topic, payload)
    except Exception as exc:  # pragma: no cover
        logger.debug("EventBus emit %s skipped: %s", topic, exc)


# ---------------------------------------------------------------------------
# ServiceToggle — singleton orchestrator
# ---------------------------------------------------------------------------
@dataclass
class ServiceToggle:
    """Registry + access orchestrator.

    Usage:
        toggle = ServiceToggle.instance()
        toggle.register_service(Service(name="my_agent", display_name="..."))
        if toggle.is_enabled("my_agent", org_id, plan, role):
            ...
    """

    _instance: Optional["ServiceToggle"] = None

    @classmethod
    def instance(cls) -> "ServiceToggle":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """For tests — drop the singleton."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register_service(
        self,
        svc: Service,
        *,
        persist: bool = True,
        actor_id: Optional[str] = None,
    ) -> Service:
        """Register or replace a service in the catalog.

        If `persist=True` (default) and Supabase is configured, the row is
        upserted and audited. Otherwise only the in-process cache is updated
        (useful for tests).
        """
        if not isinstance(svc, Service):
            raise TypeError("register_service expects a Service dataclass")

        if persist:
            try:
                sb = _supabase()
                payload = {
                    "name": svc.name,
                    "display_name": svc.display_name,
                    "description": svc.description,
                    "category": svc.category.value,
                    "status": svc.status.value,
                    "plan_required": svc.plan_required.value,
                    "roles_allowed": svc.roles_allowed,
                    "dependencies": svc.dependencies,
                    "version": svc.version,
                }
                sb.table("services").upsert(payload, on_conflict="name").execute()
            except Exception as exc:
                logger.warning(
                    "Supabase persist failed (continuing with in-memory): %s",
                    exc,
                )

        invalidate_cache(_key_service(svc.name))
        invalidate_cache("service_toggle:catalog:")
        invalidate_cache("service_toggle:override:")

        if persist:
            self._audit(
                svc.name,
                "register",
                actor_id=actor_id,
                reason="register_service",
                after=svc.to_dict(),
            )

        _emit(
            "service.changed",
            {"event": "register", "service": svc.name, "status": svc.status.value},
        )

        logger.info("Registered service %s [%s]", svc.name, svc.status.value)
        return svc

    def deregister_service(
        self,
        name: str,
        *,
        actor_id: Optional[str] = None,
    ) -> None:
        """Remove a service and its overrides from the catalog."""
        sb = _supabase_safe()
        if sb is not None:
            try:
                sb.table("service_overrides").delete().eq(
                    "service_name", name
                ).execute()
                sb.table("services").delete().eq("name", name).execute()
            except Exception as exc:
                logger.warning("Supabase delete failed: %s", exc)

        invalidate_cache(_key_service(name))
        invalidate_cache("service_toggle:catalog:")
        invalidate_cache("service_toggle:override:")

        self._audit(
            name,
            "deregister",
            actor_id=actor_id,
            reason="deregister_service",
        )

        _emit(
            "service.changed",
            {"event": "deregister", "service": name},
        )

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def get_service(self, name: str) -> Optional[Service]:
        cached = _cache_get(_key_service(name))
        if cached is not None:
            return Service.from_dict(cached)
        sb = _supabase_safe()
        if sb is None:
            return None
        try:
            res = (
                sb.table("services")
                .select("*")
                .eq("name", name)
                .limit(1)
                .execute()
            )
            data = (res.data or [None])[0]
            if not data:
                _cache_set(_key_service(name), {"__missing__": True})
                return None
            svc = Service.from_dict(data)
            _cache_set(_key_service(name), svc.to_dict())
            return svc
        except Exception as exc:
            logger.warning("get_service %s failed: %s", name, exc)
            return None

    def get_catalog(self, plan: str = "free", role: str = "") -> List[Dict[str, Any]]:
        """Return catalog view tailored to a (plan, role)."""
        key = _key_catalog(plan, role)
        cached = _cache_get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        sb = _supabase_safe()
        items: List[Dict[str, Any]] = []
        if sb is None:
            # fall back to in-process registry (empty in production without DB)
            return items
        try:
            res = sb.table("services").select("*").execute()
            rows = res.data or []
            for row in rows:
                svc = Service.from_dict(row)
                enabled = self._check_layers(svc, org_id=None, plan=plan, role=role)
                item = svc.to_dict()
                item["available"] = enabled
                items.append(item)
        except Exception as exc:
            logger.warning("get_catalog failed: %s", exc)

        _cache_set(key, items)
        return items

    # ------------------------------------------------------------------
    # Permission checks (3 layers)
    # ------------------------------------------------------------------
    def is_enabled(
        self,
        name: str,
        org_id: Optional[str],
        plan: str,
        role: str,
    ) -> bool:
        svc = self.get_service(name)
        if svc is None:
            return False
        return self._check_layers(svc, org_id, plan, role)

    def _check_layers(
        self,
        svc: Service,
        org_id: Optional[str],
        plan: str,
        role: str,
    ) -> bool:
        # Layer 1: per-org override (highest priority)
        if org_id:
            ov = self._get_override(org_id, svc.name)
            if ov is not None and not ov.is_expired(_now_iso()):
                return ov.override_status == ServiceStatus.ENABLED

        # Layer 2: global status
        if svc.status == ServiceStatus.DISABLED:
            return False
        if svc.status == ServiceStatus.MAINTENANCE:
            # maintenance is reachable but flagged; for is_enabled() we treat
            # it as accessible. Use get_service() for richer signals.
            pass

        # Layer 3: plan
        if not plan_covers(plan, svc.plan_required.value):
            return False

        # Layer 4: role allow-list. Empty list => any role allowed.
        if svc.roles_allowed:
            normalized = role.lower().strip() if role else ""
            if normalized and normalized not in {r.lower() for r in svc.roles_allowed}:
                return False

        # Status sanity for enabled/beta
        if svc.status == ServiceStatus.ENABLED or svc.status == ServiceStatus.BETA:
            return True
        if svc.status == ServiceStatus.MAINTENANCE:
            return True
        return False

    def _get_override(
        self, org_id: str, name: str
    ) -> Optional[ServiceOverride]:
        key = _key_override(org_id, name)
        cached = _cache_get(key)
        if cached is not None:
            if cached.get("__missing__"):
                return None
            return ServiceOverride(
                org_id=cached["org_id"],
                service_name=cached["service_name"],
                override_status=ServiceStatus(cached["override_status"]),
                reason=cached.get("reason", ""),
                expires_at=cached.get("expires_at"),
                created_by=cached.get("created_by"),
                created_at=cached.get("created_at"),
            )
        sb = _supabase_safe()
        if sb is None:
            return None
        try:
            res = (
                sb.table("service_overrides")
                .select("*")
                .eq("org_id", org_id)
                .eq("service_name", name)
                .limit(1)
                .execute()
            )
            data = (res.data or [None])[0]
            if not data:
                _cache_set(key, {"__missing__": True})
                return None
            ov = ServiceOverride(
                org_id=data["org_id"],
                service_name=data["service_name"],
                override_status=ServiceStatus(data["override_status"]),
                reason=data.get("reason", ""),
                expires_at=data.get("expires_at"),
                created_by=data.get("created_by"),
                created_at=data.get("created_at"),
            )
            _cache_set(key, ov.to_dict())
            return ov
        except Exception as exc:
            logger.warning("_get_override failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def enable(
        self,
        name: str,
        *,
        actor_id: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        return self._set_status(
            name,
            ServiceStatus.ENABLED,
            actor_id=actor_id,
            reason=reason,
        )

    def disable(
        self,
        name: str,
        *,
        actor_id: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        # Block disable if anyone depends on us and is enabled
        dependents = self._find_dependents(name)
        active = [
            d for d in dependents if self.get_service(d) and
            self.get_service(d).status != ServiceStatus.DISABLED  # type: ignore[union-attr]
        ]
        if active:
            raise DependencyError(
                f"Cannot disable {name!r}: required by active services {active}"
            )
        return self._set_status(
            name,
            ServiceStatus.DISABLED,
            actor_id=actor_id,
            reason=reason,
        )

    def _set_status(
        self,
        name: str,
        status: ServiceStatus,
        *,
        actor_id: Optional[str],
        reason: str,
    ) -> Dict[str, Any]:
        before = self.get_service(name)
        if before is None:
            raise ServiceNotFoundError(f"Service {name!r} not found")

        sb = _supabase_safe()
        if sb is not None:
            try:
                sb.table("services").update(
                    {"status": status.value}
                ).eq("name", name).execute()
            except Exception as exc:
                logger.warning("Supabase update status failed: %s", exc)

        invalidate_cache(_key_service(name))
        invalidate_cache("service_toggle:catalog:")
        invalidate_cache("service_toggle:override:")

        after = before
        try:
            after_status = status
            after = Service(
                **{  # type: ignore[arg-type]
                    **before.to_dict(),
                    "status": after_status.value,
                    "version": before.version + 1,
                }
            )
        except Exception:
            pass

        self._audit(
            name,
            "disable" if status == ServiceStatus.DISABLED else
            ("enable" if status == ServiceStatus.ENABLED else status.value),
            actor_id=actor_id,
            reason=reason,
            before={"status": before.status.value},
            after={"status": status.value},
        )
        _emit(
            "service.changed",
            {
                "event": status.value,
                "service": name,
                "actor_id": actor_id,
                "reason": reason,
            },
        )
        return {"before": before.status.value, "after": status.value}

    def override(
        self,
        org_id: str,
        name: str,
        status: str | ServiceStatus,
        reason: str = "",
        *,
        expires_at: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> ServiceOverride:
        """Force a per-org status (highest priority)."""
        target = ServiceStatus.coerce(status) if not isinstance(status, ServiceStatus) else status
        if target == ServiceStatus.BETA:
            raise ValueError("override_status must be enabled/disabled/maintenance")

        sb = _supabase_safe()
        payload = {
            "org_id": org_id,
            "service_name": name,
            "override_status": target.value,
            "reason": reason,
            "expires_at": expires_at,
            "created_by": actor_id,
        }
        if sb is not None:
            try:
                sb.table("service_overrides").upsert(
                    payload, on_conflict="org_id,service_name"
                ).execute()
            except Exception as exc:
                logger.warning("Supabase override upsert failed: %s", exc)

        invalidate_cache(_key_override(org_id, name))
        invalidate_cache("service_toggle:catalog:")

        ov = ServiceOverride(
            org_id=org_id,
            service_name=name,
            override_status=target,
            reason=reason,
            expires_at=expires_at,
            created_by=actor_id,
            created_at=_now_iso(),
        )
        self._audit(
            name,
            "override",
            actor_id=actor_id,
            reason=reason,
            before={"status": "none"},
            after={
                "override": target.value,
                "org_id": org_id,
                "expires_at": expires_at,
            },
        )
        _emit(
            "service.changed",
            {
                "event": "override",
                "service": name,
                "org_id": org_id,
                "status": target.value,
                "actor_id": actor_id,
                "reason": reason,
            },
        )
        return ov

    def rollback(
        self,
        name: str,
        *,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """1-key rollback — restore the row to its previous status.

        Uses the most recent service_audit row that is NOT itself a rollback
        to derive the previous state. If no history exists, fall back to
        ``enabled`` so the service is at least reachable.
        """
        before = self.get_service(name)
        if before is None:
            raise ServiceNotFoundError(f"Service {name!r} not found")

        prev_status = self._last_status_before(name) or "enabled"
        sb = _supabase_safe()
        if sb is not None:
            try:
                sb.table("services").update(
                    {"status": prev_status}
                ).eq("name", name).execute()
            except Exception as exc:
                logger.warning("Rollback update failed: %s", exc)

        invalidate_cache(_key_service(name))
        invalidate_cache("service_toggle:catalog:")

        self._audit(
            name,
            "rollback",
            actor_id=actor_id,
            reason=f"rollback from {before.status.value}",
            before={"status": before.status.value},
            after={"status": prev_status},
        )
        _emit(
            "service.changed",
            {
                "event": "rollback",
                "service": name,
                "from": before.status.value,
                "to": prev_status,
                "actor_id": actor_id,
            },
        )
        return {"before": before.status.value, "after": prev_status}

    # ------------------------------------------------------------------
    # Dependency helpers
    # ------------------------------------------------------------------
    def resolve_dependencies(self, name: str) -> List[str]:
        """Return the *transitive* list of dependencies (BFS) in order.

        A dependency that is itself disabled is returned but flagged with a
        note via the optional tuple form. We return plain list[str] to keep
        the API friendly; nested inspection lives in the admin API.
        """
        svc = self.get_service(name)
        if svc is None:
            return []
        out: List[str] = []
        seen = {name}
        stack = list(svc.dependencies or [])
        while stack:
            cur = stack.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            dep = self.get_service(cur)
            if dep is not None:
                for n in dep.dependencies or []:
                    if n not in seen:
                        stack.append(n)
        return out

    def _find_dependents(self, name: str) -> List[str]:
        """Return services that list `name` in their dependencies."""
        sb = _supabase_safe()
        if sb is None:
            # scan in-process: this is best-effort and OK for tests
            return []
        try:
            res = sb.table("services").select("name,dependencies").execute()
            deps_all = res.data or []
            return [row["name"] for row in deps_all if name in (row.get("dependencies") or [])]
        except Exception as exc:
            logger.warning("_find_dependents failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Audit helper
    # ------------------------------------------------------------------
    def _audit(
        self,
        service_name: str,
        action: str,
        *,
        actor_id: Optional[str] = None,
        reason: str = "",
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
    ) -> None:
        sb = _supabase_safe()
        if sb is None:
            return
        try:
            payload = {
                "service_name": service_name,
                "action": action,
                "actor_id": actor_id,
                "reason": reason,
                "before": before,
                "after": after,
            }
            sb.table("service_audit").insert(payload).execute()
        except Exception as exc:
            logger.warning("audit insert failed: %s", exc)

    def _last_status_before(self, name: str) -> Optional[str]:
        sb = _supabase_safe()
        if sb is None:
            return None
        try:
            res = (
                sb.table("service_audit")
                .select("action,before,after")
                .eq("service_name", name)
                .neq("action", "rollback")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                return None
            row = rows[0]
            # If the last non-rollback action flipped status, we want to flip back
            if row.get("before") and "status" in row["before"]:
                return row["before"]["status"]
            return None
        except Exception as exc:
            logger.warning("_last_status_before failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Supabase handle that never raises (for tests)
# ---------------------------------------------------------------------------
def _supabase_safe():
    try:
        return _supabase()
    except Exception:
        return None


# Module-level singleton
service_toggle = ServiceToggle.instance()
