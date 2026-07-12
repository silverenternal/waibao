"""v6.0 T2102 — Config Watcher.

Long-running watcher that bridges `config.changed` EventBus events to
worker-side caches. Workers / services subscribe to the watcher's local
``on_change(topic, callback)`` API and receive a callback whenever a
matching config row changes.

Two transports:
- in-process (default): uses the local EventBus directly
- redis: also subscribes to the Redis pub/sub channel ``waibao:config:``
  for cross-worker fan-out

Workers call ``watch(scope, key, callback)`` at boot. ``start()`` spins
the watcher up; ``stop()`` tears it down.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Singleton watcher: forwards `config.changed` to registered handlers."""

    _instance: "Optional[ConfigWatcher]" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._handlers: List[Tuple[str, str, Callable[[str, str, Any], None]]] = []
        self._subscribed = False
        self._redis_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ----- singleton -----
    @classmethod
    def instance(cls) -> "ConfigWatcher":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ConfigWatcher()
            return cls._instance

    # ----- registration -----
    def watch(self, scope: str, key: str,
              callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback for (scope, key). key='*' matches any."""
        self._handlers.append((scope, key, callback))

    def unwatch(self, callback: Callable[[str, str, Any], None]) -> None:
        self._handlers = [h for h in self._handlers if h[2] is not callback]

    def _matches(self, scope: str, key: str) -> bool:
        for s, k, _cb in self._handlers:
            if s == scope and (k == "*" or k == key):
                return True
        return False

    # ----- lifecycle -----
    def start(self) -> None:
        if self._subscribed:
            return
        from eventbus import get_event_bus, on_event
        bus = get_event_bus()

        @on_event("config.changed")
        def _on_change(evt: Any) -> None:
            p = evt.payload or {}
            scope = p.get("scope"); key = p.get("key")
            if not self._matches(scope, key):
                return
            value = p.get("value")
            for s, k, cb in list(self._handlers):
                if s == scope and (k == "*" or k == key):
                    try:
                        cb(scope, key, value)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("config watcher cb error: %s", exc)

        # cross-process redis fan-out (optional)
        if os.getenv("WAIBAO_REDIS_URL"):
            try:
                self._start_redis_listener()
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis listener start failed: %s", exc)
        self._subscribed = True
        logger.info("config_watcher started with %d handlers", len(self._handlers))

    def stop(self) -> None:
        self._stop.set()
        if self._redis_thread and self._redis_thread.is_alive():
            try:
                self._redis_thread.join(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass

    # ----- internals -----
    def _start_redis_listener(self) -> None:
        import json
        try:
            import redis  # type: ignore
        except ImportError:
            logger.debug("redis pkg missing — skipped cross-process listener")
            return
        url = os.getenv("WAIBAO_REDIS_URL", "redis://localhost:6379/0")
        cli = redis.Redis.from_url(url, decode_responses=True)
        self._redis_thread = threading.Thread(
            target=self._redis_loop,
            args=(cli, json), daemon=True, name="config-watcher-redis",
        )
        self._redis_thread.start()

    def _redis_loop(self, cli: Any, json_mod: Any) -> None:
        ps = cli.pubsub(ignore_subscribe_messages=True)
        ps.psubscribe("waibao:config:*")
        for raw in ps.listen():
            if self._stop.is_set():
                break
            if raw is None or raw.get("type") != "pmessage":
                continue
            try:
                payload = json_mod.loads(raw["data"])
            except Exception:  # noqa: BLE001
                continue
            scope = payload.get("scope"); key = payload.get("key")
            value = payload.get("value")
            if not self._matches(scope, key):
                continue
            for s, k, cb in list(self._handlers):
                if s == scope and (k == "*" or k == key):
                    try:
                        cb(scope, key, value)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("config watcher (redis) cb error: %s", exc)


# Module-level conveniences ----------------------------------------------------

def watch(scope: str, key: str,
          callback: Callable[[str, str, Any], None]) -> None:
    """Shorthand for ``ConfigWatcher.instance().watch(scope, key, cb)``."""
    ConfigWatcher.instance().watch(scope, key, callback)


def start() -> None:
    ConfigWatcher.instance().start()


def stop() -> None:
    ConfigWatcher.instance().stop()


# Default agent prompt reloader (subscribed by default) ------------------------

def _reload_agent_prompt(scope: str, key: str, value: Any) -> None:
    """When ``agent.prompts.<agent>.*`` changes, invalidate the in-process cache.

    The agent simply re-reads ``config_service.get_prompt`` next call.
    """
    from . import config_service
    config_service.clear_cache()


def install_default_prompt_watcher() -> None:
    """Register a watcher that refreshes prompt caches on change."""
    watch("agent", "*", _reload_agent_prompt)


__all__ = [
    "ConfigWatcher",
    "watch", "start", "stop",
    "install_default_prompt_watcher",
]
