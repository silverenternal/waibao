"""Realtime Session Manager (T2201).

Per-user, per-conversation session wrapper around the OpenAI Realtime API.

Responsibilities
----------------
- Allocates session IDs and persists session state (memory + Supabase)
- Forwards events from the provider to a caller-supplied ``dispatch`` callback
- Tracks metrics (latency, audio seconds, tokens, transcript deltas)
- Exposes a simple async API: ``start()``, ``push_audio()``, ``stop()``

The session intentionally knows nothing about FastAPI / WebSocket; the
HTTP/WS layer in :mod:`api.realtime_v2` adapts the protocol.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from providers.llm.openai_realtime import (
    EVT_ERROR,
    EVT_INPUT_AUDIO_BUFFER_COMMITTED,
    EVT_INPUT_AUDIO_BUFFER_SPEECH_STARTED,
    EVT_INPUT_AUDIO_BUFFER_SPEECH_STOPPED,
    EVT_RESPONSE_AUDIO_DELTA,
    EVT_RESPONSE_DONE,
    EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE,
    EVT_RESPONSE_TEXT_DELTA,
    EVT_RESPONSE_TEXT_DONE,
    EVT_SESSION_CREATED,
    RealtimeEvent,
    RealtimeSessionConfig,
    RealtimeUsage,
    get_realtime_provider,
)

logger = logging.getLogger("recruittech.services.realtime_session")

DispatchFn = Callable[[dict[str, Any]], Awaitable[None]]
AgentBridgeFn = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[str]]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
@dataclass
class TranscriptTurn:
    """A single turn (user or assistant) in the conversation."""

    role: str                       # "user" | "assistant" | "function"
    text: str = ""
    audio_bytes: int = 0            # number of audio bytes received/sent
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    emotion: str | None = None      # derived from audio features
    function_name: str | None = None
    function_args: dict[str, Any] | None = None
    function_result: str | None = None


@dataclass
class SessionMetrics:
    """Lightweight live metrics for a session."""

    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    first_audio_latency_ms: float | None = None
    last_audio_at: float | None = None
    audio_input_chunks: int = 0
    audio_output_chunks: int = 0
    text_turns: int = 0
    function_calls: int = 0
    interruptions: int = 0
    usage: RealtimeUsage = field(default_factory=RealtimeUsage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_sec": round(
                (self.ended_at or time.time()) - self.started_at, 2
            ),
            "first_audio_latency_ms": self.first_audio_latency_ms,
            "audio_input_chunks": self.audio_input_chunks,
            "audio_output_chunks": self.audio_output_chunks,
            "text_turns": self.text_turns,
            "function_calls": self.function_calls,
            "interruptions": self.interruptions,
            "usage": self.usage.to_dict(),
        }


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------
@dataclass
class ContextCompressor:
    """Naïve sliding-window context compressor.

    For Realtime sessions we cannot easily modify the model's context
    directly; instead, we keep a rolling summary of the oldest turns and
    inject it into ``session.instructions`` on every config update.
    """

    max_turns: int = 20
    summary_max_chars: int = 1500
    turns: list = field(default_factory=list)
    summary: str = ""

    def add(self, turn: TranscriptTurn) -> None:
        self.turns.append(turn)
        if len(self.turns) > self.max_turns * 2:
            # Compress oldest half
            self._compress_oldest()

    def _compress_oldest(self) -> None:
        if len(self.turns) <= self.max_turns:
            return
        oldest = self.turns[: self.max_turns]
        self.turns = self.turns[self.max_turns :]
        # Build a short bullet summary
        bullets: list[str] = []
        for t in oldest:
            if not t.text:
                continue
            text = t.text.replace("\n", " ").strip()[:200]
            bullets.append(f"- [{t.role}] {text}")
        if bullets:
            self.summary = (
                "Earlier conversation summary:\n"
                + "\n".join(bullets[-10:])[: self.summary_max_chars]
            )

    def render(self) -> str:
        return self.summary


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class RealtimeSession:
    """A single user-conversation Realtime session."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        conversation_id: str,
        config: RealtimeSessionConfig,
        agent_bridge: AgentBridgeFn | None = None,
        dispatch: DispatchFn | None = None,
        force_mock: bool = False,
    ) -> None:
        self.id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.config = config
        self.dispatch = dispatch
        self.metrics = SessionMetrics()
        self.compressor = ContextCompressor()
        self._provider = get_realtime_provider(
            model=config.model,
            voice=config.voice,
            instructions=config.instructions,
            force_mock=force_mock,
        )
        if agent_bridge:
            self._provider.set_agent_bridge(agent_bridge)
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._current_user_turn: TranscriptTurn | None = None
        self._current_assistant_turn: TranscriptTurn | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped = True
        self.metrics.ended_at = time.time()
        try:
            await self._provider.close()
        except Exception:  # noqa: BLE001
            pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _run(self) -> None:
        try:
            if getattr(self._provider, "is_mock", False):
                # Mock provider: just emit ready once, then idle.
                await self._on_event(
                    RealtimeEvent(type=EVT_SESSION_CREATED, raw={"type": EVT_SESSION_CREATED})
                )
                while not self._stopped:
                    await asyncio.sleep(0.1)
                return
            async for evt in self._provider.connect():
                if self._stopped:
                    break
                await self._on_event(evt)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("RealtimeSession loop failed: %s", e)
            await self._emit({"type": "error", "message": str(e)})

    # ------------------------------------------------------------------
    # Outbound (client -> server)
    # ------------------------------------------------------------------
    async def push_audio(self, pcm_b64: str) -> None:
        if self._stopped:
            return
        self.metrics.audio_input_chunks += 1
        self.metrics.last_audio_at = time.time()
        # Track first audio latency (from session start to first user audio)
        if self.metrics.first_audio_latency_ms is None:
            self.metrics.first_audio_latency_ms = round(
                (time.time() - self.metrics.started_at) * 1000, 1
            )
        # Buffer audio bytes
        if self._current_user_turn is None:
            self._current_user_turn = TranscriptTurn(role="user")
        try:
            n_bytes = len(pcm_b64) * 3 // 4
            self._current_user_turn.audio_bytes += n_bytes
        except Exception:  # noqa: BLE001
            pass
        await self._provider.send_audio(pcm_b64)

    async def push_text(self, text: str) -> None:
        if self._stopped or not text:
            return
        turn = TranscriptTurn(role="user", text=text)
        turn.ended_at = time.time()
        self.compressor.add(turn)
        await self._provider.send_user_text(text)
        await self._emit(
            {
                "type": "user_text",
                "text": text,
                "ts": time.time(),
            }
        )

    async def interrupt(self) -> None:
        if self._stopped:
            return
        self.metrics.interruptions += 1
        try:
            await self._provider.cancel_response()
        except Exception:  # noqa: BLE001
            pass
        if self._current_assistant_turn:
            self._current_assistant_turn.ended_at = time.time()
            self.compressor.add(self._current_assistant_turn)
            self._current_assistant_turn = None
        await self._emit({"type": "interrupted", "ts": time.time()})

    # ------------------------------------------------------------------
    # Inbound (server -> client)
    # ------------------------------------------------------------------
    async def _on_event(self, evt: RealtimeEvent) -> None:
        if evt.usage:
            self.metrics.usage = self._provider.get_usage()

        if evt.type == EVT_SESSION_CREATED:
            await self._emit(
                {
                    "type": "ready",
                    "session_id": self.id,
                    "model": self.config.model,
                    "voice": self.config.voice,
                    "ts": time.time(),
                }
            )
            return

        if evt.type == EVT_INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            await self._emit({"type": "vad_speech_start", "ts": time.time()})
            return
        if evt.type == EVT_INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            # Commit the user's audio turn
            if self._current_user_turn:
                self._current_user_turn.ended_at = time.time()
                self.compressor.add(self._current_user_turn)
                self._current_user_turn = None
            await self._emit({"type": "vad_speech_stop", "ts": time.time()})
            return
        if evt.type == EVT_INPUT_AUDIO_BUFFER_COMMITTED:
            await self._emit({"type": "audio_committed", "ts": time.time()})
            return

        if evt.type == EVT_RESPONSE_TEXT_DELTA and evt.delta is not None:
            if self._current_assistant_turn is None:
                self._current_assistant_turn = TranscriptTurn(role="assistant")
                self.metrics.text_turns += 1
            self._current_assistant_turn.text += evt.delta
            await self._emit(
                {
                    "type": "text_delta",
                    "delta": evt.delta,
                    "response_id": evt.response_id,
                    "ts": time.time(),
                }
            )
            return

        if evt.type == EVT_RESPONSE_TEXT_DONE:
            if self._current_assistant_turn:
                await self._emit(
                    {
                        "type": "text_done",
                        "text": self._current_assistant_turn.text,
                        "response_id": evt.response_id,
                        "ts": time.time(),
                    }
                )
            return

        if evt.type == EVT_RESPONSE_AUDIO_DELTA and evt.audio_b64:
            if self._current_assistant_turn is None:
                self._current_assistant_turn = TranscriptTurn(role="assistant")
            try:
                n_bytes = len(evt.audio_b64) * 3 // 4
                self._current_assistant_turn.audio_bytes += n_bytes
            except Exception:  # noqa: BLE001
                pass
            self.metrics.audio_output_chunks += 1
            await self._emit(
                {
                    "type": "audio_delta",
                    "audio": evt.audio_b64,
                    "response_id": evt.response_id,
                    "ts": time.time(),
                }
            )
            return

        if evt.type == EVT_RESPONSE_DONE:
            if self._current_assistant_turn:
                self._current_assistant_turn.ended_at = time.time()
                self.compressor.add(self._current_assistant_turn)
                self._current_assistant_turn = None
            await self._emit(
                {
                    "type": "response_done",
                    "usage": self.metrics.usage.to_dict(),
                    "ts": time.time(),
                }
            )
            return

        if evt.type == EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE:
            self.metrics.function_calls += 1
            name = (evt.raw.get("name") or "")
            await self._emit(
                {
                    "type": "function_call",
                    "name": name,
                    "call_id": evt.call_id,
                    "arguments": evt.arguments,
                    "ts": time.time(),
                }
            )
            return

        if evt.type == EVT_ERROR:
            await self._emit(
                {
                    "type": "error",
                    "message": (evt.error or {}).get("message", "unknown error"),
                    "ts": time.time(),
                }
            )
            return

    async def _emit(self, payload: dict[str, Any]) -> None:
        if not self.dispatch:
            return
        try:
            await self.dispatch(payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("dispatch failed: %s", e)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def get_transcript(self) -> list[dict[str, Any]]:
        """Return the full transcript as a list of dicts."""
        return [
            {
                "role": t.role,
                "text": t.text,
                "audio_bytes": t.audio_bytes,
                "started_at": t.started_at,
                "ended_at": t.ended_at,
                "emotion": t.emotion,
            }
            for t in self.compressor.turns
        ]


# ---------------------------------------------------------------------------
# Session registry (per-process)
# ---------------------------------------------------------------------------
class SessionRegistry:
    """In-memory registry keyed by session_id and (user_id, conversation_id)."""

    def __init__(self) -> None:
        self._sessions: dict[str, RealtimeSession] = {}
        self._lock = asyncio.Lock()

    async def register(self, session: RealtimeSession) -> None:
        async with self._lock:
            self._sessions[session.id] = session

    async def unregister(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> Optional[RealtimeSession]:
        return self._sessions.get(session_id)

    def list(self) -> list[RealtimeSession]:
        return list(self._sessions.values())

    async def stop_all(self) -> None:
        for s in list(self._sessions.values()):
            await s.stop()
        self._sessions.clear()


# Singleton
registry = SessionRegistry()


def make_session_id() -> str:
    return f"rts_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Supabase persistence helpers (best-effort)
# ---------------------------------------------------------------------------
async def persist_session_row(row: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        sb.table("realtime_sessions").upsert(row).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_session_row failed: %s", e)


async def persist_transcript(session_id: str, turn: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        row = {"session_id": session_id, **turn}
        sb.table("realtime_transcripts").insert(row).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_transcript failed: %s", e)


async def persist_metrics(session_id: str, metrics: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        sb.table("realtime_metrics").upsert(
            {"session_id": session_id, **metrics}
        ).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_metrics failed: %s", e)
