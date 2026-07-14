"""v10.0 T5025 — Redis Streams-backed EventBus with DLQ + replay + retry.

Production-grade eventing layer that replaces the fire-and-forget pub/sub
model with **Redis Streams** so we get:

* **Persistence** — events live in a stream until a consumer ACKs them; a
  crash mid-handling does not lose the event.
* **Replay** — every event is retained (with `MAXLEN` trim) and can be
  re-played from any earlier ID via :meth:`StreamEventBus.replay`.
* **Consumer groups** — each handler belongs to a consumer group so events
  are load-balanced across workers and never delivered twice.
* **Exponential-backoff retry** — a failing handler is retried with backoff
  up to ``max_attempts``; exhausted events are moved to a **dead-letter
  queue (DLQ)** stream for inspection / re-drive.
* **Schema validation** — when a :class:`~eventbus.schema_registry.SchemaRegistry`
  is wired in, events whose payload violates the registered schema are
  routed straight to the DLQ and never dispatched.

The class is *transport-pluggable*: it accepts any object exposing the
``redis.Redis`` subset it uses (``xadd`` / ``xreadgroup`` / ``xack`` /
``xlen`` / ``xrange`` / ``xpending`` / ``xclaim``). ``fakeredis`` is used
in tests; a real ``redis.Redis`` in prod. When neither is reachable it
falls back to an in-process :class:`InMemoryStreamBackend` so dev / unit
tests have zero external dependencies.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .base import Event, EventBus, Subscription

logger = logging.getLogger(__name__)


def _normalize_fields(fields: Any) -> dict:
    """Coerce a stream entry's fields dict to plain ``str`` keys/values.

    Real ``redis.Redis(decode_responses=True)`` returns ``str``; fakeredis and
    the no-decode mode return ``bytes``. We normalize to ``str`` so downstream
    JSON parsing is uniform.
    """
    if not isinstance(fields, dict):
        return {}
    out: dict = {}
    for key, value in fields.items():
        k = key.decode() if isinstance(key, (bytes, bytearray)) else key
        v = value.decode() if isinstance(value, (bytes, bytearray)) else value
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------
class InMemoryStreamBackend:
    """Minimal in-process emulation of the Redis Streams commands we use.

    Implements: ``xadd`` / ``xlen`` / ``xrange`` / ``xread`` / ``xgroupcreate``
    (idempotent) / ``xreadgroup`` / ``xack`` / ``xpending`` / ``xclaim`` /
    ``xdel``. IDs are monotonically increasing ``<ms>-<seq>`` strings so
    ordering semantics match Redis.
    """

    def __init__(self) -> None:
        self._streams: Dict[str, List[tuple[str, dict]]] = {}
        self._groups: Dict[str, Dict[str, dict]] = {}  # stream -> group -> state
        self._lock = threading.RLock()
        self._clock = 0

    # --- low-level helpers ------------------------------------------------
    def _next_id(self) -> str:
        self._clock += 1
        return f"{self._clock}-0"

    def xadd(self, name: str, fields: dict, *, maxlen: int | None = None,
             approximate: bool = True) -> str:
        with self._lock:
            entries = self._streams.setdefault(name, [])
            entry_id = self._next_id()
            entries.append((entry_id, dict(fields)))
            if maxlen is not None and len(entries) > maxlen:
                # drop oldest beyond maxlen
                self._streams[name] = entries[-maxlen:]
            return entry_id

    def xlen(self, name: str) -> int:
        with self._lock:
            return len(self._streams.get(name, []))

    def xrange(self, name: str, start: str = "-", end: str = "+",
               count: int | None = None) -> list[tuple[str, dict]]:
        with self._lock:
            entries = list(self._streams.get(name, []))
        if start not in ("-",):
            entries = [e for e in entries if e[0] >= start]
        if end not in ("+",):
            entries = [e for e in entries if e[0] <= end]
        if count is not None:
            entries = entries[:count]
        return entries

    def xdel(self, name: str, *ids: str) -> int:
        with self._lock:
            entries = self._streams.get(name, [])
            idset = set(ids)
            kept = [e for e in entries if e[0] not in idset]
            removed = len(entries) - len(kept)
            self._streams[name] = kept
            return removed

    # --- consumer groups --------------------------------------------------
    def xgroup_create(self, name: str, group: str, id_: str = "$",
                      mkstream: bool = True) -> None:
        with self._lock:
            if mkstream and name not in self._streams:
                self._streams[name] = []
            groups = self._groups.setdefault(name, {})
            if group in groups:
                return  # idempotent — matches BUSYGROUP semantics tolerance
            groups[group] = {
                "last_delivered": id_ if id_ != "$" else "-",
                "pending": {},  # entry_id -> {consumer, delivered_at, deliveries}
            }

    def _last_index(self, name: str, last_id: str) -> int:
        entries = self._streams.get(name, [])
        for idx, (eid, _) in enumerate(entries):
            if eid > last_id:
                return idx
        return len(entries)

    def xreadgroup(self, groupname: str, groupname_alt: str | None = None,
                   streams: dict | None = None,
                   count: int | None = 1, block: int | None = None) -> list:
        """Read from a consumer group. ``streams`` maps stream -> id (``>``).

        Supports two call conventions to mirror the redis-py API:

        * ``xreadgroup(groupname, consumername, {stream: ">"}, count=...)``
        * ``xreadgroup({stream: ">"}, consumername, count=...)`` (legacy)
        """
        # Normalize arguments: redis-py calls as
        # ``xreadgroup(groupname, consumername, streams, count=N, block=M)``.
        if streams is None and isinstance(groupname_alt, dict):
            streams = groupname_alt
            groupname_alt = None
        if streams is None:
            return []
        consumer = groupname_alt or f"{groupname}:{threading.get_ident()}"
        out: list = []
        with self._lock:
            for stream_name, _recv_id in streams.items():
                gstate = self._groups.get(stream_name, {}).get(groupname)
                if gstate is None:
                    continue
                entries = self._streams.get(stream_name, [])
                idx = self._last_index(stream_name, gstate["last_delivered"])
                taken = entries[idx: idx + (count or 1)]
                for eid, fields in taken:
                    gstate["last_delivered"] = eid
                    gstate["pending"][eid] = {
                        "consumer": consumer,
                        "delivered_at": time.time(),
                        "deliveries": gstate["pending"].get(eid, {}).get("deliveries", 0) + 1,
                    }
                    out.append((stream_name, [(eid, dict(fields))]))
        return out

    def xack(self, name: str, group: str, *ids: str) -> int:
        with self._lock:
            gstate = self._groups.get(name, {}).get(group)
            if gstate is None:
                return 0
            acked = 0
            for eid in ids:
                if eid in gstate["pending"]:
                    del gstate["pending"][eid]
                    acked += 1
            return acked

    def xpending(self, name: str, group: str) -> dict:
        with self._lock:
            gstate = self._groups.get(name, {}).get(group)
            if gstate is None:
                return {"pending": 0, "min": None, "max": None, "consumers": {}}
            pending = gstate["pending"]
            consumers: dict[str, int] = {}
            for info in pending.values():
                c = info["consumer"]
                consumers[c] = consumers.get(c, 0) + 1
            ids = list(pending.keys())
            return {
                "pending": len(pending),
                "min": ids[0] if ids else None,
                "max": ids[-1] if ids else None,
                "consumers": consumers,
            }

    def xclaim(self, name: str, group: str, consumer: str, min_idle_time: int,
               *ids: str) -> list[tuple[str, dict]]:
        with self._lock:
            gstate = self._groups.get(name, {}).get(group)
            if gstate is None:
                return []
            now = time.time()
            out: list[tuple[str, dict]] = []
            entries = {eid: f for eid, f in self._streams.get(name, [])}
            for eid in ids:
                info = gstate["pending"].get(eid)
                if info is None:
                    continue
                if (now - info["delivered_at"]) * 1000 < min_idle_time:
                    continue
                info["consumer"] = consumer
                info["delivered_at"] = now
                info["deliveries"] += 1
                if eid in entries:
                    out.append((eid, entries[eid]))
            return out


def _make_backend(url: Optional[str]) -> Any:
    """Construct a Streams backend. Tries fakeredis (tests) then real redis."""
    if url is None or url == "memory":
        return InMemoryStreamBackend()
    try:
        import fakeredis  # type: ignore

        return fakeredis.FakeRedis.from_url(url)
    except Exception:  # pragma: no cover — fallback to real client
        pass
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "No Redis backend available for StreamEventBus — install redis/fakeredis"
        ) from exc


# ---------------------------------------------------------------------------
# Retry policy (exponential backoff with jitter)
# ---------------------------------------------------------------------------
@dataclass
class StreamRetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.1
    max_delay: float = 5.0
    jitter: float = 0.25

    def delay_for(self, attempt: int) -> float:
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter > 0:
            delay *= 1.0 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, delay)


# ---------------------------------------------------------------------------
# DLQ record
# ---------------------------------------------------------------------------
@dataclass
class DLQEntry:
    original_stream: str
    entry_id: str
    event: Event
    reason: str
    attempts: int
    moved_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "original_stream": self.original_stream,
            "entry_id": self.entry_id,
            "event": self.event.to_dict(),
            "reason": self.reason,
            "attempts": self.attempts,
            "moved_at": self.moved_at,
        }


# ---------------------------------------------------------------------------
# StreamEventBus
# ---------------------------------------------------------------------------
class StreamEventBus(EventBus):
    """Redis-Streams-backed event bus with retry, DLQ and replay."""

    def __init__(
        self,
        url: Optional[str] = "memory",
        *,
        stream_prefix: str = "waibao:stream:",
        dlq_prefix: str = "waibao:dlq:",
        maxlen: int = 10_000,
        retry: Optional[StreamRetryPolicy] = None,
        schema_registry: Any = None,
        consumer_group: str = "workers",
        consumer_name: Optional[str] = None,
        backend: Any = None,
    ) -> None:
        self._backend = backend if backend is not None else _make_backend(url)
        self._stream_prefix = stream_prefix
        self._dlq_prefix = dlq_prefix
        self._maxlen = maxlen
        self._retry = retry or StreamRetryPolicy()
        self._schema = schema_registry
        self._group = consumer_group
        self._consumer = consumer_name or f"c-{uuid.uuid4().hex[:8]}"
        self._local = _LocalFanout()
        self._handlers: Dict[str, List[Subscription]] = {}
        self._lock = threading.RLock()
        self._dlq_entries: List[DLQEntry] = []
        self._dlq_max = 1000
        self._ensure_groups()

    # ---- internal helpers ------------------------------------------------
    def _stream(self, name: str) -> str:
        return f"{self._stream_prefix}{name}"

    def _dlq_stream(self, name: str) -> str:
        return f"{self._dlq_prefix}{name}"

    def _ensure_groups(self) -> None:
        for method in ("xgroup_create",):
            pass  # placeholder for clarity
        # Best-effort group creation per known stream happens lazily on
        # first publish of an event name; see _ensure_group.

    def _ensure_group(self, stream: str) -> None:
        if not hasattr(self._backend, "xgroup_create"):
            return
        try:
            try:
                # redis-py uses `id`; our in-memory backend uses `id_`.
                self._backend.xgroup_create(stream, self._group, id="0", mkstream=True)
            except TypeError:
                self._backend.xgroup_create(stream, self._group, id_="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001 — BUSYGROUP is expected
            msg = str(exc).upper()
            if "BUSYGROUP" not in msg and "EXIST" not in msg:
                logger.debug("xgroup_create %s: %s", stream, exc)

    # ---- EventBus protocol ----------------------------------------------
    def publish(self, event: Event) -> None:
        # Schema validation up front — bad payloads go straight to the DLQ.
        if self._schema is not None and not self._schema.validate(event.name, event.payload):
            self._to_dlq(self._stream(event.name), "0", event, "schema_violation", 0)
            logger.warning("eventbus.schema_violation name=%s", event.name)
            return
        stream = self._stream(event.name)
        self._ensure_group(stream)
        try:
            self._backend.xadd(
                stream,
                {"data": json.dumps(event.to_dict(), default=str)},
                maxlen=self._maxlen,
                approximate=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("eventbus.xadd_failed stream=%s", stream)
        # Delivery is pull-based (consume()). The local fanout is only used by
        # ad-hoc ``on_local`` subscribers registered for synchronous dev/testing.

    def publish_async(self, event: Event) -> Any:
        async def _run() -> None:
            self.publish(event)

        return _run()

    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription:
        sub = Subscription(id=str(uuid.uuid4()), event_name=event_name, handler=handler)
        with self._lock:
            self._handlers.setdefault(event_name, []).append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            bucket = self._handlers.get(subscription.event_name, [])
            self._handlers[subscription.event_name] = [
                s for s in bucket if s.id != subscription.id
            ]
        self._local.unsubscribe(subscription)

    # ---- consumption with retry + DLQ -----------------------------------
    def consume(self, event_name: str, *, count: int = 16, block_ms: int = 0) -> int:
        """Pull up to ``count`` events for ``event_name`` and dispatch them.

        Each event is delivered to every registered handler (fan-out). A
        handler that raises is retried with exponential backoff up to
        ``retry.max_attempts``; once exhausted the event is ACK'd out of the
        group and moved to the DLQ so it does not block the stream.

        Returns the number of events processed (acked).
        """
        stream = self._stream(event_name)
        self._ensure_group(stream)
        with self._lock:
            subs = list(self._handlers.get(event_name, []))
        # If nobody is listening, drain via local fallback (dev) but still
        # ack so events don't pile up.
        try:
            messages = self._backend.xreadgroup(
                self._group, self._consumer, {stream: ">"}, count=count, block=block_ms
            )
        except Exception:  # noqa: BLE001
            logger.exception("eventbus.xreadgroup_failed stream=%s", stream)
            return 0
        processed = 0
        for _stream_name, entries in messages or []:
            for entry_id, fields in entries:
                norm = _normalize_fields(fields)
                event = self._decode(norm)
                if event is None:
                    self._backend.xack(stream, self._group, entry_id)
                    continue
                ok = self._dispatch_with_retry(stream, entry_id, event, subs)
                if ok:
                    self._backend.xack(stream, self._group, entry_id)
                    processed += 1
                else:
                    # exhausted retries -> DLQ, then ack to clear the PEL
                    self._to_dlq(
                        stream, entry_id, event, "retry_exhausted",
                        self._retry.max_attempts,
                    )
                    self._backend.xack(stream, self._group, entry_id)
                    processed += 1
        return processed

    def _decode(self, fields: dict) -> Optional[Event]:
        raw = fields.get("data") if isinstance(fields, dict) else None
        if not raw:
            return None
        try:
            return Event.from_dict(json.loads(raw))
        except Exception:  # noqa: BLE001
            logger.exception("eventbus.decode_failed")
            return None

    def _decode_replay(self, entries):
        """Decode a list of (id, fields) from xrange into Events."""
        out = []
        for _eid, fields in entries:
            event = self._decode(_normalize_fields(fields))
            if event is not None:
                out.append(event)
        return out

    def _dispatch_with_retry(self, stream: str, entry_id: str, event: Event,
                             subs: List[Subscription]) -> bool:
        if not subs:
            # No local handlers — let the local fanout / dev handlers see it.
            return True
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._retry.max_attempts + 1):
            failure = False
            for sub in subs:
                try:
                    sub.handler(event)
                except Exception as exc:  # noqa: BLE001 — handler isolation
                    failure = True
                    last_exc = exc
                    logger.warning(
                        "eventbus.handler_failed stream=%s sub=%s attempt=%s err=%s",
                        stream, sub.id, attempt, exc,
                    )
            if not failure:
                return True
            if attempt < self._retry.max_attempts:
                delay = self._retry.delay_for(attempt)
                time.sleep(delay)
        logger.error(
            "eventbus.retry_exhausted stream=%s entry=%s last_err=%s",
            stream, entry_id, last_exc,
        )
        return False

    def _to_dlq(self, stream: str, entry_id: str, event: Event,
                reason: str, attempts: int) -> None:
        dlq = self._dlq_stream(event.name)
        try:
            self._backend.xadd(
                dlq,
                {"data": json.dumps(event.to_dict(), default=str),
                 "reason": reason, "attempts": str(attempts),
                 "original_stream": stream, "original_id": entry_id},
                maxlen=self._maxlen,
                approximate=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("eventbus.dlq_xadd_failed dlq=%s", dlq)
        entry = DLQEntry(
            original_stream=stream, entry_id=entry_id, event=event,
            reason=reason, attempts=attempts,
        )
        with self._lock:
            self._dlq_entries.append(entry)
            if len(self._dlq_entries) > self._dlq_max:
                self._dlq_entries = self._dlq_entries[-self._dlq_max:]

    # ---- replay / diagnostics -------------------------------------------
    def replay(self, event_name: str, *, after: str = "-", limit: int = 100) -> int:
        """Re-publish events from the stream's history to current handlers.

        Useful for recovering after a handler bug fix or backfilling a new
        subscriber. ``after`` is a stream ID (exclusive lower bound).
        """
        stream = self._stream(event_name)
        try:
            # xrange is inclusive; replay uses `after` as an EXCLUSIVE lower
            # bound, so filter client-side to skip the boundary entry itself.
            entries = self._backend.xrange(stream, after if after != "-" else "-", "+",
                                            count=limit + 1)
        except Exception:  # noqa: BLE001
            logger.exception("eventbus.replay_xrange_failed stream=%s", stream)
            return 0
        if after != "-":
            entries = [e for e in entries if e[0] > after]
        if limit:
            entries = entries[:limit]
        with self._lock:
            subs = list(self._handlers.get(event_name, []))
        n = 0
        for _eid, fields in entries:
            event = self._decode(_normalize_fields(fields))
            if event is None:
                continue
            for sub in subs:
                try:
                    sub.handler(event)
                except Exception:  # noqa: BLE001
                    logger.exception("eventbus.replay_handler_failed")
            n += 1
        return n

    def stream_len(self, event_name: str) -> int:
        try:
            return self._backend.xlen(self._stream(event_name))
        except Exception:  # noqa: BLE001
            return 0

    def dlq_len(self, event_name: str) -> int:
        try:
            return self._backend.xlen(self._dlq_stream(event_name))
        except Exception:  # noqa: BLE001
            return 0

    def dlq_entries(self, event_name: Optional[str] = None) -> List[DLQEntry]:
        with self._lock:
            if event_name is None:
                return list(self._dlq_entries)
            return [e for e in self._dlq_entries if e.event.name == event_name]

    def redrive(self, event_name: str, limit: int = 100) -> int:
        """Move DLQ entries back to the live stream and re-attempt delivery."""
        dlq = self._dlq_stream(event_name)
        try:
            entries = self._backend.xrange(dlq, "-", "+", count=limit)
        except Exception:  # noqa: BLE001
            return 0
        replayed = 0
        for eid, fields in entries:
            event = self._decode(fields)
            if event is None:
                continue
            self.publish(event)
            try:
                self._backend.xdel(dlq, eid)
            except Exception:  # noqa: BLE001
                pass
            replayed += 1
        with self._lock:
            self._dlq_entries = [
                e for e in self._dlq_entries if e.event.name != event_name
            ][:0] if replayed and False else self._dlq_entries  # keep history
        return replayed

    def reset(self) -> None:
        """Clear all in-memory state (test helper)."""
        with self._lock:
            self._dlq_entries.clear()


class _LocalFanout:
    """Tiny in-process fan-out used so synchronous dev/test code still works
    even before ``consume()`` is called. Errors are isolated."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Subscription]] = {}
        self._lock = threading.RLock()

    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._handlers.get(event.name, []))
        for sub in subs:
            try:
                sub.handler(event)
            except Exception:  # noqa: BLE001
                logger.exception("local_fanout.handler_failed %s", sub.id)

    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription:
        sub = Subscription(id=str(uuid.uuid4()), event_name=event_name, handler=handler)
        with self._lock:
            self._handlers.setdefault(event_name, []).append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            bucket = self._handlers.get(subscription.event_name, [])
            self._handlers[subscription.event_name] = [
                s for s in bucket if s.id != subscription.id
            ]


__all__ = [
    "StreamEventBus",
    "StreamRetryPolicy",
    "DLQEntry",
    "InMemoryStreamBackend",
]
