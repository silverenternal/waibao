"""v6.0 T2104 — Plugin loader.

Loads a plugin from a directory or from a ``plugin.yaml`` path, optionally
applying sandbox guards at install / enable time.

The loader is *not* the same as :func:`load_entry_point` (which only
imports a module — useful for trusted, in-process plugins). The loader
is the surface used by the admin install endpoint and by the boot
bootstrapper to load third-party plugins.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Plugin
from .manifest import (
    ManifestError,
    PluginManifest,
    load_manifest_file,
)
from .sandbox import (
    BlockedImportError,
    SandboxConfig,
    compile_plugin_source,
    safe_import,
    sandboxed,
)

logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    success: bool
    plugin: Optional[Plugin] = None
    manifest: Optional[PluginManifest] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "plugin_name": self.manifest.name if self.manifest else None,
            "error": self.error,
            "error_type": self.error_type,
            "duration_ms": self.duration_ms,
        }


class PluginLoader:
    def __init__(self, *, sandbox: Optional[SandboxConfig] = None,
                 extra_blocked_modules: Optional[List[str]] = None,
                 allowed_permissions: Optional[List[str]] = None) -> None:
        self._sandbox = sandbox or SandboxConfig()
        self._extra_blocked = set(extra_blocked_modules or [])
        self._allowed_perms = set(allowed_permissions or [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_from_directory(self, directory: str) -> LoadResult:
        """Load a plugin from a directory containing ``plugin.yaml``."""
        import time as _t

        manifest_path = os.path.join(directory, "plugin.yaml")
        started = _t.time() * 1000.0
        try:
            manifest = load_manifest_file(manifest_path)
        except ManifestError as exc:
            return LoadResult(success=False, error=str(exc), error_type="manifest",
                              duration_ms=_t.time() * 1000.0 - started)

        module_path = self._find_module_path(directory, manifest.entry_point)
        if module_path is None:
            return LoadResult(success=False, manifest=manifest,
                              error=f"entry_point module not found: {manifest.entry_point}",
                              error_type="load", duration_ms=_t.time() * 1000.0 - started)

        return self.load(manifest, module_path=module_path, source_dir=directory,
                         started=started)

    def load(self, manifest: PluginManifest, *, module_path: str,
             source_dir: str, started: Optional[float] = None) -> LoadResult:
        """Load the entry point referenced by the manifest.

        ``module_path`` is the absolute path to the ``.py`` file containing
        the Plugin class. ``source_dir`` is added to ``sys.path`` for the
        duration of the import.
        """
        import time as _t

        if started is None:
            started = _t.time() * 1000.0

        module_name, _, class_name = manifest.entry_point.partition(":")
        if not module_name or not class_name:
            return LoadResult(success=False, manifest=manifest,
                              error=f"bad entry_point {manifest.entry_point!r}",
                              error_type="manifest",
                              duration_ms=_t.time() * 1000.0 - started)

        # Permission gate — install-time check against the host's allow-list.
        if self._allowed_perms:
            unknown = [p for p in manifest.permissions if p not in self._allowed_perms]
            if unknown:
                return LoadResult(success=False, manifest=manifest,
                                  error=f"permissions not allowed by host: {unknown}",
                                  error_type="permission",
                                  duration_ms=_t.time() * 1000.0 - started)

        try:
            instance = self._import_module(manifest, module_path,
                                           module_name, source_dir, class_name)
        except BlockedImportError as exc:
            return LoadResult(success=False, manifest=manifest, error=str(exc),
                              error_type="sandbox",
                              duration_ms=_t.time() * 1000.0 - started)
        except Exception as exc:  # noqa: BLE001
            logger.exception("plugin load crashed")
            return LoadResult(success=False, manifest=manifest, error=str(exc),
                              error_type="crash",
                              duration_ms=_t.time() * 1000.0 - started)

        if not isinstance(instance, Plugin):
            return LoadResult(success=False, manifest=manifest,
                              error=f"{manifest.entry_point} is not a Plugin subclass",
                              error_type="type",
                              duration_ms=_t.time() * 1000.0 - started)

        return LoadResult(success=True, plugin=instance, manifest=manifest,
                          duration_ms=_t.time() * 1000.0 - started)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _find_module_path(self, directory: str, entry_point: str) -> Optional[str]:
        """Translate ``module.path:Class`` to a real file path under
        ``directory``. We look for both ``module/path.py`` and a top-level
        ``module.py``.
        """
        module_name, _, _ = entry_point.partition(":")
        if not module_name:
            return None

        parts = module_name.split(".")
        # Try /dir/module/path.py
        candidate = os.path.join(directory, *parts) + ".py"
        if os.path.isfile(candidate):
            return candidate
        # Try /dir/module/path/__init__.py
        candidate_pkg = os.path.join(directory, *parts, "__init__.py")
        if os.path.isfile(candidate_pkg):
            return candidate_pkg
        # Fallback: top-level module file
        top = os.path.join(directory, parts[-1] + ".py")
        if os.path.isfile(top):
            return top
        return None

    def _import_module(self, manifest: PluginManifest, module_path: str,
                       module_name: str, source_dir: str, class_name: str) -> Any:
        """Import a plugin module under the sandbox guards.

        We use ``importlib.util.spec_from_file_location`` to avoid polluting
        ``sys.modules`` with the plugin's top-level name (each install gets
        its own copy). The sandbox patches ``__import__`` to block forbidden
        modules.
        """
        import time as _t
        started = _t.time() * 1000.0

        spec = importlib.util.spec_from_file_location(
            f"waibao_plugin.{manifest.name}.{int(started)}", module_path
        )
        if spec is None or spec.loader is None:
            raise ManifestError(f"could not build import spec for {module_path}")

        module = importlib.util.module_from_spec(spec)

        # Compose a hardened globals dict for the plugin module.
        safe_globals: Dict[str, Any] = {
            "__name__": module_name,
            "__file__": module_path,
            "__builtins__": _safe_builtins(self._sandbox.use_restricted_python,
                                           extra={"__import__": safe_import}),
        }
        # Inject Plugin base + PluginContext so the plugin can subclass them
        # without re-implementing the import dance.
        from .base import Plugin as _Plugin, PluginContext as _PluginContext
        safe_globals["Plugin"] = _Plugin
        safe_globals["PluginContext"] = _PluginContext
        safe_globals["PluginState"] = getattr(
            importlib.import_module("plugins.sdk.base"), "PluginState"
        )
        safe_globals["PluginType"] = getattr(
            importlib.import_module("plugins.sdk.base"), "PluginType"
        )

        prev_path = sys.path.copy()
        sys.path.insert(0, source_dir)
        try:
            # Compile under restricted guards (if enabled) before exec.
            if self._sandbox.use_restricted_python:
                with open(module_path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                code = compile_plugin_source(source, filename=module_path,
                                             use_restricted=True)
            else:
                with open(module_path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                code = compile(source, module_path, "exec")

            with sandboxed(self._sandbox):
                exec(code, safe_globals)
        finally:
            try:
                sys.path.remove(source_dir)
            except ValueError:
                pass
            # Restore sys.path to the original state.
            sys.path[:] = prev_path

        cls = safe_globals.get(class_name)
        if cls is None:
            # The class may have been defined under a different scope; look
            # at the module attributes we just exec'd.
            cls = getattr(module, class_name, None)
        if cls is None:
            raise ManifestError(f"{class_name} not found in {module_path}")
        return cls()


def _safe_builtins(restricted: bool, *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a builtin namespace safe for plugin modules.

    When ``restricted`` is True, dangerous builtins are stripped — but we
    re-inject a safe ``__import__`` (see ``safe_import``) so plugin code can
    still ``import`` whitelisted modules. ``extra`` overrides or adds
    arbitrary entries (used to inject ``__import__``).
    """
    import builtins

    safe: Dict[str, Any] = {}
    blocked = set()
    if restricted:
        blocked = {
            "compile", "exec", "eval", "open", "input",
            "globals", "locals", "vars", "getattr", "setattr", "delattr",
            "breakpoint", "memoryview",
        }
    for name in dir(builtins):
        if name in blocked:
            continue
        safe[name] = getattr(builtins, name)
    if extra:
        safe.update(extra)
    return safe


__all__ = ["PluginLoader", "LoadResult"]