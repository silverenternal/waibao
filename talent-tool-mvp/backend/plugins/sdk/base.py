"""Plugin SDK — base abstractions for v6.0 third-party plugins.

A plugin is a self-contained bundle (manifest + code) that the host loads
through a sandboxed runner. Each plugin declares:

* ``name`` / ``version`` / ``author``
* ``permissions`` — explicit whitelist of capabilities
* ``config_schema`` — JSON-schema-style description for the UI
* an ``entry_point`` exposing one of: Agent / Service / Provider / Widget
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class PluginType(str, Enum):
    AGENT = "agent"
    SERVICE = "service"
    PROVIDER = "provider"
    WIDGET = "widget"


# ---------------------------------------------------------------------------
# Runtime context
# ---------------------------------------------------------------------------

@dataclass
class PluginContext:
    """Runtime context handed to a plugin during install/enable/execute."""

    plugin_name: str
    db: Any  # SQLAlchemy session / repository handle
    event_bus: Any  # backend.eventbus.EventBus
    logger: logging.Logger
    config: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=list)

    def require_permission(self, perm: str) -> None:
        if perm not in self.permissions:
            raise PermissionError(
                f"plugin {self.plugin_name!r} missing required permission {perm!r}"
            )

    def event_bus_emit(self, name: str, payload: Optional[Dict[str, Any]] = None,
                       correlation_id: Optional[str] = None) -> None:
        if "events:emit" not in self.permissions:
            self.require_permission("events:emit")
        if self.event_bus is None:
            # No event bus wired (test / standalone plugin run). Log and
            # return — never crash a plugin because the host hasn't injected
            # a bus yet.
            self.logger.debug(
                "event_bus_emit(%s) skipped — no event bus injected", name
            )
            return
        self.event_bus.emit(name, payload or {}, source=self.plugin_name,
                            correlation_id=correlation_id)


# ---------------------------------------------------------------------------
# Plugin state machine
# ---------------------------------------------------------------------------

class PluginState(str, Enum):
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class Plugin(ABC):
    """Base class every plugin must subclass."""

    name: str = ""
    version: str = "0.0.0"
    author: str = "unknown"
    description: str = ""

    # Whitelist of permission tokens, e.g. ["db:read", "events:emit", "http:call"]
    permissions: List[str] = []

    # Lightweight config schema for the UI (not a strict JSON-schema — just hints).
    config_schema: Dict[str, Any] = {}

    state: PluginState = PluginState.INSTALLED

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def install(self, ctx: PluginContext) -> None:  # noqa: D401
        """Override to provision tables, seed data, register migrations."""
        self.state = PluginState.INSTALLED

    def uninstall(self, ctx: PluginContext) -> None:
        self.state = PluginState.DISABLED

    def enable(self, ctx: PluginContext) -> None:
        self.state = PluginState.ENABLED

    def disable(self, ctx: PluginContext) -> None:
        self.state = PluginState.DISABLED

    # ------------------------------------------------------------------
    # Capability surface
    # ------------------------------------------------------------------
    @abstractmethod
    def get_agent(self) -> Optional[Any]:
        """Return an Agent instance if this plugin contributes one."""

    @abstractmethod
    def get_service(self) -> Optional[Any]:
        """Return a Service instance if this plugin contributes one."""

    @abstractmethod
    def get_provider(self) -> Optional[Any]:
        """Return a Provider instance if this plugin contributes one."""

    @abstractmethod
    def get_widget(self) -> Optional[Any]:
        """Return a frontend widget descriptor if this plugin contributes one."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def manifest_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "permissions": list(self.permissions),
            "config_schema": self.config_schema,
            "state": self.state.value,
            "type": self._detect_type(),
        }

    def _detect_type(self) -> str:
        if self.get_agent() is not None:
            return PluginType.AGENT.value
        if self.get_service() is not None:
            return PluginType.SERVICE.value
        if self.get_provider() is not None:
            return PluginType.PROVIDER.value
        if self.get_widget() is not None:
            return PluginType.WIDGET.value
        return "unknown"


# ---------------------------------------------------------------------------
# Registry — tracks loaded plugins
# ---------------------------------------------------------------------------

class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        if not plugin.name:
            raise ValueError("plugin.name is required")
        if plugin.name in self._plugins:
            raise ValueError(f"plugin {plugin.name!r} already registered")
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def all(self) -> List[Plugin]:
        return list(self._plugins.values())

    def by_type(self, ptype: PluginType) -> List[Plugin]:
        return [p for p in self._plugins.values() if p._detect_type() == ptype.value]


_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry