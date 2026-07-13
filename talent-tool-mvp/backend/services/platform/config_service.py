"""v6.0 T2102 — Config Service.

Reads / writes runtime configuration. Every change is:
- persisted (Supabase `configs` table)
- audited (append-only `config_history`)
- broadcast (`config.changed` EventBus event so workers / front-end
  refresh immediately without a deploy).

This is the single read path for any agent / service that needs an
operator-tunable setting (agent prompts, bias thresholds, match weights,
feature flags).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from eventbus import emit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope / value_type constants
# ---------------------------------------------------------------------------

VALID_SCOPES = ("system", "org", "agent", "feature", "service_toggle")
VALID_VALUE_TYPES = ("json", "string", "number", "boolean", "array")


@dataclass
class ConfigRecord:
    scope: str
    key: str
    value: Any
    version: int
    value_type: str = "json"
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "scope": self.scope,
            "key": self.key,
            "value": self.value,
            "version": self.version,
            "value_type": self.value_type,
        }
        if self.description is not None:
            d["description"] = self.description
        if self.updated_by is not None:
            d["updated_by"] = self.updated_by
        if self.updated_at is not None:
            d["updated_at"] = self.updated_at
        if self.id is not None:
            d["id"] = self.id
        return d


# ---------------------------------------------------------------------------
# In-memory cache (per-process)
# ---------------------------------------------------------------------------

_CACHE: Dict[Tuple[str, str], ConfigRecord] = {}
_INITIALIZED = False


def _cache_key(scope: str, key: str) -> Tuple[str, str]:
    return (scope, key)


def _coerce_value(value: Any, value_type: str) -> Any:
    """Validate / coerce a value according to the declared type."""
    if value_type == "string":
        return str(value)
    if value_type == "number":
        if isinstance(value, (int, float)):
            return value
        return float(value)
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if value_type == "array":
        if isinstance(value, list):
            return value
        return list(value)
    # default: json
    if isinstance(value, (dict, list, int, float, bool, str)) or value is None:
        return value
    return json.loads(value) if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Supabase handles (lazy)
# ---------------------------------------------------------------------------

def _supabase():
    from api.deps import get_supabase_admin
    return get_supabase_admin()


# ---------------------------------------------------------------------------
# get / set / list / delete
# ---------------------------------------------------------------------------

def get(scope: str, key: str, default: Any = None) -> Any:
    """Read a single config value, returning `default` if not set."""
    rec = _get_record(scope, key)
    if rec is None:
        return default
    return copy.deepcopy(rec.value)


def get_record(scope: str, key: str) -> Optional[ConfigRecord]:
    return _get_record(scope, key)


def _get_record(scope: str, key: str) -> Optional[ConfigRecord]:
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}")
    cached = _CACHE.get(_cache_key(scope, key))
    if cached is not None:
        return cached
    try:
        sb = _supabase()
        resp = sb.table("configs").select("*").eq("scope", scope).eq("key", key).limit(1).execute()
        if not resp.data:
            return None
        row = resp.data[0]
        rec = ConfigRecord(
            scope=row["scope"],
            key=row["key"],
            value=row["value"],
            version=row.get("version", 1),
            value_type=row.get("value_type", "json"),
            description=row.get("description"),
            updated_by=row.get("updated_by"),
            updated_at=row.get("updated_at"),
            id=row.get("id"),
        )
        _CACHE[_cache_key(scope, key)] = rec
        return rec
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.get failed for %s/%s: %s", scope, key, exc)
        return None


def set_value(scope: str, key: str, value: Any, *,
              value_type: str = "json",
              description: Optional[str] = None,
              changed_by: Optional[str] = None,
              comment: Optional[str] = None) -> ConfigRecord:
    """Create-or-update a config entry and broadcast `config.changed`."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}")
    coerced = _coerce_value(value, value_type)
    try:
        sb = _supabase()
        existing = sb.table("configs").select("id,version").eq("scope", scope).eq("key", key).limit(1).execute()
        if existing.data:
            cid = existing.data[0]["id"]
            new_version = existing.data[0]["version"] + 1
            sb.table("configs").update({
                "value": coerced, "value_type": value_type,
                "description": description, "updated_by": changed_by,
                "updated_at": "now()", "version": new_version,
            }).eq("id", cid).execute()
            sb.table("config_history").insert({
                "config_id": cid, "scope": scope, "key": key, "value": coerced,
                "version": new_version, "changed_by": changed_by,
                "operation": "update", "comment": comment,
            }).execute()
            rec = ConfigRecord(scope=scope, key=key, value=coerced,
                               version=new_version, value_type=value_type,
                               description=description, updated_by=changed_by,
                               id=cid)
        else:
            insert = sb.table("configs").insert({
                "scope": scope, "key": key, "value": coerced,
                "value_type": value_type, "description": description,
                "updated_by": changed_by, "version": 1,
            }).execute()
            cid = insert.data[0]["id"] if insert.data else None
            sb.table("config_history").insert({
                "config_id": cid, "scope": scope, "key": key, "value": coerced,
                "version": 1, "changed_by": changed_by,
                "operation": "create", "comment": comment,
            }).execute()
            rec = ConfigRecord(scope=scope, key=key, value=coerced,
                               version=1, value_type=value_type,
                               description=description, updated_by=changed_by,
                               id=cid)
        _CACHE[_cache_key(scope, key)] = rec
        # broadcast
        try:
            emit("config.changed", {
                "scope": scope, "key": key, "value": coerced,
                "version": rec.version, "changed_by": changed_by,
                "value_type": value_type,
            }, source="service.config")
        except Exception as exc:  # noqa: BLE001
            logger.debug("config.changed emit failed: %s", exc)
        return rec
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.set failed for %s/%s: %s", scope, key, exc)
        raise


