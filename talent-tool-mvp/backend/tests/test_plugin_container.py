"""T5023 — plugin container sandbox + cross-platform compat tests."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from plugins.sdk.compat import (  # noqa: E402
    OS,
    TimeoutError as CompatTimeout,
    current_platform,
    detect_platform,
    native_arch_suffix,
    native_timeout,
    normalize_line_endings,
    plugin_cache_dir,
)
from plugins.sdk.sandbox_v2 import (  # noqa: E402
    ContainerPluginRunner,
    SandboxError,
)


# ---------------------------------------------------------------------------
# Container sandbox (subprocess fallback path)
# ---------------------------------------------------------------------------

SIMPLE_CODE = (
    "import os, json\n"
    "payload = json.loads(os.environ.get('WAIBAO_PAYLOAD', '{}'))\n"
    "print(json.dumps({'echo': payload}))\n"
)


def test_container_runner_executes_plugin_and_returns_output():
    runner = ContainerPluginRunner(timeout_s=10)
    # Force the subprocess backend so we don't require a docker daemon.
    os.environ["WAIBAO_DISABLE_DOCKER"] = "1"
    try:
        result = runner.run(SIMPLE_CODE, {"hello": "world"})
    finally:
        os.environ.pop("WAIBAO_DISABLE_DOCKER", None)
    assert result.backend == "subprocess"
    assert result.ok, result.stderr
    assert "hello" in result.stdout


def test_container_runner_enforces_timeout():
    runner = ContainerPluginRunner(timeout_s=1.0)
    os.environ["WAIBAO_DISABLE_DOCKER"] = "1"
    try:
        result = runner.run("import time\nwhile True:\n    time.sleep(0.1)", None)
    finally:
        os.environ.pop("WAIBAO_DISABLE_DOCKER", None)
    assert result.timed_out is True
    assert result.exit_code != 0
    assert result.duration_s < 5.0  # killed near the deadline, not after


def test_container_runner_captures_failure_exit_code():
    runner = ContainerPluginRunner(timeout_s=10)
    os.environ["WAIBAO_DISABLE_DOCKER"] = "1"
    try:
        result = runner.run("import sys; sys.exit(3)", None)
    finally:
        os.environ.pop("WAIBAO_DISABLE_DOCKER", None)
    assert result.exit_code == 3
    assert not result.ok


def test_container_resource_limits_are_configured():
    runner = ContainerPluginRunner(cpu_quota=0.5, memory_mb=128, timeout_s=2.0)
    assert runner.cpu_quota == 0.5
    assert runner.memory_mb == 128
    assert runner.timeout_s == 2.0
    assert runner.network == "none"


# ---------------------------------------------------------------------------
# Compat layer
# ---------------------------------------------------------------------------

def test_detect_platform_returns_typed_enum():
    pf = detect_platform()
    assert isinstance(pf.os, OS)
    assert pf.os in {OS.WINDOWS, OS.MACOS, OS.LINUX, OS.OTHER}
    assert current_platform().os == pf.os


def test_native_ext_matches_os():
    pf = current_platform()
    if pf.is_windows:
        assert pf.native_ext == ".dll"
    elif pf.os is OS.MACOS:
        assert pf.native_ext == ".dylib"
    else:
        assert pf.native_ext == ".so"


def test_plugin_cache_dir_uses_platform_convention():
    d = plugin_cache_dir()
    assert "plugins" in d
    # must be absolute
    assert os.path.isabs(d)


def test_native_timeout_returns_result_in_time():
    out = native_timeout(lambda x: x * 2, args=(3,), timeout_s=2.0)
    assert out == 6


def test_native_timeout_raises_on_overrun():
    with pytest.raises(CompatTimeout):
        native_timeout(lambda: time.sleep(2), timeout_s=0.3)


def test_native_timeout_can_return_default_instead_of_raising():
    out = native_timeout(lambda: time.sleep(2), timeout_s=0.3,
                        default="fallback", raise_on_timeout=False)
    assert out == "fallback"


def test_normalize_line_endings():
    assert normalize_line_endings("a\r\nb\rc\n") == "a\nb\nc\n"


def test_native_arch_suffix_contains_machine():
    suffix = native_arch_suffix()
    pf = current_platform()
    assert pf.machine in suffix or "arm" in suffix.lower() or "x86" in suffix
