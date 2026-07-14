"""v10.0 T5026 — Prompt hot reload tests."""
from __future__ import annotations

from eventbus.base import InMemoryEventBus
from services.platform.prompt_hot_reload import (
    PromptHotReloader,
    notify_prompt_changed,
)
from services.platform.prompt_v2 import PromptService


def _service_with_active():
    service = PromptService()
    service.create_version(tenant_id="t1", name="greet", agent="default",
                           content="Hi {{name}}", version=1)
    service.activate_version("t1", "greet", "default", 1, traffic_pct=100)
    return service


def test_reload_new_version_flips_traffic():
    service = _service_with_active()
    bus = InMemoryEventBus()
    reloader = PromptHotReloader(service, bus=bus)
    record = reloader.reload("t1", "greet", "default", content="Hello {{name}}")
    assert record.success
    # override served on the read path
    assert reloader.get_active_content("t1", "greet", "default") == "Hello {{name}}"
    assert reloader.generation == 1


def test_reload_invalidate_clears_override():
    service = _service_with_active()
    bus = InMemoryEventBus()
    reloader = PromptHotReloader(service, bus=bus)
    reloader.reload("t1", "greet", "default", content="temp")
    assert reloader.get_active_content("t1", "greet", "default") == "temp"
    # invalidate -> back to registry content
    reloader.reload("t1", "greet", "default", content=None)
    assert reloader.get_active_content("t1", "greet", "default") == "Hi {{name}}"


def test_event_driven_reload_via_bus():
    service = _service_with_active()
    bus = InMemoryEventBus()
    reloader = PromptHotReloader(service, bus=bus)
    reloader.start()
    # publish a prompt.changed event
    notify_prompt_changed(bus, tenant_id="t1", name="greet", agent="default",
                          content="Hola {{name}}")
    assert reloader.generation == 1
    assert reloader.get_active_content("t1", "greet", "default") == "Hola {{name}}"


def test_listener_invoked_on_reload():
    service = _service_with_active()
    bus = InMemoryEventBus()
    reloader = PromptHotReloader(service, bus=bus)
    seen = []
    reloader.add_listener(lambda r: seen.append(r))
    reloader.reload("t1", "greet", "default", content="x")
    assert len(seen) == 1
    assert seen[0].success


def test_reload_failure_isolated_and_recorded():
    service = _service_with_active()
    # break the service so create_version raises
    service.list_versions = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    bus = InMemoryEventBus()
    reloader = PromptHotReloader(service, bus=bus)
    record = reloader.reload("t1", "greet", "default", content="x")
    assert record.success is False
    assert record.error is not None
    assert "RuntimeError" in record.error
    # generation still bumped so callers can detect an attempt
    assert reloader.generation == 1


def test_reloaded_event_emitted():
    service = _service_with_active()
    received = []
    bus = InMemoryEventBus()
    bus.subscribe(PromptHotReloader.RELOADED_EVENT,
                  lambda e: received.append(e.payload))
    reloader = PromptHotReloader(service, bus=bus)
    reloader.reload("t1", "greet", "default", content="x")
    assert len(received) == 1
    assert received[0]["name"] == "greet"
    assert received[0]["generation"] == 1
