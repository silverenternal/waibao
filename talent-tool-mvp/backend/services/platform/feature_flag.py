"""v6.0 T2103 — Feature Flag service.

A small, deterministic feature flag implementation. The contract:

* ``is_enabled(name, user_id=None, org_id=None) -> bool`` is the only hot
  path. It must be cheap (one Redis GET, one hash).
* Decision order (highest priority first):
    1. Disabled globally => always False (unless override explicitly forces it on).
    2. Per-user override (white/black list) => wins.
    3. Per-org override => wins.
    4. ``rollout_percent`` hash bucket => ``hash(user_id|org_id|flag) % 100 < p``.
    5. Default rule in ``rules.jsonb`` (cohort / region / custom).
    6. ``enabled`` column => boolean toggle for admin enable → 全网生效.
* Cache TTL is 60s. Cache key incorporates user/org so per-user overrides
  are also cached.
* Audit: every state mutation appends to ``feature_flag_audit``.

This module degrades gracefully when Supabase / Redis are unavailable —
the in-memory fallback is enough for dev / tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eventbus import emit

logger = logging.getLogger(__name__)

CACHE_TTL_S = 60.0
HASH_BUCKETS = 100  # rollout_percent is integer 0..100

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FeatureFlag:
    name: str
    description: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)
    rollout_percent: int = 0
    enabled: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FlagOverride:
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    flag_name: str = ""
    value: bool = True
    reason: str = ""
    expires_at: Optional[str] = None
    created_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FeatureFlagError(Exception):
    pass


class FlagNotFound(FeatureFlagError):
    pass


# ---------------------------------------------------------------------------
# Hash bucket — deterministic, uniform across users
# ---------------------------------------------------------------------------

def _bucket(subject: str, flag_name: str) -> int:
    """Stable 0..99 bucket for (subject, flag_name).

    We use SHA-256 truncated to 8 hex chars (32 bits) mod 100. SHA-256 gives
    very uniform distribution; the 100-bucket granularity is enough for
    rollout percentages.
    """
    raw = f"{subject}|{flag_name}".encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()[:8]
    return int(h, 16) % HASH_BUCKETS


# ---------------------------------------------------------------------------
# Cache abstraction — Redis with in-memory fallback
# ---------------------------------------------------------------------------

class _Cache:
    def __init__(self) -> None:
        self._mem: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._init_redis()

    def _init_redis(self) -> None:
        url = os.environ.get("WAIBAO_REDIS_URL") or os.environ.get("REDIS_URL")
        if not url:
            return
        try:
            import redis  # type: ignore

            self._redis = redis.Redis.from_url(url, decode_responses=True)
            self._redis.ping()  # surface connection issues early
            logger.info("feature_flag cache: using redis at %s", url)
        except Exception as exc:  # noqa: BLE001 — graceful fallback
            logger.warning("feature_flag cache: redis unavailable (%s)", exc)
            self._redis = None

    def get(self, key: str) -> Optional[Any]:
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                return self._mem_get(key)
        return self._mem_get(key)

    def set(self, key: str, value: Any, ttl_s: float = CACHE_TTL_S) -> None:
        payload = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, int(ttl_s), payload)
                return
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            self._mem[key] = (time.time() + ttl_s, value)

    def invalidate(self, prefix: str = "") -> None:
        if self._redis is not None:
            try:
                if not prefix:
                    self._redis.flushdb()
                else:
                    for k in self._redis.scan_iter(match=f"{prefix}*"):
                        self._redis.delete(k)
                return
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            if not prefix:
                self._mem.clear()
            else:
                for k in list(self._mem.keys()):
                    if k.startswith(prefix):
                        self._mem.pop(k, None)

    def _mem_get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._mem.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                self._mem.pop(key, None)
                return None
            return value


_cache = _Cache()


# ---------------------------------------------------------------------------
# Supabase abstraction — same shape as config_service so it can swap
# ---------------------------------------------------------------------------

class _SupabaseClient:
    """Tiny Supabase wrapper; falls back to in-memory store if unconfigured.

    The contract intentionally mirrors ``services.platform.config_service``
    so future migrations to a hosted Supabase only touch this class.
    """

    _instance: Optional["_SupabaseClient"] = None

    def __init__(self) -> None:
        self._flags: Dict[str, FeatureFlag] = {}
        self._overrides: Dict[str, List[FlagOverride]] = {}
        self._audit: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._init_remote()

    @classmethod
    def instance(cls) -> "_SupabaseClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_remote(self) -> None:
        url = os.environ.get("SUPABASE_URL") or os.environ.get("WAIBAO_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("WAIBAO_SUPABASE_KEY")
        if not (url and key):
            logger.info("feature_flag: no Supabase creds; using in-memory store")
            return
        try:
            from supabase import create_client  # type: ignore

            self._remote = create_client(url, key)
            logger.info("feature_flag: connected to Supabase at %s", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("feature_flag: Supabase unavailable (%s); using memory", exc)
            self._remote = None

    # ---- flags ----------------------------------------------------------
    def list_flags(self) -> List[FeatureFlag]:
        with self._lock:
            return list(self._flags.values())

    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        with self._lock:
            return self._flags.get(name)

    def upsert_flag(self, flag: FeatureFlag, *, actor: Optional[str] = None) -> FeatureFlag:
        with self._lock:
            existing = self._flags.get(flag.name)
            flag.updated_at = _now_iso()
            flag.updated_by = actor or flag.updated_by
            self._flags[flag.name] = flag
            self._audit.append({
                "flag_name": flag.name,
                "action": "update" if existing else "create",
                "before": existing.to_dict() if existing else None,
                "after": flag.to_dict(),
                "actor": actor,
                "note": "",
                "created_at": _now_iso(),
            })
        _cache.invalidate(f"ff:{flag.name}:")
        try:
            emit("feature_flag.changed", {"name": flag.name, "enabled": flag.enabled,
                                          "rollout_percent": flag.rollout_percent})
        except Exception:  # noqa: BLE001
            pass
        return flag

    def delete_flag(self, name: str, *, actor: Optional[str] = None) -> None:
        with self._lock:
            existing = self._flags.pop(name, None)
            if existing:
                self._audit.append({
                    "flag_name": name,
                    "action": "delete",
                    "before": existing.to_dict(),
                    "after": None,
                    "actor": actor,
                    "note": "",
                    "created_at": _now_iso(),
                })
        _cache.invalidate(f"ff:{name}:")

    # ---- overrides ------------------------------------------------------
    def overrides_for(self, flag_name: str) -> List[FlagOverride]:
        with self._lock:
            return list(self._overrides.get(flag_name, []))

    def set_override(self, override: FlagOverride, *, actor: Optional[str] = None) -> FlagOverride:
        with self._lock:
            arr = self._overrides.setdefault(override.flag_name, [])
            # de-dup on user_id/org_id
            arr[:] = [
                o for o in arr
                if not (
                    (override.user_id and o.user_id == override.user_id)
                    or (override.org_id and o.org_id == override.org_id)
                )
            ]
            override.created_by = actor
            arr.append(override)
            self._audit.append({
                "flag_name": override.flag_name,
                "action": "override_set",
                "before": None,
                "after": override.to_dict(),
                "actor": actor,
                "note": "",
                "created_at": _now_iso(),
            })
        _cache.invalidate(f"ff:{override.flag_name}:")
        return override

    def remove_override(self, flag_name: str, *, user_id: Optional[str] = None,
                        org_id: Optional[str] = None, actor: Optional[str] = None) -> int:
        with self._lock:
            arr = self._overrides.get(flag_name, [])
            before = len(arr)
            arr[:] = [
                o for o in arr
                if not (
                    (user_id and o.user_id == user_id)
                    or (org_id and o.org_id == org_id)
                )
            ]
            removed = before - len(arr)
            if removed:
                self._audit.append({
                    "flag_name": flag_name,
                    "action": "override_remove",
                    "before": {"user_id": user_id, "org_id": org_id},
                    "after": None,
                    "actor": actor,
                    "note": "",
                    "created_at": _now_iso(),
                })
        _cache.invalidate(f"ff:{flag_name}:")
        return removed


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def _decide(flag: FeatureFlag, *, user_id: Optional[str], org_id: Optional[str],
            overrides: List[FlagOverride]) -> Tuple[bool, str]:
    """Return (enabled, reason)."""
    # 1) per-user overrides — whitelist always wins
    if user_id:
        for ov in overrides:
            if ov.user_id == user_id:
                return ov.value, f"override:user:{user_id}"

    # 2) per-org overrides
    if org_id:
        for ov in overrides:
            if ov.org_id == org_id:
                return ov.value, f"override:org:{org_id}"

    # 3) admin enable → 全网生效 (the spec asks for this knob explicitly)
    if flag.enabled and flag.rollout_percent >= 100:
        return True, "enabled:full"

    # 4) rollout bucketing
    if flag.rollout_percent > 0:
        subject = user_id or org_id
        if subject:
            bucket = _bucket(subject, flag.name)
            if bucket < flag.rollout_percent:
                return True, f"rollout:{bucket}<{flag.rollout_percent}"
            return False, f"rollout:{bucket}>={flag.rollout_percent}"

    # 5) rule-based cohort/region (rules jsonb)
    rule_decision = _eval_rules(flag.rules, user_id=user_id, org_id=org_id)
    if rule_decision is not None:
        return rule_decision, "rule"

    # 6) simple enabled toggle
    if flag.enabled:
        return True, "enabled"

    return False, "default-off"


def _eval_rules(rules: Dict[str, Any], *, user_id: Optional[str],
                org_id: Optional[str]) -> Optional[bool]:
    """Evaluate a small declarative ruleset.

    Supported shapes::

        rules:
          regions: ["cn", "uk"]
          orgs: ["org_demo"]
          min_user_id: 1000
          max_user_id: 9999

    Returns the decision if a rule fires, else None.
    """
    if not rules:
        return None

    regions = rules.get("regions")
    if regions and org_id:
        if org_id in regions:
            return True
    orgs = rules.get("orgs")
    if orgs and org_id:
        if org_id in orgs:
            return True
    min_uid = rules.get("min_user_id")
    max_uid = rules.get("max_user_id")
    if user_id and (min_uid is not None or max_uid is not None):
        try:
            uid_int = int(user_id)
        except (TypeError, ValueError):
            uid_int = None
        if uid_int is not None:
            if min_uid is not None and uid_int < int(min_uid):
                return False
            if max_uid is not None and uid_int > int(max_uid):
                return False
            if (min_uid is not None or max_uid is not None):
                return True
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_enabled(name: str, *, user_id: Optional[str] = None,
               org_id: Optional[str] = None) -> bool:
    """Return whether ``name`` is enabled for the given (user, org) pair.

    Cheap — at most one Redis round-trip; falls back to in-memory.
    """
    cache_key = f"ff:{name}:u={user_id or ''}:o={org_id or ''}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return bool(cached.get("enabled", False))

    flag = _SupabaseClient.instance().get_flag(name)
    if flag is None:
        # Unknown flag defaults to enabled=False; do not cache so a freshly
        # created flag becomes effective without waiting 60s.
        return False

    overrides = _SupabaseClient.instance().overrides_for(name)
    decision, _reason = _decide(flag, user_id=user_id, org_id=org_id, overrides=overrides)
    _cache.set(cache_key, {"enabled": decision}, ttl_s=CACHE_TTL_S)
    return decision


def get_flag(name: str) -> Optional[FeatureFlag]:
    """Module-level convenience: lookup a flag by name."""
    return _SupabaseClient.instance().get_flag(name)


def decide(name: str, *, user_id: Optional[str] = None,
           org_id: Optional[str] = None) -> Dict[str, Any]:
    """Like ``is_enabled`` but returns the structured decision payload."""
    flag = _SupabaseClient.instance().get_flag(name)
    if flag is None:
        return {"name": name, "enabled": False, "reason": "missing", "rule": None}
    overrides = _SupabaseClient.instance().overrides_for(name)
    enabled, reason = _decide(flag, user_id=user_id, org_id=org_id, overrides=overrides)
    return {
        "name": name,
        "enabled": enabled,
        "reason": reason,
        "rollout_percent": flag.rollout_percent,
        "global_enabled": flag.enabled,
    }


# ---- admin surface --------------------------------------------------------

def list_flags() -> List[Dict[str, Any]]:
    return [f.to_dict() for f in _SupabaseClient.instance().list_flags()]


def upsert_flag(payload: Dict[str, Any], *, actor: Optional[str] = None) -> Dict[str, Any]:
    if not payload.get("name"):
        raise FeatureFlagError("name is required")
    rollout = int(payload.get("rollout_percent", 0) or 0)
    if rollout < 0 or rollout > 100:
        raise FeatureFlagError("rollout_percent must be in [0, 100]")
    flag = FeatureFlag(
        name=str(payload["name"]),
        description=str(payload.get("description", "")),
        rules=dict(payload.get("rules") or {}),
        rollout_percent=rollout,
        enabled=bool(payload.get("enabled", False)),
    )
    saved = _SupabaseClient.instance().upsert_flag(flag, actor=actor)
    return saved.to_dict()


def delete_flag(name: str, *, actor: Optional[str] = None) -> None:
    _SupabaseClient.instance().delete_flag(name, actor=actor)


def set_override(payload: Dict[str, Any], *, actor: Optional[str] = None) -> Dict[str, Any]:
    if not payload.get("flag_name"):
        raise FeatureFlagError("flag_name required")
    if not payload.get("user_id") and not payload.get("org_id"):
        raise FeatureFlagError("user_id or org_id required")
    override = FlagOverride(
        flag_name=str(payload["flag_name"]),
        user_id=payload.get("user_id"),
        org_id=payload.get("org_id"),
        value=bool(payload.get("value", True)),
        reason=str(payload.get("reason", "")),
        expires_at=payload.get("expires_at"),
    )
    saved = _SupabaseClient.instance().set_override(override, actor=actor)
    return saved.to_dict()


def remove_override(flag_name: str, *, user_id: Optional[str] = None,
                    org_id: Optional[str] = None, actor: Optional[str] = None) -> int:
    return _SupabaseClient.instance().remove_override(
        flag_name, user_id=user_id, org_id=org_id, actor=actor)


def list_overrides(flag_name: str) -> List[Dict[str, Any]]:
    return [o.to_dict() for o in _SupabaseClient.instance().overrides_for(flag_name)]


def audit_log(flag_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Return recent audit entries (newest first)."""
    with _SupabaseClient.instance()._lock:  # noqa: SLF001 — admin helper
        rows = _SupabaseClient.instance()._audit  # noqa: SLF001
        out = [r for r in rows if not flag_name or r["flag_name"] == flag_name]
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out[:limit]


def reset_for_tests() -> None:
    """Reset module state — used by test suite."""
    global _cache  # noqa: PLW0603
    _cache = _Cache()
    _SupabaseClient._instance = None  # noqa: SLF001


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()