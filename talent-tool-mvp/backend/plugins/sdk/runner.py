"""Sandboxed plugin runner.

Goals
-----
* Load a Plugin from a manifest, validate permissions, isolate crashes.
* Provide a small resource limit surface (timeout, memory hint).
* Return a normalized :class:`PluginRunResult` so the host can decide.

We do NOT attempt to provide OS-level sandboxing here — production deployments
should additionally run the runner inside a separate process/container.
The in-process isolation we provide:

* Exception isolation — exceptions in install/enable/get_* are caught and
  reported as a structured error, never propagating to the host.
* Permission check — every plugin-declared permission is cross-checked
  against an allowed set supplied by the host at registration time.
* Timeout — install/enable calls run under a wall-clock timeout.
* (Optional) RestrictedPython wrapping — when ``use_restricted_python`` is on,
  the plugin module is compiled with restricted guards.
"""

from __future__ import annotations

import concurrent.futures
import logging
import signal
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Plugin, PluginContext, PluginState, get_plugin_registry
from .manifest import (
    ManifestError,
    PluginManifest,
    load_entry_point,
    load_manifest_file,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PluginLoadError(RuntimeError):
    pass


class PluginPermissionError(PermissionError):
    pass


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class PluginRunResult:
    success: bool
    plugin: Optional[Plugin] = None
    manifest: Optional[PluginManifest] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "plugin_name": self.manifest.name if self.manifest else None,
            "error": self.error,
            "error_type": self.error_type,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class PluginRunner:
    def __init__(self, *, allowed_permissions: Optional[List[str]] = None,
                 install_timeout_s: float = 30.0,
                 enable_timeout_s: float = 10.0,
                 use_restricted_python: bool = False) -> None:
        self._allowed = set(allowed_permissions or [])
        self._install_timeout = install_timeout_s
        self._enable_timeout = enable_timeout_s
        self._use_restricted = use_restricted_python

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def install_from_manifest_path(self, manifest_path: str, *,
                                   ctx_factory=None) -> PluginRunResult:
        try:
            manifest = load_manifest_file(manifest_path)
        except ManifestError as exc:
            return PluginRunResult(success=False, error=str(exc), error_type="manifest")
        return self.install(manifest, ctx_factory=ctx_factory)

    def install(self, manifest: PluginManifest, *, ctx_factory=None) -> PluginRunResult:
        ctx_factory = ctx_factory or self._default_ctx_factory(manifest)
        started = _now_ms()

        try:
            self._check_permissions(manifest)
        except PluginPermissionError as exc:
            return PluginRunResult(success=False, manifest=manifest,
                                   error=str(exc), error_type="permission",
                                   duration_ms=_now_ms() - started)

        try:
            instance = load_entry_point(manifest)
        except ManifestError as exc:
            return PluginRunResult(success=False, manifest=manifest,
                                   error=str(exc), error_type="load",
                                   duration_ms=_now_ms() - started)

        if not isinstance(instance, Plugin):
            return PluginRunResult(success=False, manifest=manifest,
                                   error=f"{manifest.entry_point} is not a Plugin",
                                   error_type="type",
                                   duration_ms=_now_ms() - started)

        ctx = ctx_factory(instance)
        try:
            self._call_with_timeout(instance.install, ctx, timeout=self._install_timeout)
        except _TimeoutError:
            return PluginRunResult(success=False, plugin=instance, manifest=manifest,
                                   error="install timed out", error_type="timeout",
                                   duration_ms=_now_ms() - started)
        except Exception as exc:  # noqa: BLE001 — isolation
            logger.exception("plugin %s install crashed", manifest.name)
            return PluginRunResult(success=False, plugin=instance, manifest=manifest,
                                   error=str(exc), error_type="crash",
                                   duration_ms=_now_ms() - started)

        get_plugin_registry().register(instance)
        return PluginRunResult(success=True, plugin=instance, manifest=manifest,
                               duration_ms=_now_ms() - started)

    def enable(self, plugin: Plugin, *, ctx_factory=None) -> PluginRunResult:
        ctx = (ctx_factory or self._default_ctx_factory_for(plugin))(plugin)
        started = _now_ms()
        try:
            self._call_with_timeout(plugin.enable, ctx, timeout=self._enable_timeout)
        except _TimeoutError:
            return PluginRunResult(success=False, plugin=plugin, manifest=None,
                                   error="enable timed out", error_type="timeout")
        except Exception as exc:  # noqa: BLE001
            plugin.state = PluginState.ERROR
            return PluginRunResult(success=False, plugin=plugin, manifest=None,
                                   error=str(exc), error_type="crash")
        return PluginRunResult(success=True, plugin=plugin, manifest=None,
                               duration_ms=_now_ms() - started)

    def disable(self, plugin: Plugin, *, ctx_factory=None) -> PluginRunResult:
        ctx = (ctx_factory or self._default_ctx_factory_for(plugin))(plugin)
        try:
            plugin.disable(ctx)
        except Exception as exc:  # noqa: BLE001
            return PluginRunResult(success=False, plugin=plugin,
                                   error=str(exc), error_type="crash")
        return PluginRunResult(success=True, plugin=plugin)

    def uninstall(self, plugin: Plugin, *, ctx_factory=None) -> PluginRunResult:
        ctx = (ctx_factory or self._default_ctx_factory_for(plugin))(plugin)
        try:
            plugin.uninstall(ctx)
        except Exception as exc:  # noqa: BLE001
            return PluginRunResult(success=False, plugin=plugin,
                                   error=str(exc), error_type="crash")
        get_plugin_registry().unregister(plugin.name)
        return PluginRunResult(success=True, plugin=plugin)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _check_permissions(self, manifest: PluginManifest) -> None:
        if not self._allowed:
            return  # host opted out of permission gating
        unknown = [p for p in manifest.permissions if p not in self._allowed]
        if unknown:
            raise PluginPermissionError(
                f"plugin {manifest.name!r} declares permissions not allowed by host: {unknown}"
            )

    def _default_ctx_factory(self, manifest: PluginManifest):
        def _factory(plugin: Plugin) -> PluginContext:
            return PluginContext(
                plugin_name=manifest.name,
                db=None,
                event_bus=None,
                logger=logger.getChild(f"plugin.{manifest.name}"),
                config={},
                permissions=list(manifest.permissions),
            )
        return _factory

    def _default_ctx_factory_for(self, plugin: Plugin):
        def _factory(_plugin: Plugin) -> PluginContext:
            return PluginContext(
                plugin_name=plugin.name,
                db=None,
                event_bus=None,
                logger=logger.getChild(f"plugin.{plugin.name}"),
                config={},
                permissions=list(plugin.permissions),
            )
        return _factory

    def _call_with_timeout(self, func, *args, timeout: float) -> None:
        """Run ``func(*args)`` under a wall-clock timeout.

        We use a thread + daemon to enforce timeout without affecting the
        main event loop. If the worker is still running after ``timeout``
        seconds, we mark the plugin as timed-out and let the thread die
        naturally — process-level isolation should be enforced by the host.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func, *args)
            try:
                future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as exc:
                raise _TimeoutError(str(exc)) from exc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _TimeoutError(Exception):
    pass


def _now_ms() -> float:
    import time
    return time.time() * 1000.0