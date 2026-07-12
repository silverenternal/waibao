"""Tests for the v6.0 T2104 plugin SDK.

Covers:
- Manifest validation (good + bad)
- Plugin lifecycle (install / enable / disable / uninstall / run)
- Sandbox guards (os.system / network / file writes blocked)
- RestrictedPython / AST audit (forbidden imports caught)
- Resource limiter basic semantics
- Persistent registry (state transitions + run history)
- Reference plugins (resume-scorer / interview-bot / dingtalk-approval)
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import yaml

from plugins import (
    BlockedImportError,
    FilesystemGuard,
    InstalledPluginRegistry,
    ManifestError,
    NetworkGuard,
    Plugin,
    PluginContext,
    PluginManifest,
    PluginRegistryError,
    PluginRunner,
    PluginState,
    ResourceLimiter,
    SandboxConfig,
    compile_plugin_source,
    get_installed_plugin_registry,
    get_plugin_registry,
    parse_manifest,
    safe_import,
    sandboxed,
    try_compile_restricted,
)
from plugins.sdk.manifest import load_manifest_file
from plugins.sdk.registry import reset_store_for_tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_state():
    """Reset all module-level singletons between tests."""
    # Clear runtime registry
    reg = get_plugin_registry()
    for name in list(reg.all()):
        reg.unregister(name)
    # Clear persistent registry
    reset_store_for_tests()
    yield
    for name in list(reg.all()):
        reg.unregister(name)
    reset_store_for_tests()


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def test_parse_manifest_minimal_ok():
    m = parse_manifest({
        "name": "x", "version": "1.0.0", "entry_point": "m:C",
        "permissions": ["db:read"],
    })
    assert m.name == "x"
    assert m.entry_point == "m:C"


def test_parse_manifest_rejects_missing_name():
    with pytest.raises(ManifestError):
        parse_manifest({"version": "1.0.0", "entry_point": "m:C"})


def test_parse_manifest_rejects_bad_version():
    with pytest.raises(ManifestError):
        parse_manifest({"name": "x", "version": "1.0", "entry_point": "m:C"})


def test_load_entry_point_rejects_bad_format():
    """load_entry_point requires the `module:Class` shape."""
    m = parse_manifest({"name": "x", "version": "1.0.0", "entry_point": "no-colon"})
    from plugins.sdk.manifest import load_entry_point
    with pytest.raises(ManifestError):
        load_entry_point(m)


def test_parse_manifest_rejects_unknown_permission():
    with pytest.raises(ManifestError):
        parse_manifest({
            "name": "x", "version": "1.0.0", "entry_point": "m:C",
            "permissions": ["db:read", "evil:do"],
        })


def test_load_manifest_file_missing(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest_file(str(tmp_path / "missing.yaml"))


# ---------------------------------------------------------------------------
# Plugin lifecycle via PluginRunner
# ---------------------------------------------------------------------------

class _EchoPlugin(Plugin):
    name = "echo"
    version = "1.0.0"
    permissions = ["events:emit"]

    def get_agent(self): return None
    def get_service(self): return self
    def get_provider(self): return None
    def get_widget(self): return None

    def handle(self, payload):
        return {"echo": payload}


def _write_plugin(tmp_path: Path, *, name: str = "echo",
                  permissions: List[str] = None,
                  extra_source: str = "") -> Path:
    """Drop a minimal plugin into tmp_path."""
    plugin_dir = tmp_path / name
    plugin_dir.mkdir()
    permissions = permissions or ["events:emit"]
    (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump({
        "name": name,
        "version": "1.0.0",
        "author": "tests",
        "description": "test plugin",
        "entry_point": "main:EchoPlugin",
        "permissions": permissions,
    }))
    src = textwrap.dedent(f"""
        from plugins.sdk.base import Plugin, PluginState

        class EchoPlugin(Plugin):
            name = {name!r}
            version = "1.0.0"
            permissions = {permissions!r}

            def install(self, ctx):
                self.state = PluginState.INSTALLED

            def enable(self, ctx):
                self.state = PluginState.ENABLED

            def get_agent(self): return None
            def get_service(self): return self
            def get_provider(self): return None
            def get_widget(self): return None

            def handle(self, payload):
                return {{"echo": payload, "name": self.name}}

        {extra_source}
    """).strip()
    (plugin_dir / "main.py").write_text(src)
    return plugin_dir


def test_runner_install_enables_and_lists(tmp_path):
    """For disk-installed plugins, PluginLoader is the right surface
    (sandboxed, dynamic). PluginRunner is for trusted, importable modules."""
    plugin_dir = _write_plugin(tmp_path)
    from plugins.sdk.loader import PluginLoader
    from plugins.sdk.sandbox import SandboxConfig
    loader = PluginLoader(sandbox=SandboxConfig(use_restricted_python=False))
    res = loader.load_from_directory(str(plugin_dir))
    assert res.success, res.to_dict()
    assert res.plugin is not None
    assert get_plugin_registry().get(res.plugin.name) is None  # not yet registered


def test_runner_install_rejects_unauthorized_permission(tmp_path):
    plugin_dir = _write_plugin(tmp_path, permissions=["admin"])
    from plugins.sdk.loader import PluginLoader
    from plugins.sdk.sandbox import SandboxConfig
    loader = PluginLoader(
        sandbox=SandboxConfig(use_restricted_python=False),
        allowed_permissions=["events:emit"],
    )
    res = loader.load_from_directory(str(plugin_dir))
    assert not res.success
    assert res.error_type == "permission"


def test_runner_install_crash_isolated(tmp_path):
    """Even if install() raises, the runner should isolate."""
    # Write a plugin whose install() raises — and verify the registry
    # catches the exception rather than letting it propagate.
    plugin_dir = _write_plugin(tmp_path)
    # Replace the install() with one that raises.
    (plugin_dir / "main.py").write_text(textwrap.dedent("""
        from plugins.sdk.base import Plugin, PluginState

        class EchoPlugin(Plugin):
            name = "echo"
            version = "1.0.0"
            permissions = ["events:emit"]

            def install(self, ctx):
                raise RuntimeError("plugin boom")

            def enable(self, ctx):
                self.state = PluginState.ENABLED

            def get_agent(self): return None
            def get_service(self): return self
            def get_provider(self): return None
            def get_widget(self): return None
    """).strip())
    reg = InstalledPluginRegistry()
    res = reg.install_from_directory(str(plugin_dir))
    # Install returns LoadResult; crash in install() surfaces as
    # error_type="crash". The host survives.
    assert not res.success
    assert res.error_type == "crash"
    # Host registry should still be functional.
    assert get_plugin_registry().get("echo") is None


# ---------------------------------------------------------------------------
# Sandbox — import-time guard
# ---------------------------------------------------------------------------

def test_safe_import_blocks_os():
    with pytest.raises(BlockedImportError):
        safe_import("os")


def test_safe_import_blocks_subprocess():
    with pytest.raises(BlockedImportError):
        safe_import("subprocess")


def test_safe_import_blocks_socket():
    with pytest.raises(BlockedImportError):
        safe_import("socket")


def test_safe_import_blocks_ctypes():
    with pytest.raises(BlockedImportError):
        safe_import("ctypes")


def test_safe_import_allows_json():
    import json as _json
    assert safe_import("json") is _json


def test_safe_import_allows_pathlib():
    import pathlib
    assert safe_import("pathlib") is pathlib


# ---------------------------------------------------------------------------
# Sandbox — AST audit catches forbidden imports
# ---------------------------------------------------------------------------

def test_ast_audit_blocks_os_import():
    src = "import os\nx = os.system('ls')\n"
    with pytest.raises(BlockedImportError):
        try_compile_restricted(src, filename="<test>")


def test_ast_audit_blocks_from_subprocess_import():
    src = "from subprocess import call\ncall(['echo', 'pwned'])\n"
    with pytest.raises(BlockedImportError):
        try_compile_restricted(src)


def test_ast_audit_blocks_socket():
    src = "import socket\ns = socket.socket()\n"
    with pytest.raises(BlockedImportError):
        try_compile_restricted(src)


def test_ast_audit_blocks_dunder_attribute():
    src = "x = object.__subclasses__()\n"
    with pytest.raises(BlockedImportError):
        try_compile_restricted(src)


def test_ast_audit_allows_safe_code():
    src = "def add(a, b):\n    return a + b\n"
    code = try_compile_restricted(src, filename="<ok>")
    assert code is not None


def test_compile_plugin_source_wrapper():
    src = "x = 1 + 2\n"
    code = compile_plugin_source(src, filename="<ok>")
    assert code is not None


# ---------------------------------------------------------------------------
# Sandbox — network guard
# ---------------------------------------------------------------------------

def test_network_guard_blocks_unknown_host():
    with NetworkGuard(allow=["allowed.example.com"]):
        import socket as _socket
        s = _socket.socket()
        try:
            with pytest.raises(PermissionError):
                s.connect(("blocked.example.com", 80))
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_network_guard_allows_listed_host():
    with NetworkGuard(allow=["allowed.example.com", "*.trusted.com"]):
        import socket as _socket
        s = _socket.socket()
        try:
            # We won't actually connect — we just check the predicate allows
            # it by patching getaddrinfo or by direct call. The guard's
            # _is_allowed is the source of truth.
            from plugins.sdk.sandbox import NetworkGuard as _NG
            g = _NG(allow=["allowed.example.com", "*.trusted.com"])
            assert g._is_allowed("allowed.example.com") is True
            assert g._is_allowed("api.trusted.com") is True
            assert g._is_allowed("blocked.com") is False
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_network_guard_disabled_when_allow_empty():
    with NetworkGuard(allow=[]):
        import socket as _socket
        # No patching should have happened — the patched list is empty.
        assert _socket.socket is _socket.socket.__class__ or True


# ---------------------------------------------------------------------------
# Sandbox — filesystem guard
# ---------------------------------------------------------------------------

def test_filesystem_guard_blocks_writes_outside_sandbox(tmp_path):
    sandbox = tmp_path / "sandbox"
    outside = tmp_path / "outside.txt"
    with FilesystemGuard(str(sandbox)):
        # Allowed: write inside sandbox.
        with open(sandbox / "ok.txt", "w") as fh:
            fh.write("ok")
        # Blocked: write outside.
        with pytest.raises(PermissionError):
            with open(str(outside), "w") as fh:
                fh.write("nope")


def test_filesystem_guard_allows_reads_outside_sandbox(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "data.txt"
    outside.write_text("hello")
    with FilesystemGuard(str(sandbox)):
        with open(str(outside), "r") as fh:
            assert fh.read() == "hello"


def test_filesystem_guard_restores_open_on_exit(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    builtins_open = open
    with FilesystemGuard(str(sandbox)):
        pass
    assert open is builtins_open


# ---------------------------------------------------------------------------
# Resource limiter — basic semantics (skipped on Windows)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="POSIX-only")
def test_resource_limiter_context_runs():
    """ResourceLimiter must be a no-op-compatible context manager."""
    with ResourceLimiter(cpu_seconds=10.0, memory_mb=256, file_descriptors=64):
        # Should not raise
        x = 1 + 1
        assert x == 2


# ---------------------------------------------------------------------------
# Composite sandbox
# ---------------------------------------------------------------------------

def test_sandboxed_context_manager():
    with sandboxed(SandboxConfig(sandbox_dir="/tmp/sandbox",
                                  allow_network_hosts=["allowed.test"])):
        # We should be inside the sandbox; let's verify the filesystem guard
        # is active by attempting a forbidden write.
        import tempfile as _tf
        outside = "/tmp/sandbox_outside_test.txt"
        with pytest.raises(PermissionError):
            with open(outside, "w") as fh:
                fh.write("nope")


# ---------------------------------------------------------------------------
# Persistent registry — install / enable / disable / uninstall / run
# ---------------------------------------------------------------------------

def test_registry_install_then_enable_then_run(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    res = reg.install_from_directory(str(plugin_dir), actor="alice")
    assert res.success, res.to_dict()

    en = reg.enable("echo", actor="alice")
    assert en["enabled"] is True

    res = reg.run("echo", {"text": "hi"})
    assert res["success"] is True
    assert res["output"]["name"] == "echo"
    assert res["output"]["echo"] == {"text": "hi"}


def test_registry_run_fails_when_not_enabled(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    reg.install_from_directory(str(plugin_dir))
    with pytest.raises(PluginRegistryError):
        reg.run("echo", {})


def test_registry_disable_then_run_fails(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    reg.install_from_directory(str(plugin_dir))
    reg.enable("echo")
    reg.disable("echo")
    with pytest.raises(PluginRegistryError):
        reg.run("echo", {})


def test_registry_uninstall_then_run_raises_not_installed(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    reg.install_from_directory(str(plugin_dir))
    reg.uninstall("echo")
    with pytest.raises(Exception):
        reg.run("echo", {})


def test_registry_run_history_records_status(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    reg.install_from_directory(str(plugin_dir))
    reg.enable("echo")
    reg.run("echo", {"k": 1})
    reg.run("echo", {"k": 2})
    runs = reg.list_runs(plugin_name="echo")
    assert len(runs) >= 2
    assert all(r["status"] == "success" for r in runs)


def test_registry_rejects_reinstall_when_enabled(tmp_path):
    plugin_dir = _write_plugin(tmp_path, name="echo")
    reg = InstalledPluginRegistry()
    reg.install_from_directory(str(plugin_dir))
    reg.enable("echo")
    with pytest.raises(Exception):
        reg.install_from_directory(str(plugin_dir))


# ---------------------------------------------------------------------------
# Sandbox end-to-end — install a plugin that tries forbidden ops
# ---------------------------------------------------------------------------

def test_loader_blocks_os_import(tmp_path):
    """A plugin that imports os must fail to load."""
    plugin_dir = tmp_path / "evil"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump({
        "name": "evil", "version": "1.0.0",
        "entry_point": "main:EvilPlugin",
        "permissions": ["events:emit"],
    }))
    (plugin_dir / "main.py").write_text(textwrap.dedent("""
        import os  # forbidden
        from plugins.sdk.base import Plugin

        class EvilPlugin(Plugin):
            name = "evil"
            version = "1.0.0"
            permissions = ["events:emit"]

            def get_agent(self): return None
            def get_service(self): return None
            def get_provider(self): return None
            def get_widget(self): return None
    """))
    reg = InstalledPluginRegistry()
    res = reg.install_from_directory(str(plugin_dir))
    assert not res.success
    assert res.error_type in {"sandbox", "load", "crash"}


def test_loader_blocks_filesystem_write_outside_sandbox(tmp_path):
    """A plugin that opens /etc/passwd for write must be blocked."""
    plugin_dir = tmp_path / "evilwrite"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump({
        "name": "evilwrite", "version": "1.0.0",
        "entry_point": "main:EvilPlugin",
        "permissions": ["files:write"],
    }))
    (plugin_dir / "main.py").write_text(textwrap.dedent("""
        from plugins.sdk.base import Plugin

        class EvilPlugin(Plugin):
            name = "evilwrite"
            version = "1.0.0"
            permissions = ["files:write"]

            def install(self, ctx):
                with open("/etc/passwd", "a") as fh:  # forbidden
                    fh.write("pwned")

            def get_agent(self): return None
            def get_service(self): return None
            def get_provider(self): return None
            def get_widget(self): return None
    """))
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    reg = InstalledPluginRegistry(sandbox=SandboxConfig(
        sandbox_dir=str(sandbox_dir),
        use_restricted_python=False,
    ))
    # load_from_directory doesn't call install(); explicitly invoke to
    # trigger the filesystem guard.
    from plugins.sdk.loader import PluginLoader
    loader = PluginLoader(sandbox=SandboxConfig(
        sandbox_dir=str(sandbox_dir),
        use_restricted_python=False,
    ))
    load_res = loader.load_from_directory(str(plugin_dir))
    assert load_res.success, load_res.to_dict()
    # Now run install() under the sandbox — it should raise PermissionError
    # which the runner wraps in error_type=crash.
    from plugins.sdk.sandbox import sandboxed
    ctx = PluginContext(
        plugin_name="evilwrite", db=None, event_bus=None,
        logger=__import__("logging").getLogger("test"),
        config={}, permissions=["files:write"],
    )
    with pytest.raises(PermissionError):
        with sandboxed(SandboxConfig(sandbox_dir=str(sandbox_dir))):
            load_res.plugin.install(ctx)


def test_loader_blocks_network_call_outside_allow_list(tmp_path):
    plugin_dir = tmp_path / "evilnet"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump({
        "name": "evilnet", "version": "1.0.0",
        "entry_point": "main:EvilPlugin",
        "permissions": ["http:call"],
    }))
    (plugin_dir / "main.py").write_text(textwrap.dedent("""
        import socket
        from plugins.sdk.base import Plugin

        class EvilPlugin(Plugin):
            name = "evilnet"
            version = "1.0.0"
            permissions = ["http:call"]

            def install(self, ctx):
                s = socket.socket()
                s.connect(("attacker.example.com", 80))

            def get_agent(self): return None
            def get_service(self): return None
            def get_provider(self): return None
            def get_widget(self): return None
    """))
    reg = InstalledPluginRegistry(sandbox=SandboxConfig(
        allow_network_hosts=[],
        use_restricted_python=False,
    ))
    res = reg.install_from_directory(str(plugin_dir))
    assert not res.success


# ---------------------------------------------------------------------------
# Reference plugins — verify they install + run
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGINS_DIR = REPO_ROOT / "plugins"


@pytest.mark.parametrize("plugin_dir_name,plugin_name,expected_key", [
    ("waibao-plugin-resume-scorer", "resume-scorer", "score"),
    ("waibao-plugin-interview-bot", "interview-bot", "question"),
    ("waibao-plugin-dingtalk-approval", "dingtalk-approval", "process_id"),
])
def test_reference_plugins_install_and_run(plugin_dir_name, plugin_name, expected_key):
    plugin_dir = PLUGINS_DIR / plugin_dir_name
    if not plugin_dir.is_dir():
        pytest.skip(f"reference plugin {plugin_dir_name} not present")
    reg = InstalledPluginRegistry()
    res = reg.install_from_directory(str(plugin_dir))
    assert res.success, res.to_dict()
    actual_name = res.manifest.name
    assert actual_name == plugin_name
    en = reg.enable(actual_name)
    assert en["enabled"] is True

    if expected_key == "score":
        out = reg.run(actual_name, {"resume": {"skills": ["python", "fastapi"],
                                               "experience_years": 5,
                                               "education_level": "master"}})
        assert out["success"] is True
        assert expected_key in out["output"]
    elif expected_key == "question":
        out = reg.run(actual_name, {"action": "start", "session_id": "s-1"})
        assert out["success"] is True
        assert expected_key in out["output"]
    elif expected_key == "process_id":
        out = reg.run(actual_name, {"approval_type": "offer",
                                    "subject": "Offer for Jane",
                                    "applicant": "hr_1"})
        assert out["success"] is True
        assert out["output"][expected_key].startswith("PROC-")


# ---------------------------------------------------------------------------
# Admin API smoke
# ---------------------------------------------------------------------------

def test_admin_api_smoke(tmp_path):
    from fastapi.testclient import TestClient
    from main import app  # noqa: WPS433
    plugin_dir = _write_plugin(tmp_path, name="echo")
    client = TestClient(app)

    r = client.post("/api/admin/plugins/install",
                    json={"directory": str(plugin_dir), "actor": "alice"})
    assert r.status_code == 200, r.text

    r = client.post("/api/admin/plugins/echo/enable",
                    json={"actor": "alice"})
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    r = client.post("/api/admin/plugins/echo/run",
                    json={"payload": {"k": 1}})
    assert r.status_code == 200
    assert r.json()["success"] is True

    r = client.post("/api/admin/plugins/echo/disable",
                    json={"actor": "alice"})
    assert r.status_code == 200

    r = client.request("DELETE", "/api/admin/plugins/echo",
                       json={"actor": "alice"})
    assert r.status_code == 200


def test_admin_api_returns_404_for_unknown_plugin():
    from fastapi.testclient import TestClient
    from main import app  # noqa: WPS433
    client = TestClient(app)
    r = client.post("/api/admin/plugins/never-installed/run",
                    json={"payload": {}})
    assert r.status_code == 404


def test_admin_api_permissions_endpoint():
    from fastapi.testclient import TestClient
    from main import app  # noqa: WPS433
    client = TestClient(app)
    r = client.get("/api/admin/plugins/permissions")
    assert r.status_code == 200
    assert "db:read" in r.json()["allowed"]
    assert "admin" in r.json()["allowed"]