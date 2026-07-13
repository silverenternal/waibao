"""v6.0 T2103 — Admin Feature Flag API.

CRUD over the feature flag store + override management + decision probe.

Endpoints (all under ``/api/admin/feature-flags``):
- GET    /                          List all flags
- GET    /{name}                    Read one flag + overrides
- PUT    /{name}                    Create or update a flag
- DELETE /{name}                    Delete a flag
- POST   /{name}/override           Add an override (whitelist/blacklist)
- DELETE /{name}/override           Remove an override
- GET    /{name}/decide             Dry-run the decision for a (user, org)
- GET    /audit                     Audit log (optional flag filter)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from services.platform import feature_flag as ff
from services.platform.audit_v2 import audit_pii

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/feature-flags", tags=["admin-feature-flags"])


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class FlagUpsertBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    rules: Dict[str, Any] = Field(default_factory=dict)
    rollout_percent: int = Field(0, ge=0, le=100)
    enabled: bool = False
    actor: Optional[str] = None


class OverrideBody(BaseModel):
    flag_name: str = Field(..., min_length=1)
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    value: bool = True
    reason: str = ""
    expires_at: Optional[str] = None
    actor: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_flags() -> List[Dict[str, Any]]:
    return ff.list_flags()


@router.get("/audit")
async def audit(flag_name: Optional[str] = Query(None),
                limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return ff.audit_log(flag_name=flag_name, limit=limit)


@router.get("/{name}")
@audit_pii("read", "feature_flag", pii_fields=["name"], resource_id_arg="name")
async def get_flag(name: str) -> Dict[str, Any]:
    flag = ff._SupabaseClient.instance().get_flag(name)  # noqa: SLF001
    if flag is None:
        raise HTTPException(404, f"flag {name!r} not found")
    payload = flag.to_dict()
    payload["overrides"] = ff.list_overrides(name)
    return payload


@router.put("/{name}")
@audit_pii("update", "feature_flag", pii_fields=["name"], resource_id_arg="name")
async def upsert_flag(name: str, body: FlagUpsertBody) -> Dict[str, Any]:
    payload = body.model_dump()
    payload["name"] = name
    try:
        return ff.upsert_flag(payload, actor=body.actor)
    except ff.FeatureFlagError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{name}")
@audit_pii("delete", "feature_flag", pii_fields=["name"], resource_id_arg="name")
async def delete_flag(name: str, actor: Optional[str] = None) -> Dict[str, Any]:
    ff.delete_flag(name, actor=actor)
    return {"deleted": name}


@router.post("/{name}/override")
@audit_pii("update", "feature_flag_override", pii_fields=["name"], resource_id_arg="name")
async def set_override(name: str, body: OverrideBody) -> Dict[str, Any]:
    body.flag_name = name
    try:
        return ff.set_override(body.model_dump(), actor=body.actor)
    except ff.FeatureFlagError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{name}/override")
@audit_pii("delete", "feature_flag_override", pii_fields=["name"], resource_id_arg="name")
async def remove_override(name: str, user_id: Optional[str] = None,
                          org_id: Optional[str] = None,
                          actor: Optional[str] = None) -> Dict[str, Any]:
    removed = ff.remove_override(name, user_id=user_id, org_id=org_id, actor=actor)
    return {"removed": removed}


@router.get("/{name}/decide")
@audit_pii("read", "feature_flag", pii_fields=["name"], resource_id_arg="name")
async def decide(name: str, user_id: Optional[str] = None,
                 org_id: Optional[str] = None) -> Dict[str, Any]:
    return ff.decide(name, user_id=user_id, org_id=org_id)