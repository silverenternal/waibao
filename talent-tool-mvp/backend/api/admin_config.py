"""v6.0 T2102 — Admin Config API.

CRUD over the runtime Config Center + version history + rollback.

Endpoints:
- GET    /api/admin/config            List all configs (with optional scope filter)
- GET    /api/admin/config/{scope}/{key}    Read one config
- PUT    /api/admin/config/{scope}/{key}    Set value (creates if missing)
- DELETE /api/admin/config/{scope}/{key}    Delete a config
- GET    /api/admin/config/{scope}/{key}/history   List version history
- POST   /api/admin/config/{scope}/{key}/rollback  Roll back to a version
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from services.platform import config_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/config", tags=["admin-config"])


class ConfigSetBody(BaseModel):
    value: Any
    value_type: str = Field("json", pattern="^(json|string|number|boolean|array)$")
    description: Optional[str] = None
    changed_by: Optional[str] = None
    comment: Optional[str] = None


class ConfigRecordBody(BaseModel):
    scope: str
    key: str
    value: Any
    version: int
    value_type: str = "json"


class RollbackBody(BaseModel):
    to_version: int
    changed_by: Optional[str] = None


@router.get("")
async def list_configs(scope: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    return [r.to_dict() for r in config_service.list_keys(scope)]


@router.get("/{scope}/{key}")
async def get_config(scope: str, key: str) -> Dict[str, Any]:
    rec = config_service.get_record(scope, key)
    if rec is None:
        raise HTTPException(404, f"config {scope}/{key} not found")
    return rec.to_dict()


@router.put("/{scope}/{key}")
async def set_config(scope: str, key: str, body: ConfigSetBody) -> Dict[str, Any]:
    if scope not in config_service.VALID_SCOPES:
        raise HTTPException(400, f"invalid scope {scope!r}")
    try:
        rec = config_service.set_value(
            scope, key, body.value, value_type=body.value_type,
            description=body.description, changed_by=body.changed_by,
            comment=body.comment,
        )
        return rec.to_dict()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"set failed: {exc}") from exc


@router.delete("/{scope}/{key}")
async def delete_config(scope: str, key: str) -> Dict[str, bool]:
    ok = config_service.delete(scope, key)
    return {"deleted": ok}


@router.get("/{scope}/{key}/history")
async def history(scope: str, key: str,
                  limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
    return config_service.history(scope, key, limit=limit)


@router.post("/{scope}/{key}/rollback")
async def rollback_config(scope: str, key: str, body: RollbackBody) -> Dict[str, Any]:
    rec = config_service.rollback(scope, key, body.to_version,
                                  changed_by=body.changed_by)
    if rec is None:
        raise HTTPException(404, f"version {body.to_version} not found")
    return rec.to_dict()


@router.post("/_reload-cache")
async def reload_cache() -> Dict[str, bool]:
    config_service.clear_cache()
    return {"reloaded": True}


__all__ = ["router"]