def delete(scope: str, key: str, *, changed_by: Optional[str] = None) -> bool:
    try:
        sb = _supabase()
        resp = sb.table("configs").delete().eq("scope", scope).eq("key", key).execute()
        _CACHE.pop(_cache_key(scope, key), None)
        try:
            emit("config.changed", {
                "scope": scope, "key": key, "value": None,
                "version": 0, "changed_by": changed_by,
                "operation": "delete",
            }, source="service.config")
        except Exception:  # noqa: BLE001
            pass
        return bool(resp.data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.delete failed: %s", exc)
        return False


def list_keys(scope: Optional[str] = None) -> List[ConfigRecord]:
    try:
        sb = _supabase()
        q = sb.table("configs").select("*")
        if scope:
            q = q.eq("scope", scope)
        resp = q.execute()
        return [
            ConfigRecord(scope=r["scope"], key=r["key"], value=r["value"],
                         version=r.get("version", 1),
                         value_type=r.get("value_type", "json"),
                         description=r.get("description"),
                         updated_by=r.get("updated_by"),
                         updated_at=r.get("updated_at"),
                         id=r.get("id"))
            for r in resp.data
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.list_keys failed: %s", exc)
        return []


def history(scope: str, key: str, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        sb = _supabase()
        resp = sb.table("config_history").select("*").eq("scope", scope).eq(
            "key", key).order("version", desc=True).limit(limit).execute()
        return list(resp.data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.history failed: %s", exc)
        return []


def rollback(scope: str, key: str, to_version: int, *,
             changed_by: Optional[str] = None) -> Optional[ConfigRecord]:
    """Roll back to a specific prior version."""
    try:
        sb = _supabase()
        target = sb.table("config_history").select("value,version").eq(
            "scope", scope).eq("key", key).eq("version", to_version).limit(1).execute()
        if not target.data:
            return None
        old_value = target.data[0]["value"]
        current = sb.table("configs").select("id,version").eq("scope", scope).eq(
            "key", key).limit(1).execute()
        if not current.data:
            return set_value(scope, key, old_value, changed_by=changed_by,
                             comment=f"rollback to v{to_version}")
        cid = current.data[0]["id"]
        new_version = current.data[0]["version"] + 1
        sb.table("configs").update({
            "value": old_value, "version": new_version,
            "updated_by": changed_by, "updated_at": "now()",
        }).eq("id", cid).execute()
        sb.table("config_history").insert({
            "config_id": cid, "scope": scope, "key": key, "value": old_value,
            "version": new_version, "changed_by": changed_by,
            "operation": "rollback",
            "comment": f"rolled back to v{to_version}",
        }).execute()
        rec = _get_record(scope, key)
        try:
            emit("config.changed", {
                "scope": scope, "key": key, "value": old_value,
                "version": new_version, "changed_by": changed_by,
                "operation": "rollback",
            }, source="service.config")
            emit("config.rolled_back", {
                "scope": scope, "key": key, "from_version": current.data[0]["version"],
                "to_version": to_version, "changed_by": changed_by,
            }, source="service.config")
        except Exception:  # noqa: BLE001
            pass
        return rec
    except Exception as exc:  # noqa: BLE001
        logger.warning("config_service.rollback failed: %s", exc)
        return None


def clear_cache() -> None:
    """Test helper — flush in-memory cache."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Convenience: typed getters for the most common needs
# ---------------------------------------------------------------------------

def get_string(scope: str, key: str, default: str = "") -> str:
    v = get(scope, key, default)
    return str(v) if v is not None else default


def get_int(scope: str, key: str, default: int = 0) -> int:
    v = get(scope, key, default)
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return default


def get_float(scope: str, key: str, default: float = 0.0) -> float:
    v = get(scope, key, default)
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return default


def get_bool(scope: str, key: str, default: bool = False) -> bool:
    v = get(scope, key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def get_dict(scope: str, key: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    v = get(scope, key, default)
    return v if isinstance(v, dict) else (default or {})


def get_list(scope: str, key: str, default: Optional[List[Any]] = None) -> List[Any]:
    v = get(scope, key, default)
    return v if isinstance(v, list) else (default or [])


def get_prompt(agent: str, prompt_key: str = "system", default: str = "") -> str:
    """Read agent.prompts.<agent>.<prompt_key> as a string."""
    key = f"agent.prompts.{agent}.{prompt_key}"
    val = get_string("agent", key, default)
    return val


__all__ = [
    "ConfigRecord",
    "VALID_SCOPES",
    "VALID_VALUE_TYPES",
    "get", "get_record", "set_value", "delete",
    "list_keys", "history", "rollback", "clear_cache",
    "get_string", "get_int", "get_float", "get_bool",
    "get_dict", "get_list", "get_prompt",
]
