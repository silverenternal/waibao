"""plugin.yaml manifest parser for the plugin SDK."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # manifest parsing requires PyYAML; explicit error raised below


# Strict semver-ish regex. We don't enforce the whole spec — just basic shape.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([\-+][\w.]+)?$")
# Allowed permission tokens — anything else triggers a validation error.
_VALID_PERMS = {
    "db:read", "db:write",
    "events:emit", "events:subscribe",
    "http:call", "http:listen",
    "files:read", "files:write",
    "llm:call",
    "metrics:emit",
    "admin",
}


@dataclass
class PluginManifest:
    name: str
    version: str
    entry_point: str
    type: str = "agent"
    author: str = "unknown"
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "entry_point": self.entry_point,
            "type": self.type, "author": self.author, "description": self.description,
            "permissions": list(self.permissions), "config_schema": dict(self.config_schema),
            "dependencies": list(self.dependencies), "source_path": self.source_path,
        }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ManifestError(ValueError):
    """Raised when a plugin.yaml is malformed or fails validation."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _require_yaml() -> None:
    if yaml is None:  # pragma: no cover
        raise ManifestError("PyYAML is required for plugin manifests: pip install pyyaml")


def parse_manifest(data: Dict[str, Any], *, source_path: str = "") -> PluginManifest:
    """Validate and convert a raw dict (loaded from plugin.yaml) into a
    PluginManifest instance."""
    _require_yaml()

    if not isinstance(data, dict):
        raise ManifestError("plugin manifest must be a mapping")

    name = data.get("name")
    version = data.get("version")
    entry_point = data.get("entry_point") or data.get("entry")

    if not name or not isinstance(name, str):
        raise ManifestError("manifest.name is required (str)")
    if not version or not _VERSION_RE.match(str(version)):
        raise ManifestError(f"manifest.version {version!r} is not valid semver")
    if not entry_point or not isinstance(entry_point, str):
        raise ManifestError("manifest.entry_point is required (str)")

    permissions = data.get("permissions") or []
    if not isinstance(permissions, list):
        raise ManifestError("manifest.permissions must be a list")
    bad = [p for p in permissions if p not in _VALID_PERMS]
    if bad:
        raise ManifestError(f"manifest.permissions contains invalid tokens: {bad}")

    return PluginManifest(
        name=name,
        version=str(version),
        entry_point=entry_point,
        type=str(data.get("type", "agent")),
        author=str(data.get("author", "unknown")),
        description=str(data.get("description", "")),
        permissions=list(permissions),
        config_schema=dict(data.get("config_schema") or {}),
        dependencies=list(data.get("dependencies") or []),
        source_path=source_path,
    )


def load_manifest_file(path: str) -> PluginManifest:
    _require_yaml()
    if not os.path.isfile(path):
        raise ManifestError(f"manifest file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return parse_manifest(raw or {}, source_path=path)


def load_entry_point(manifest: PluginManifest) -> Any:
    """Import `module:attr` and return the resolved Plugin subclass instance.

    The runner wraps this in exception isolation, so any import error is
    surfaced as a PluginLoadError (caught by the runner).
    """
    module_name, _, attr = manifest.entry_point.partition(":")
    if not module_name or not attr:
        raise ManifestError(
            f"manifest.entry_point must be 'module.path:Class' — got {manifest.entry_point!r}"
        )
    import importlib
    module = importlib.import_module(module_name)
    cls = getattr(module, attr, None)
    if cls is None:
        raise ManifestError(f"{module_name}.{attr} not found")
    if not isinstance(cls, type):
        raise ManifestError(f"{module_name}.{attr} must be a class")
    return cls()