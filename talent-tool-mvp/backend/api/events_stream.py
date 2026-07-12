"""SSE endpoint for back-end EventBus fan-out to the browser.

Bridges the internal Python EventBus (InMemory or Redis) to the browser
via Server-Sent Events. Subscribers register for one or more topics on
the ``?topics=`` query param.

Usage (front-end):

    const es = new EventSource(`/api/events/stream?topics=profile.updated`);
    es.addEventListener("profile.updated", (raw) => {...});

Or use ``frontend/hooks/use-event.ts``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from eventbus import Event, get_event_bus, on_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

# In-process queue per (topic, client-id) — set by the SSE endpoint.
_QUEUES: dict[str, asyncio.Queue[Event]] = {}


def _queue_key(topic: str, client_id: str) -> str:
    return f"{topic}::{client_id}"


@router.get("/stream")
async def stream(
    request: Request,
    topics: str = Query(..., description="Comma-separated list of topic names"),
) -> StreamingResponse:
    """Server-Sent Events stream fan-out for the given topics."""

    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    if not topic_list:
        topic_list = ["*"]

    bus = get_event_bus()
    client_id = request.headers.get("x-client-id", str(time.time()))
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=128)

    subscriptions = []
    for topic in topic_list:
        qkey = _queue_key(topic, client_id)
        _QUEUES[qkey] = queue

        async def _handler(evt: Event, _t: str = topic) -> None:
            # Callback path for subscribe; mark _handler async
            pass

        def _sync_handler(evt: Event, _t: str = topic) -> None:
            try:
                qkey2 = _queue_key(_t, client_id)
                q = _QUEUES.get(qkey2)
                if q is not None:
                    q.put_nowait(evt)
            except (asyncio.QueueFull, KeyError):
                pass  # drop on slow client

        sub = bus.subscribe(topic, _sync_handler)
        subscriptions.append((topic, sub))

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            yield b": connected\n\n"
            last_keepalive = time.time()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = json.dumps(evt.to_dict(), ensure_ascii=False)
                    yield f"event: {evt.name}\ndata: {payload}\n\n".encode("utf-8")
                except asyncio.TimeoutError:
                    # send keepalive comment every 15s
                    yield b": keepalive\n\n"
                    last_keepalive = time.time()
        finally:
            # cleanup
            for topic, sub in subscriptions:
                try:
                    bus.unsubscribe(sub)
                except Exception:  # noqa: BLE001
                    pass
                _QUEUES.pop(_queue_key(topic, client_id), None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/topics")
async def list_topics() -> dict:
    """Quick introspection endpoint."""
    from eventbus.subscribers import _REGISTRY_FUNCS
    return {
        "registered_subscribers": len(_REGISTRY_FUNCS),
        "active_streams": len(_QUEUES),
    }


__all__ = ["router"]
