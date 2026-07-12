"""Tests for the plugin SDK."""

from __future__ import annotations

import textwrap

import pytest

from plugins import (
    Plugin,
    PluginContext,
    PluginManifest,
    PluginRunner,
    PluginType,
    get_plugin_registry,
    parse_manifest,
)
from plugins.sdk.manifest import ManifestError


# ---------------------------------------------------------------------------
# A minimal plugin
# ---------------------------------------------------------------------------

class EchoPlugin(Plugin):
    name = "echo"
    version = "1.0.0"
    author = "tests"
    description = "echoes input"
    permissions = ["db:read", "events:emit"]

    def install(self, ctx):  # noqa: D401
        self.state = "installed"  # type: ignore[assignment]

    def enable(self, ctx):
        self.state = "enabled"  # type: ignore[assignment]

    def get_agent(self): return None
    def get_service(self): return self
    def get_provider(self): return None
    def get_widget(self): return None

    def run(self, x):
        return {"echo": x}


class CrashingPlugin(Plugin):
    name = "crash"
    version = "0.1.0"
    permissions = ["db:read"]

    def install(self, ctx):
        raise RuntimeError("kaboom")

    def get_agent(self): return None
    def get_service(self): return None
    def get_provider(self): return None
    def get_widget(self): return None


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def test_manifest_validation_ok():
    m = parse_manifest({
        "name": "demo",
        "version": "1.2.3",
        "entry_point": "demo_pkg.main:DemoPlugin",
        "permissions": ["db:read", "events:emit"],
    })
    assert m.name == "demo"
    assert m.permissions == ["db:read", "events:emit"]


def test_manifest_validation_rejects_bad_version():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "x", "version": "not-semver",
                         "entry_point": "a:b"})


def test_manifest_validation_rejects_unknown_permission():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "x", "version": "1.0.0",
                         "entry_point": "a:b",
                         "permissions": ["rm-rf"]})


def test_manifest_validation_requires_fields():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "x"})


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def test_runner_installs_and_registers():
    get_plugin_registry().unregister("echo")
    runner = PluginRunner()
    manifest = PluginManifest(
        name="echo", version="1.0.0", entry_point="plugins.tests.test_plugins:EchoPlugin",
    )
    result = runner.install(manifest)
    assert result.success, result.error
    assert get_plugin_registry().get("echo") is not None
    get_plugin_registry().unregister("echo")


def test_runner_isolates_crashes():
    runner = PluginRunner()
    manifest = PluginManifest(
        name="crash", version="0.1.0",
        entry_point="plugins.tests.test_plugins:CrashingPlugin",
    )
    result = runner.install(manifest)
    assert not result.success
    assert result.error_type == "crash"
    assert "kaboom" in (result.error or "")


def test_runner_enforces_permissions():
    runner = PluginRunner(allowed_permissions=["db:read"])
    manifest = PluginManifest(
        name="echo", version="1.0.0",
        entry_point="plugins.tests.test_plugins:EchoPlugin",
        permissions=["db:read", "events:emit", "admin"],
    )
    result = runner.install(manifest)
    assert not result.success
    assert result.error_type == "permission"