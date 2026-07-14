"""T5023 — cross-platform (Windows / macOS / Linux) compatibility layer.

Plugin hosts run on all three desktop OSes. This module centralises the
platform-specific bits that previously leaked through the SDK:

* :class:`Platform` — typed detection of OS + arch.
* :func:`plugin_cache_dir` — the canonical per-user plugin directory
  (``%LOCALAPPDATA%\\waibao\\plugins`` on Windows,
  ``~/Library/Caches/waibao/plugins`` on macOS,
  ``~/.cache/waibao/plugins`` on Linux / ``$XDG_CACHE_HOME``).
* :func:`native_timeout` — wall-clock enforcement that works without
  ``signal.SIGALRM`` (which Windows lacks), using a watchdog thread.
* :func:`safe_kill` — terminate a process tree cross-platform.
* :func:`normalize_line_endings` — CRLF/LF normalisation for plugin source.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

class OS(str, Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"


@dataclass(frozen=True)
class Platform:
    os: OS
    machine: str
    python_version: str
    is_windows: bool
    is_posix: bool

    @property
    def native_ext(self) -> str:
        return ".dll" if self.is_windows else (".dylib" if self.os is OS.MACOS else ".so")

    @property
    def path_sep(self) -> str:
        return "\\" if self.is_windows else "/"

    def to_dict(self) -> dict[str, str]:
        return {
            "os": self.os.value, "machine": self.machine,
            "python_version": self.python_version,
            "is_windows": str(self.is_windows), "is_posix": str(self.is_posix),
        }


def detect_platform() -> Platform:
    system = platform.system().lower()
    if system.startswith("win"):
        os_kind = OS.WINDOWS
    elif system == "darwin":
        os_kind = OS.MACOS
    elif system == "linux":
        os_kind = OS.LINUX
    else:
        os_kind = OS.OTHER
    return Platform(
        os=os_kind,
        machine=platform.machine().lower(),
        python_version=platform.python_version(),
        is_windows=os.name == "nt" or os_kind is OS.WINDOWS,
        is_posix=os.name == "posix",
    )


_CURRENT_PLATFORM = detect_platform()


def current_platform() -> Platform:
    return _CURRENT_PLATFORM


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def plugin_cache_dir(base: str = "waibao") -> str:
    """Return the canonical plugin cache directory for the current OS."""
    pf = _CURRENT_PLATFORM
    if pf.is_windows:
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(local, base, "plugins")
    if pf.os is OS.MACOS:
        return os.path.join(os.path.expanduser("~/Library/Caches"), base, "plugins")
    # Linux + other POSIX honour XDG_CACHE_HOME.
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = xdg if xdg and os.path.isabs(xdg) else os.path.expanduser("~/.cache")
    return os.path.join(root, base, "plugins")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Timeout (works on Windows where SIGALRM is unavailable)
# ---------------------------------------------------------------------------

class TimeoutError(RuntimeError):  # noqa: A001 - intentional shadow for SDK ergonomics
    """Raised by :func:`native_timeout` when the callable overruns."""


def native_timeout(
    func: Callable[..., T],
    args: tuple = (),
    kwargs: Optional[dict] = None,
    *,
    timeout_s: float,
    default: Optional[T] = None,
    raise_on_timeout: bool = True,
) -> Optional[T]:
    """Run ``func`` with a wall-clock timeout.

    On POSIX we prefer ``signal.SIGALRM`` (cheap, in-thread). On Windows
    (or when the caller is not in the main thread) we fall back to a
    watchdog thread that cannot interrupt CPU-bound Python but WILL
    return control after the deadline.
    """
    kwargs = kwargs or {}
    pf = _CURRENT_PLATFORM

    if pf.is_posix and threading.current_thread() is threading.main_thread():
        import signal

        def _handler(signum, frame):  # noqa: ARG001
            raise TimeoutError(f"exceeded {timeout_s}s")

        old = signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_s)
        try:
            return func(*args, **kwargs)
        except TimeoutError:
            if raise_on_timeout:
                raise
            return default
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)

    # Watchdog-thread fallback (Windows / non-main thread).
    box: dict[str, Any] = {}

    def _runner():
        try:
            box["result"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        if raise_on_timeout:
            raise TimeoutError(f"exceeded {timeout_s}s")
        return default
    if "error" in box:
        raise box["error"]
    return box.get("result")


# ---------------------------------------------------------------------------
# Process killing
# ---------------------------------------------------------------------------

def safe_kill(proc: subprocess.Popen) -> None:
    """Terminate an entire process tree, cross-platform."""
    if proc.poll() is not None:
        return
    try:
        if _CURRENT_PLATFORM.is_windows:
            # taskkill /T kills the whole tree; /F forces.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, check=False,
            )
        else:
            import signal as _sig
            try:
                os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:  # noqa: BLE001
                proc.kill()
    finally:
        try:
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def normalize_line_endings(text: str) -> str:
    """Normalise CRLF/CR to LF so plugin source hashes are stable."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def native_arch_suffix() -> str:
    """Return a conventional ``os-arch`` wheel suffix, e.g. ``linux-x86_64``."""
    pf = _CURRENT_PLATFORM
    os_part = {
        OS.WINDOWS: "win",
        OS.MACOS: "macos",
        OS.LINUX: "linux",
        OS.OTHER: platform.system().lower(),
    }[pf.os]
    return f"{os_part}-{pf.machine}"
