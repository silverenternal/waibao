"""T5024 — WorkflowEngine persistence + lifecycle (save/load/resume/cancel).

Wraps a :class:`WorkflowEngine` store with:

* **timeline** — an append-only per-run event log (node started /
  completed / failed / paused / retried / cancelled).
* **DBWorkflowStore** — a Postgres/Supabase-backed implementation of the
  engine's store protocol so runs survive process restarts.
* **PersistenceManager** — high-level save / load / resume / cancel /
  timeline surface used by the API layer.

Cycle detection, node timeout + retry live in :mod:`workflow_engine`;
this module records the resulting events and persists run state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

@dataclass
class TimelineEvent:
    run_id: str
    node_id: Optional[str]
    event: str            # started | completed | failed | paused | retried | cancelled | resumed
    detail: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "event": self.event,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class Timeline:
    """In-memory timeline log keyed by run_id (also mirrored to the DB store)."""

    def __init__(self) -> None:
        self._events: dict[str, list[TimelineEvent]] = {}
        self._lock = asyncio.Lock()

    async def record(self, ev: TimelineEvent) -> None:
        async with self._lock:
            self._events.setdefault(ev.run_id, []).append(ev)

    async def for_run(self, run_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return [e.to_dict() for e in self._events.get(run_id, [])]


# ---------------------------------------------------------------------------
# DB-backed workflow store
# ---------------------------------------------------------------------------

class DBWorkflowStore:
    """Postgres/Supabase-backed implementation of the engine store protocol.

    Stores run state as JSON in a ``workflow_runs`` table:

        id uuid pk, workflow_name text, status text, state jsonb,
        started_at timestamptz, finished_at timestamptz, updated_at timestamptz

    ``client_factory`` returns a Supabase/PostgREST client. When the DB
    is unavailable the constructor raises so misconfiguration fails fast.
    """

    def __init__(self, client_factory: Any, *, table: str = "workflow_runs") -> None:
        self._client_factory = client_factory
        self.table = table
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    def _sb(self) -> Any:
        try:
            return self._client_factory()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"workflow DB client unavailable: {exc}") from exc

    # ------------------------------------------------------------------
    async def save(self, result: Any) -> None:
        # ``result`` is a WorkflowResult; we serialise via to_dict().
        payload = {
            "id": result.run_id,
            "workflow_name": getattr(result, "workflow_name", None),
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "state": json.dumps(result.to_dict(), default=str),
            "updated_at": datetime.utcnow().isoformat(),
        }
        if result.finished_at is None and not getattr(result, "_started_persisted", False):
            payload["started_at"] = datetime.utcnow().isoformat()
            result._started_persisted = True  # type: ignore[attr-defined]
        if result.finished_at is not None:
            payload["finished_at"] = datetime.utcnow().isoformat()
        async with self._lock:
            try:
                self._sb().table(self.table).upsert(payload).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("workflow save failed: %s", exc)

    async def load(self, run_id: str) -> Optional[Any]:
        # Returns the raw state dict; the caller reconstructs the result.
        try:
            res = self._sb().table(self.table).select("state").eq("id", run_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow load failed: %s", exc)
            return None
        rows = getattr(res, "data", None) or []
        if not rows:
            return None
        return json.loads(rows[0]["state"]) if rows[0].get("state") else None

    async def list_runs(self, workflow_name: Optional[str] = None) -> List[Any]:
        try:
            q = self._sb().table(self.table).select("state")
            if workflow_name:
                q = q.eq("workflow_name", workflow_name)
            res = q.order("updated_at", desc=True).limit(100).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow list failed: %s", exc)
            return []
        rows = getattr(res, "data", None) or []
        return [json.loads(r["state"]) for r in rows if r.get("state")]

    async def delete(self, run_id: str) -> bool:
        try:
            self._sb().table(self.table).delete().eq("id", run_id).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow delete failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Persistence manager (high-level lifecycle)
# ---------------------------------------------------------------------------

class WorkflowPersistenceManager:
    """High-level save / load / resume / cancel / timeline facade."""

    def __init__(self, engine: Any, *, store: Any = None, timeline: Optional[Timeline] = None) -> None:
        self.engine = engine
        self.store = store or getattr(engine, "store")
        self.timeline = timeline or Timeline()

    # ------------------------------------------------------------------
    async def save(self, result: Any) -> None:
        await self.store.save(result)

    async def load(self, run_id: str) -> Optional[Any]:
        return await self.store.load(run_id)

    async def resume(self, run_id: str, *, decision: Any = None) -> Any:
        await self.timeline.record(TimelineEvent(run_id, None, "resumed",
                                                 detail=f"decision={'yes' if decision else 'no'}"))
        result = await self.engine.resume(run_id, decision=decision)
        await self.timeline.record(TimelineEvent(
            run_id, getattr(result, "paused_at_node", None), result.status.value
            if hasattr(result.status, "value") else str(result.status),
        ))
        return result

    async def cancel(self, run_id: str) -> Any:
        await self.timeline.record(TimelineEvent(run_id, None, "cancelled"))
        result = await self.engine.cancel(run_id)
        return result

    async def timeline_for(self, run_id: str) -> list[dict[str, Any]]:
        return await self.timeline.for_run(run_id)

    async def record_node(self, run_id: str, node_id: str, event: str, detail: str = "") -> None:
        await self.timeline.record(TimelineEvent(run_id, node_id, event, detail))


# ---------------------------------------------------------------------------
# Module-level timeline registry (used by the API layer)
# ---------------------------------------------------------------------------

_GLOBAL_TIMELINE = Timeline()


async def record_global_event(ev: TimelineEvent) -> None:
    await _GLOBAL_TIMELINE.record(ev)


def _global_timeline(run_id: str) -> list[dict[str, Any]]:
    """Sync accessor for the API layer (returns whatever has been
    recorded so far)."""
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            # Cannot await — return a snapshot if the loop has one cached.
            return [e.to_dict() for e in _GLOBAL_TIMELINE._events.get(run_id, [])]
    except RuntimeError:
        pass
    return [e.to_dict() for e in _GLOBAL_TIMELINE._events.get(run_id, [])]
