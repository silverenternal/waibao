"""v6.0 T2104 — Admin Plugin API.

Endpoints (all under ``/api/admin/plugins``):
- GET    /                       List installed plugins
- POST   /install                Install from a directory path
- POST   /{name}/enable          Enable
- POST   /{name}/disable         Disable
- DELETE /{name}                 Uninstall
- POST   /{name}/run             Invoke a plugin's primary contribution
- GET    /{name}/runs            Run history
- GET    /runs                   All recent runs
- GET    /permissions            List host-allowed permission tokens

The install endpoint expects a JSON body containing the absolute path to a
directory containing ``plugin.yaml``. In production this should be paired
with a multipart-upload path that writes to a controlled plugin store —
out of scope for this milestone.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from plugins import (
    PluginAlreadyInstalled,
    PluginNotInstalled,
    PluginRegistryError,
    get_installed_plugin_registry,
)
from plugins.sdk.sandbox import SandboxConfig
from services.platform.audit_v2 import audit_pii

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/plugins", tags=["admin-plugins"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class InstallBody(BaseModel):
    directory: str = Field(..., min_length=1)
    actor: Optional[str] = None


class EnableBody(BaseModel):
    actor: Optional[str] = None


class DisableBody(BaseModel):
    actor: Optional[str] = None


class UninstallBody(BaseModel):
    actor: Optional[str] = None


class RunBody(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_plugins() -> List[Dict[str, Any]]:
    return get_installed_plugin_registry().list_installed()


@router.get("/permissions")
async def allowed_permissions() -> Dict[str, List[str]]:
    from plugins.sdk.manifest import _VALID_PERMS  # noqa: WPS437
    return {"allowed": sorted(_VALID_PERMS)}


@router.post("/install")
async def install(body: InstallBody) -> Dict[str, Any]:
    if not os.path.isdir(body.directory):
        raise HTTPException(400, f"directory not found: {body.directory}")
    try:
        result = get_installed_plugin_registry().install_from_directory(
            body.directory, actor=body.actor
        )
    except PluginAlreadyInstalled as exc:
        raise HTTPException(409, str(exc)) from exc
    if not result.success:
        raise HTTPException(400, result.to_dict())
    return {
        "installed": result.manifest.name if result.manifest else None,
        "version": result.manifest.version if result.manifest else None,
        "duration_ms": result.duration_ms,
    }


@router.post("/{name}/enable")
@audit_pii("update", "plugin", pii_fields=["name"], resource_id_arg="name")
async def enable(name: str, body: Optional[EnableBody] = None) -> Dict[str, Any]:
    try:
        return get_installed_plugin_registry().enable(
            name, actor=(body.actor if body else None)
        )
    except PluginNotInstalled as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{name}/disable")
@audit_pii("update", "plugin", pii_fields=["name"], resource_id_arg="name")
async def disable(name: str, body: Optional[DisableBody] = None) -> Dict[str, Any]:
    try:
        return get_installed_plugin_registry().disable(
            name, actor=(body.actor if body else None)
        )
    except PluginNotInstalled as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{name}")
@audit_pii("delete", "plugin", pii_fields=["name"], resource_id_arg="name")
async def uninstall(name: str, body: Optional[UninstallBody] = None) -> Dict[str, Any]:
    try:
        return get_installed_plugin_registry().uninstall(
            name, actor=(body.actor if body else None)
        )
    except PluginNotInstalled as exc:
        raise HTTPException(404, str(exc)) from exc
    except PluginRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{name}/run")
@audit_pii("update", "plugin_run", pii_fields=["name"], resource_id_arg="name")
async def run(name: str, body: RunBody) -> Dict[str, Any]:
    try:
        return get_installed_plugin_registry().run(name, body.payload)
    except PluginNotInstalled as exc:
        raise HTTPException(404, str(exc)) from exc
    except PluginRegistryError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/runs")
async def list_runs(plugin_name: Optional[str] = Query(None),
                    limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return get_installed_plugin_registry().list_runs(plugin_name=plugin_name,
                                                      limit=limit)


@router.get("/{name}/runs")
@audit_pii("read", "plugin_runs", pii_fields=["name"], resource_id_arg="name")
async def list_runs_for_plugin(name: str,
                               limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return get_installed_plugin_registry().list_runs(plugin_name=name, limit=limit)