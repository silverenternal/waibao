"""v6.0 T2104 — Persistent plugin registry.

Builds on top of the in-memory ``PluginRegistry`` from
``plugins.sdk.base`` and adds:

* persistent ``installed_plugins`` table (Supabase / Postgres) — survives
  process restart;
* an install / uninstall / enable / disable / run API;
* per-plugin permission enforcement;
* run history (success / failure counts) for diagnostics.

The global singleton is :func:`get_installed_plugin_registry`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .base import Plugin, PluginContext, PluginState, get_plugin_registry
from .loader import LoadResult, PluginLoader
from .manifest import ManifestError, PluginManifest, load_manifest_file
from .sandbox import SandboxConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PluginRegistryError(Exception):
    pass


class PluginAlreadyInstalled(PluginRegistryError):
    pass


class PluginNotInstalled(PluginRegistryError):
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class InstalledPlugin:
    name: str
    version: str
    manifest: Dict[str, Any]
    source_path: str
    state: str = PluginState.INSTALLED.value
    enabled_at: Optional[str] = None
    installed_at: Optional[str] = None
    installed_by: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    run_count: int = 0
    failure_count: int = 0
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    plugin_name: str
    status: str  # "success" | "crash" | "permission" | "timeout"
    duration_ms: float
    error: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Persistent storage — Supabase with in-memory fallback
# ---------------------------------------------------------------------------

class _Store:
    def __init__(self) -> None:
        self._installed: Dict[str, InstalledPlugin] = {}
        self._runs: List[RunRecord] = []
        self._lock = threading.RLock()
        self._remote = None
        self._init_remote()

    def _init_remote(self) -> None:
        url = os.environ.get("SUPABASE_URL") or os.environ.get("WAIBAO_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
            "WAIBAO_SUPABASE_KEY"
        )
        if not (url and key):
            return
        try:
            from supabase import create_client  # type: ignore

            self._remote = create_client(url, key)
            logger.info("plugin_registry: connected to Supabase")
        except Exception as exc:  # noqa: BLE001
            logger.warning("plugin_registry: Supabase unavailable (%s); using memory", exc)
            self._remote = None

    # ---- installed plugins ------------------------------------------------
    def list_installed(self) -> List[InstalledPlugin]:
        with self._lock:
            return list(self._installed.values())

    def get_installed(self, name: str) -> Optional[InstalledPlugin]:
        with self._lock:
            return self._installed.get(name)

    def upsert_installed(self, record: InstalledPlugin) -> InstalledPlugin:
        with self._lock:
            self._installed[record.name] = record
        return record

    def remove_installed(self, name: str) -> Optional[InstalledPlugin]:
        with self._lock:
            return self._installed.pop(name, None)

    # ---- run history ------------------------------------------------------
    def append_run(self, record: RunRecord) -> None:
        with self._lock:
            self._runs.append(record)
            # Trim to last 5000 to avoid unbounded growth in memory mode.
            if len(self._runs) > 5000:
                self._runs = self._runs[-5000:]

    def list_runs(self, plugin_name: Optional[str] = None,
                  limit: int = 100) -> List[RunRecord]:
        with self._lock:
            rows = [r for r in self._runs if not plugin_name or r.plugin_name == plugin_name]
        rows.sort(key=lambda r: r.created_at or "", reverse=True)
        return rows[:limit]


_store: Optional[_Store] = None


def _get_store() -> _Store:
    global _store
    if _store is None:
        _store = _Store()
    return _store


def reset_store_for_tests() -> None:
    global _store
    _store = None


# ---------------------------------------------------------------------------
# Persistent registry — admin surface
# ---------------------------------------------------------------------------

class InstalledPluginRegistry:
    """Process-wide singleton wrapping ``_store`` + the runtime PluginRegistry."""

    def __init__(self, *, sandbox: Optional[SandboxConfig] = None) -> None:
        self._sandbox = sandbox or SandboxConfig()
        self._loader = PluginLoader(sandbox=self._sandbox)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # install / uninstall
    # ------------------------------------------------------------------
    def install_from_directory(self, directory: str, *,
                               actor: Optional[str] = None) -> LoadResult:
        result = self._loader.load_from_directory(directory)
        if not result.success:
            return result
        return self._register(result, source_path=directory, actor=actor)

    def install_from_manifest(self, manifest_path: str, *,
                              actor: Optional[str] = None) -> LoadResult:
        try:
            manifest = load_manifest_file(manifest_path)
        except ManifestError as exc:
            return LoadResult(success=False, error=str(exc), error_type="manifest")

        directory = os.path.dirname(os.path.abspath(manifest_path))
        return self.install_from_directory(directory, actor=actor)

    def _register(self, result: LoadResult, *, source_path: str,
                  actor: Optional[str] = None) -> LoadResult:
        assert result.plugin is not None
        assert result.manifest is not None
        name = result.manifest.name
        with self._lock:
            existing = _get_store().get_installed(name)
            if existing and existing.state == PluginState.ENABLED.value:
                raise PluginAlreadyInstalled(
                    f"plugin {name!r} is enabled; disable it before re-installing"
                )
            record = InstalledPlugin(
                name=name,
                version=result.manifest.version,
                manifest=result.manifest.to_dict(),
                source_path=source_path,
                state=PluginState.INSTALLED.value,
                installed_at=_now_iso(),
                installed_by=actor,
            )
            _get_store().upsert_installed(record)
        # Also register with the runtime registry so get_plugin(name) finds it.
        # If a stale entry already exists (e.g. from a previous install),
        # unregister first so the re-install is idempotent.
        if get_plugin_registry().get(name) is not None:
            get_plugin_registry().unregister(name)
        get_plugin_registry().register(result.plugin)

        # Invoke the plugin's install() hook — wrapped in exception isolation
        # so a crashing install() doesn't take down the host.
        ctx = self._make_ctx(result.plugin)
        try:
            result.plugin.install(ctx)
        except PermissionError as exc:
            get_plugin_registry().unregister(name)
            _get_store().remove_installed(name)
            return LoadResult(success=False, manifest=result.manifest,
                              error=f"install permission denied: {exc}",
                              error_type="permission",
                              duration_ms=result.duration_ms)
        except Exception as exc:  # noqa: BLE001 — isolation
            get_plugin_registry().unregister(name)
            _get_store().remove_installed(name)
            return LoadResult(success=False, manifest=result.manifest,
                              error=str(exc), error_type="crash",
                              duration_ms=result.duration_ms)
        return result

    def uninstall(self, name: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            record = _get_store().get_installed(name)
            if record is None:
                raise PluginNotInstalled(f"plugin {name!r} is not installed")
            if record.state == PluginState.ENABLED.value:
                raise PluginRegistryError(
                    f"plugin {name!r} is enabled; disable it first"
                )
            _get_store().remove_installed(name)
        get_plugin_registry().unregister(name)
        return {"uninstalled": name, "actor": actor}

    # ------------------------------------------------------------------
    # enable / disable
    # ------------------------------------------------------------------
    def enable(self, name: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
        plugin = get_plugin_registry().get(name)
        record = _get_store().get_installed(name)
        if plugin is None or record is None:
            raise PluginNotInstalled(f"plugin {name!r} is not installed")
        ctx = self._make_ctx(plugin)
        try:
            plugin.enable(ctx)
        except PermissionError as exc:
            return {"enabled": False, "error": str(exc), "error_type": "permission"}
        except Exception as exc:  # noqa: BLE001
            plugin.state = PluginState.ERROR
            return {"enabled": False, "error": str(exc), "error_type": "crash"}

        record.state = PluginState.ENABLED.value
        record.enabled_at = _now_iso()
        _get_store().upsert_installed(record)
        return {"enabled": True, "name": name, "actor": actor}

    def disable(self, name: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
        plugin = get_plugin_registry().get(name)
        record = _get_store().get_installed(name)
        if plugin is None or record is None:
            raise PluginNotInstalled(f"plugin {name!r} is not installed")
        ctx = self._make_ctx(plugin)
        try:
            plugin.disable(ctx)
        except Exception:  # noqa: BLE001
            pass
        record.state = PluginState.DISABLED.value
        _get_store().upsert_installed(record)
        return {"disabled": True, "name": name, "actor": actor}

    # ------------------------------------------------------------------
    # run — execute the plugin's primary contribution
    # ------------------------------------------------------------------
    def run(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        plugin = get_plugin_registry().get(name)
        record = _get_store().get_installed(name)
        if plugin is None or record is None:
            raise PluginNotInstalled(f"plugin {name!r} is not installed")
        if record.state != PluginState.ENABLED.value:
            raise PluginRegistryError(
                f"plugin {name!r} is not enabled (state={record.state})"
            )
        ctx = self._make_ctx(plugin)
        started = time.time() * 1000.0
        try:
            output = self._invoke(plugin, ctx, payload or {})
            duration = time.time() * 1000.0 - started
            record.last_run_at = _now_iso()
            record.last_run_status = "success"
            record.run_count += 1
            _get_store().upsert_installed(record)
            _get_store().append_run(RunRecord(
                plugin_name=name, status="success",
                duration_ms=duration, created_at=_now_iso(),
            ))
            return {"success": True, "output": output,
                    "duration_ms": duration, "plugin": name}
        except PermissionError as exc:
            duration = time.time() * 1000.0 - started
            record.last_run_status = "permission"
            record.failure_count += 1
            _get_store().upsert_installed(record)
            _get_store().append_run(RunRecord(
                plugin_name=name, status="permission",
                duration_ms=duration, error=str(exc), created_at=_now_iso(),
            ))
            return {"success": False, "error": str(exc),
                    "error_type": "permission", "duration_ms": duration}
        except Exception as exc:  # noqa: BLE001
            duration = time.time() * 1000.0 - started
            record.last_run_status = "crash"
            record.failure_count += 1
            _get_store().upsert_installed(record)
            _get_store().append_run(RunRecord(
                plugin_name=name, status="crash",
                duration_ms=duration, error=str(exc), created_at=_now_iso(),
            ))
            return {"success": False, "error": str(exc),
                    "error_type": "crash", "duration_ms": duration}

    def _invoke(self, plugin: Plugin, ctx: PluginContext,
                payload: Dict[str, Any]) -> Any:
        """Invoke a plugin's primary contribution.

        Priority order: get_agent (call ``.run(payload)``) → get_service
        (call ``.handle(payload)``) → get_provider (call ``.provide(payload)``)
        → get_widget (return descriptor). Plugins may implement any subset.
        """
        agent = plugin.get_agent()
        if agent is not None and hasattr(agent, "run"):
            return agent.run(payload)
        service = plugin.get_service()
        if service is not None and hasattr(service, "handle"):
            return service.handle(payload)
        provider = plugin.get_provider()
        if provider is not None and hasattr(provider, "provide"):
            return provider.provide(payload)
        widget = plugin.get_widget()
        if widget is not None:
            return widget
        return {"noop": True, "plugin": plugin.name}

    def _make_ctx(self, plugin: Plugin) -> PluginContext:
        return PluginContext(
            plugin_name=plugin.name,
            db=None,
            event_bus=None,
            logger=logger.getChild(f"plugin.{plugin.name}"),
            config={},
            permissions=list(plugin.permissions),
        )

    # ------------------------------------------------------------------
    # list / history
    # ------------------------------------------------------------------
    def list_installed(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in _get_store().list_installed()]

    def get_installed(self, name: str) -> Optional[Dict[str, Any]]:
        rec = _get_store().get_installed(name)
        return rec.to_dict() if rec else None

    def list_runs(self, plugin_name: Optional[str] = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in _get_store().list_runs(plugin_name, limit)]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry_instance: Optional[InstalledPluginRegistry] = None


def get_installed_plugin_registry() -> InstalledPluginRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = InstalledPluginRegistry()
    return _registry_instance


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


__all__ = [
    "InstalledPlugin",
    "InstalledPluginRegistry",
    "RunRecord",
    "PluginRegistryError",
    "PluginAlreadyInstalled",
    "PluginNotInstalled",
    "get_installed_plugin_registry",
]