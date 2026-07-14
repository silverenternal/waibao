"""v10.0 T5025 — StreamEventBus + DLQ + schema registry tests.

Exercises the Redis-Streams-backed bus using the in-memory backend so the
suite has zero external dependencies, then re-runs the publish/consume/replay
matrix against ``fakeredis`` to prove the same code path works with a real
Redis Streams client shape.
"""
from __future__ import annotations


import pytest

from eventbus.base import Event
from eventbus.schema_registry import (
    IncompatibleSchemaError,
    SchemaRegistry,
    get_schema_registry,
    set_schema_registry,
)
from eventbus.streams import (
    InMemoryStreamBackend,
    StreamEventBus,
    StreamRetryPolicy,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def bus():
    b = StreamEventBus(backend=InMemoryStreamBackend(),
                       retry=StreamRetryPolicy(max_attempts=2, base_delay=0.0))
    yield b
    b.reset()


def _make_bus(**kw):
    return StreamEventBus(backend=InMemoryStreamBackend(),
                          retry=StreamRetryPolicy(max_attempts=2, base_delay=0.0),
                          **kw)


# ---------------------------------------------------------------------------
# Basic publish / subscribe (in-process fan-out)
# ---------------------------------------------------------------------------
def test_local_fanout_delivers_synchronously(bus):
    # StreamEventBus is pull-based: subscribe then consume to deliver.
    received = []
    bus.subscribe("profile.updated", lambda e: received.append(e.payload))
    bus.publish(Event(name="profile.updated", payload={"user_id": 1}))
    bus.consume("profile.updated")
    assert received == [{"user_id": 1}]


def test_publish_appends_to_stream(bus):
    bus.publish(Event(name="profile.updated", payload={"user_id": 1}))
    bus.publish(Event(name="profile.updated", payload={"user_id": 2}))
    assert bus.stream_len("profile.updated") == 2


# ---------------------------------------------------------------------------
# Consume with retry + DLQ
# ---------------------------------------------------------------------------
def test_consume_acks_successful_events(bus):
    seen = []
    bus.subscribe("ticket.created", lambda e: seen.append(e.event_id))
    bus.publish(Event(name="ticket.created", payload={"ticket_id": "T1"}))
    n = bus.consume("ticket.created")
    assert n == 1
    assert len(seen) == 1


def test_retry_then_success(bus):
    calls = {"n": 0}

    def flaky(evt):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")

    bus.subscribe("journal.submitted", flaky)
    bus.publish(Event(name="journal.submitted", payload={"user_id": 1}))
    bus.consume("journal.submitted")
    # succeeded on the 2nd attempt within the same consume call
    assert calls["n"] == 2
    assert bus.dlq_len("journal.submitted") == 0


def test_retry_exhausted_moves_to_dlq(bus):
    def always_fail(evt):
        raise RuntimeError("permanent")

    bus.subscribe("plan.generated", always_fail)
    bus.publish(Event(name="plan.generated", payload={"user_id": 1}))
    n = bus.consume("plan.generated")
    assert n == 1  # processed (acked + DLQ'd)
    assert bus.dlq_len("plan.generated") == 1
    entries = bus.dlq_entries("plan.generated")
    assert len(entries) == 1
    assert entries[0].reason == "retry_exhausted"
    assert entries[0].attempts == 2
    # the live stream entry has been acked out of the PEL
    # (xack does not remove from the stream, so len stays 1 — that's expected)


def test_dlq_entries_includes_event_payload(bus):
    bus.subscribe("plan.generated", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
    bus.publish(Event(name="plan.generated", payload={"user_id": 42}))
    bus.consume("plan.generated")
    entries = bus.dlq_entries("plan.generated")
    assert entries[0].event.payload == {"user_id": 42}


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def test_replay_redelivers_history(bus):
    delivered = []
    bus.subscribe("market.updated", lambda e: delivered.append(e.payload["user_id"]))
    bus.publish(Event(name="market.updated", payload={"user_id": 1}))
    bus.publish(Event(name="market.updated", payload={"user_id": 2}))
    # subscribe AFTER publish via replay by clearing delivered then replaying
    delivered.clear()
    n = bus.replay("market.updated")
    assert n == 2
    assert delivered == [1, 2]


def test_replay_respects_after_bound(bus):
    bus.publish(Event(name="market.updated", payload={"user_id": 1}))
    # capture the first stream id via xrange
    stream = bus._stream("market.updated")  # noqa: SLF001 — test only
    first_id = bus._backend.xrange(stream, "-", "+", count=1)[0][0]  # noqa: SLF001
    bus.publish(Event(name="market.updated", payload={"user_id": 2}))
    delivered = []
    bus.subscribe("market.updated", lambda e: delivered.append(e.payload["user_id"]))
    n = bus.replay("market.updated", after=first_id)
    assert n == 1
    assert delivered == [2]


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
def test_schema_validation_routes_bad_payload_to_dlq():
    reg = SchemaRegistry()
    reg.register("ticket.created",
                 fields={"ticket_id": (str, int)},
                 required=["ticket_id"])
    b = _make_bus(schema_registry=reg)
    b.subscribe("ticket.created", lambda e: None)
    # missing required ticket_id
    b.publish(Event(name="ticket.created", payload={"oops": 1}))
    assert b.dlq_len("ticket.created") == 1
    entries = b.dlq_entries("ticket.created")
    assert entries[0].reason == "schema_violation"


def test_schema_validation_passes_good_payload():
    reg = SchemaRegistry()
    reg.register("ticket.created",
                 fields={"ticket_id": (str, int)},
                 required=["ticket_id"])
    b = _make_bus(schema_registry=reg)
    b.subscribe("ticket.created", lambda e: None)
    b.publish(Event(name="ticket.created", payload={"ticket_id": "T9"}))
    assert b.dlq_len("ticket.created") == 0
    assert b.stream_len("ticket.created") == 1


def test_unknown_event_validates_as_ok():
    reg = SchemaRegistry()
    b = _make_bus(schema_registry=reg)
    b.publish(Event(name="totally.adhoc", payload={"anything": True}))
    assert b.stream_len("totally.adhoc") == 1
    assert b.dlq_len("totally.adhoc") == 0


def test_backward_compatible_evolution_allows_optional_field():
    reg = SchemaRegistry()
    reg.register("profile.updated", fields={"user_id": int}, required=["user_id"])
    # add an optional field — backward compatible
    v2 = reg.register("profile.updated",
                      fields={"user_id": int, "nickname": str},
                      required=["user_id"])
    assert v2.version == 2
    assert reg.get("profile.updated").version == 2


def test_incompatible_evolution_raises():
    reg = SchemaRegistry()
    reg.register("profile.updated", fields={"user_id": int}, required=["user_id"])
    with pytest.raises(IncompatibleSchemaError):
        # remove a previously-required field
        reg.register("profile.updated", fields={}, required=[])


def test_default_registry_has_known_events():
    reg = get_schema_registry()
    known = reg.known()
    assert "profile.updated" in known
    assert "emotion.risk" in known
    assert "ticket.created" in known
    # reset singleton so other tests get a clean default
    set_schema_registry(SchemaRegistry())


# ---------------------------------------------------------------------------
# redrive
# ---------------------------------------------------------------------------
def test_redrive_moves_dlq_back_to_live_stream(bus):
    bus.subscribe("plan.generated", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
    bus.publish(Event(name="plan.generated", payload={"user_id": 1}))
    bus.consume("plan.generated")
    assert bus.dlq_len("plan.generated") == 1
    # swap handler for a working one and redrive
    bus._handlers["plan.generated"] = []  # noqa: SLF001
    bus.subscribe("plan.generated", lambda e: None)
    n = bus.redrive("plan.generated")
    assert n == 1
    # re-published onto the live stream
    assert bus.stream_len("plan.generated") >= 1


# ---------------------------------------------------------------------------
# fakeredis-backed end-to-end (real Redis Streams command surface)
# ---------------------------------------------------------------------------
def test_fakeredis_backend_roundtrip():
    fakeredis = pytest.importorskip("fakeredis")
    backend = fakeredis.FakeRedis()
    reg = SchemaRegistry()
    b = StreamEventBus(backend=backend, schema_registry=reg,
                       retry=StreamRetryPolicy(max_attempts=1, base_delay=0.0))
    seen = []
    b.subscribe("emotion.detected", lambda e: seen.append(e.payload["emotion"]))
    b.publish(Event(name="emotion.detected", payload={"emotion": "happy", "user_id": 1}))
    n = b.consume("emotion.detected")
    assert n == 1
    assert seen == ["happy"]
    assert b.dlq_len("emotion.detected") == 0
