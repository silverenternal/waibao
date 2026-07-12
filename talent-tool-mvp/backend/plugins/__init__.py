"""Plugins SDK — public surface."""

from .sdk.base import (
    Plugin,
    PluginContext,
    PluginRegistry,
    PluginState,
    PluginType,
    get_plugin_registry,
)
from .sdk.loader import LoadResult, PluginLoader
from .sdk.manifest import (
    ManifestError,
    PluginManifest,
    load_entry_point,
    load_manifest_file,
    parse_manifest,
)
from .sdk.registry import (
    InstalledPlugin,
    InstalledPluginRegistry,
    PluginAlreadyInstalled,
    PluginNotInstalled,
    PluginRegistryError,
    RunRecord,
    get_installed_plugin_registry,
)
from .sdk.runner import (
    PluginLoadError,
    PluginPermissionError,
    PluginRunResult,
    PluginRunner,
)
from .sdk.sandbox import (
    BlockedImportError,
    FilesystemGuard,
    NetworkGuard,
    ResourceLimiter,
    SandboxConfig,
    SandboxError,
    compile_plugin_source,
    safe_import,
    sandboxed,
    try_compile_restricted,
)

__all__ = [
    # base
    "Plugin", "PluginContext", "PluginRegistry", "PluginState", "PluginType",
    "get_plugin_registry",
    # manifest
    "ManifestError", "PluginManifest",
    "load_entry_point", "load_manifest_file", "parse_manifest",
    # runner (legacy / direct execution)
    "PluginLoadError", "PluginPermissionError", "PluginRunResult", "PluginRunner",
    # T2104 additions
    "LoadResult", "PluginLoader",
    "InstalledPlugin", "InstalledPluginRegistry", "RunRecord",
    "PluginRegistryError", "PluginAlreadyInstalled", "PluginNotInstalled",
    "get_installed_plugin_registry",
    "BlockedImportError", "FilesystemGuard", "NetworkGuard", "ResourceLimiter",
    "SandboxConfig", "SandboxError",
    "compile_plugin_source", "safe_import", "sandboxed",
    "try_compile_restricted",
]