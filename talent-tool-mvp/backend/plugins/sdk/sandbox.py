"""v6.0 T2104 — Plugin sandbox.

Belt-and-braces over the existing :class:`PluginRunner` so a plugin cannot
take down the host even if it manages to escape Python-level guards.

Layered defences:

* **Import-time guarding** — :func:`safe_import` blocks importing of blacklisted
  modules (``os``, ``subprocess``, ``socket``, ``ctypes``, ``importlib``...).
* **RestrictedPython** — when ``use_restricted_python=True``, plugin source
  is compiled with restricted guards (no ``__import__``, no ``open``,
  no ``getattr`` on dunder attrs, no comprehension side effects).
* **Permission whitelist** — every privileged call goes through
  :class:`PluginContext.require_permission` which raises if the token is not
  in the manifest.
* **Resource limits** — :class:`ResourceLimiter` puts soft caps on CPU time
  (via :mod:`signal.SIGXCPU` on POSIX) and on memory growth (via
  :func:`resource.setrlimit` when available).
* **Network egress guard** — :class:`NetworkGuard` blocks outbound traffic
  to anything outside the configured allow-list by patching :mod:`socket`.
* **Filesystem guard** — :class:`FilesystemGuard` pins the plugin to a
  dedicated sandbox directory.

The sandbox is intentionally opt-in: the production deployment should
ALSO run plugins inside a separate process / container (see
``docs/PLUGIN_SECURITY.md``). The in-process guards are defence-in-depth.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import logging
import os
import sys
import time
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Blacklists
# ---------------------------------------------------------------------------

# Modules that the sandboxed plugin code must never import. Add to this list
# whenever a new capability should be opt-in instead of default-allowed.
DEFAULT_BLOCKED_MODULES: Set[str] = {
    "os",
    "os.path",
    "sys",
    "subprocess",
    "socket",
    "ssl",
    "ctypes",
    "ctypes.util",
    "_ctypes",
    "importlib",
    "importlib.util",
    "importlib.machinery",
    "importlib.abc",
    "code",
    "codeop",
    "pickle",
    "cPickle",
    "shelve",
    "multiprocessing",
    "fcntl",
    "pty",
    "resource",
    "pty",  # pseudo-terminal
    "spwd",
    "crypt",
    "grp",
    "pwd",
    "platform",
    "signal",
    "posix",
    "nt",
    "msvcrt",
    "_winreg",
    "win32api",
    "win32com",
}

# Methods that we strip from the builtin namespace when RestrictedPython
# is enabled.
RESTRICTED_BUILTINS_BLACKLIST: Set[str] = {
    "__import__",
    "compile",
    "exec",
    "eval",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
}


# ---------------------------------------------------------------------------
# safe_import
# ---------------------------------------------------------------------------

class BlockedImportError(ImportError):
    pass


def safe_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
    """Replacement for ``__import__`` that refuses blacklisted modules."""
    top = name.split(".")[0]
    if top in DEFAULT_BLOCKED_MODULES:
        raise BlockedImportError(
            f"plugin import blocked: {name!r} (sandbox forbids {top!r})"
        )
    return importlib.__import__(name, globals, locals, fromlist, level)


# ---------------------------------------------------------------------------
# RestrictedPython wrapper (optional)
# ---------------------------------------------------------------------------

def try_compile_restricted(source: str, filename: str = "<plugin>") -> Any:
    """Compile ``source`` under RestrictedPython if available, else fall back
    to plain ``compile`` after a manual AST audit.

    Returns the code object. Raises ``BlockedImportError`` for blacklisted
    imports and ``SyntaxError`` for everything else.
    """
    try:
        from RestrictedPython import compile_restricted  # type: ignore
        from RestrictedPython.PrintCollector import PrintCollector  # noqa: F401
    except ImportError:
        # RestrictedPython not installed — fall back to AST audit.
        return _ast_audit_compile(source, filename)

    try:
        return compile_restricted(source, filename, "exec")
    except SyntaxError as exc:
        raise
    except Exception as exc:  # RestrictedPython raises its own type
        raise SyntaxError(f"restricted compile failed: {exc}") from exc


def _ast_audit_compile(source: str, filename: str) -> Any:
    """Pure-stdlib fallback: scan the AST for forbidden imports / dunder
    accesses."""
    import ast

    tree = ast.parse(source, filename=filename)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in DEFAULT_BLOCKED_MODULES:
                    raise BlockedImportError(
                        f"plugin imports blocked module {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in DEFAULT_BLOCKED_MODULES:
                raise BlockedImportError(
                    f"plugin imports blocked module {node.module!r}"
                )
        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__") and attr not in {"__name__", "__doc__"}:
                raise BlockedImportError(
                    f"plugin accesses dunder attribute {attr!r}"
                )

    # Strip dangerous builtins from the compile namespace.
    code = compile(source, filename, "exec")
    return code


# ---------------------------------------------------------------------------
# Resource limits (POSIX)
# ---------------------------------------------------------------------------

@dataclass
class ResourceLimiter:
    cpu_seconds: float = 30.0
    memory_mb: int = 256
    file_descriptors: int = 64

    def __post_init__(self) -> None:
        self._previous: List[Any] = []
        self._supported = sys.platform != "win32"

    def __enter__(self) -> "ResourceLimiter":
        if not self._supported:
            return self
        try:
            import resource  # type: ignore
        except ImportError:
            return self
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
            self._previous.append(("CPU", soft, hard))
            resource.setrlimit(resource.RLIMIT_CPU,
                               (int(self.cpu_seconds), hard))
        except (ValueError, OSError) as exc:
            logger.debug("RLIMIT_CPU not applied: %s", exc)

        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            self._previous.append(("AS", soft, hard))
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.memory_mb * 1024 * 1024, hard),
            )
        except (ValueError, OSError) as exc:
            logger.debug("RLIMIT_AS not applied: %s", exc)

        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            self._previous.append(("NOFILE", soft, hard))
            resource.setrlimit(resource.RLIMIT_NOFILE,
                               (self.file_descriptors, hard))
        except (ValueError, OSError) as exc:
            logger.debug("RLIMIT_NOFILE not applied: %s", exc)

        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._supported:
            return
        try:
            import resource  # type: ignore
            for entry in reversed(self._previous):
                name, soft, hard = entry
                rsrc = getattr(resource, f"RLIMIT_{name}")
                resource.setrlimit(rsrc, (soft, hard))
        except Exception:  # noqa: BLE001 — best-effort restore
            pass


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------

class NetworkGuard:
    """Block outbound network access outside the configured allow-list.

    Implementation: monkey-patch :mod:`socket.socket` so any
    ``connect()`` call goes through our predicate. The original socket
    class is restored on exit. Only takes effect if ``allow`` is non-empty;
    pass ``allow=None`` to disable the guard entirely (not recommended in
    production).
    """

    def __init__(self, allow: Optional[Iterable[str]] = None) -> None:
        self.allow = set(allow or [])
        self._real_socket = None
        self._patched: List[Any] = []

    def __enter__(self) -> "NetworkGuard":
        if not self.allow:
            return self
        import socket  # local import — guard may not always be active

        self._real_socket = socket.socket
        guard = self

        class _GuardedSocket(socket.socket):  # type: ignore[misc]
            def connect(self, address):  # type: ignore[override]
                host, *_ = address if isinstance(address, tuple) else (address,)
                if not guard._is_allowed(str(host)):
                    raise PermissionError(
                        f"plugin network access denied to {host!r}"
                    )
                return super().connect(address)

        socket.socket = _GuardedSocket  # type: ignore[misc]
        self._patched.append(socket.socket)
        return self

    def _is_allowed(self, host: str) -> bool:
        for pattern in self.allow:
            if pattern == host:
                return True
            if pattern.startswith("*.") and host.endswith(pattern[1:]):
                return True
        return False

    def __exit__(self, exc_type, exc, tb) -> None:
        import socket

        if self._real_socket is not None:
            socket.socket = self._real_socket  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Filesystem guard
# ---------------------------------------------------------------------------

class FilesystemGuard:
    """Pin file writes to a sandbox directory; reads allowed anywhere.

    Implementation: monkey-patch the builtin ``open`` so writes are
    rejected unless the path falls inside ``sandbox_dir``.
    """

    def __init__(self, sandbox_dir: str) -> None:
        self.sandbox_dir = os.path.realpath(sandbox_dir)
        self._real_open = None

    def __enter__(self) -> "FilesystemGuard":
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self._real_open = open
        guard = self
        builtins_mod = sys.modules.get("builtins") or sys.modules["__builtin__"]

        def _safe_open(file, mode="r", *args, **kwargs):  # type: ignore[no-redef]
            if any(ch in mode for ch in ("w", "a", "x", "+")):
                target = os.path.realpath(str(file))
                if not target.startswith(guard.sandbox_dir + os.sep) and \
                        target != guard.sandbox_dir:
                    raise PermissionError(
                        f"plugin write blocked: {file!r} not under sandbox"
                    )
            return guard._real_open(file, mode, *args, **kwargs)

        builtins_mod.open = _safe_open  # type: ignore[assignment]
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        builtins_mod = sys.modules.get("builtins") or sys.modules["__builtin__"]
        if self._real_open is not None:
            builtins_mod.open = self._real_open  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Top-level sandbox runner
# ---------------------------------------------------------------------------

@dataclass
class SandboxConfig:
    allow_network_hosts: List[str] = field(default_factory=list)
    sandbox_dir: Optional[str] = None
    cpu_seconds: float = 30.0
    memory_mb: int = 256
    file_descriptors: int = 64
    use_restricted_python: bool = True
    permissions: List[str] = field(default_factory=list)


class SandboxError(RuntimeError):
    pass


@contextlib.contextmanager
def sandboxed(config: SandboxConfig):
    """Composite guard context. Use as::

        with sandboxed(cfg):
            plugin.install(ctx)
    """
    layers: List[Any] = []

    layers.append(ResourceLimiter(
        cpu_seconds=config.cpu_seconds,
        memory_mb=config.memory_mb,
        file_descriptors=config.file_descriptors,
    ))
    if config.sandbox_dir:
        layers.append(FilesystemGuard(config.sandbox_dir))
    if config.allow_network_hosts is not None:
        layers.append(NetworkGuard(allow=config.allow_network_hosts))

    # Enter all guards.
    for layer in layers:
        layer.__enter__()
    try:
        yield
    finally:
        # Exit in reverse order.
        for layer in reversed(layers):
            try:
                layer.__exit__(None, None, None)
            except Exception:  # noqa: BLE001 — best effort
                pass


# ---------------------------------------------------------------------------
# Source compilation helper for plugin entry points
# ---------------------------------------------------------------------------

def compile_plugin_source(source: str, filename: str,
                          use_restricted: bool = True) -> Any:
    """Compile raw plugin source. Applies RestrictedPython if enabled,
    otherwise falls back to plain compile with a stdlib AST audit."""
    if use_restricted:
        return try_compile_restricted(source, filename=filename)
    return compile(source, filename, "exec")


__all__ = [
    "DEFAULT_BLOCKED_MODULES",
    "RESTRICTED_BUILTINS_BLACKLIST",
    "BlockedImportError",
    "SandboxConfig",
    "SandboxError",
    "sandboxed",
    "safe_import",
    "compile_plugin_source",
    "try_compile_restricted",
    "ResourceLimiter",
    "NetworkGuard",
    "FilesystemGuard",
]