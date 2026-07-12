"""OpenAI Realtime Provider (T2201).

Implements the OpenAI Realtime API (GA, Dec 2024) using the
``wss://api.openai.com/v1/realtime?model=...`` WebSocket protocol.

Features
--------
- Bidirectional audio streaming (PCM16 / G.711 µ-law / A-law)
- Server-side VAD (default ``server_vad``)
- Tool/function calling (wire to backend agents via :class:`AgentBridge`)
- Token usage tracking (input_tokens, output_tokens, audio_seconds)
- Configurable voice, temperature, modalities, turn detection
- Graceful fallback to :class:`MockRealtimeProvider` when no API key

This provider is intentionally framework-agnostic: it does not depend on
FastAPI or Pydantic. The :mod:`services.platform.realtime_session` layer
binds it to a per-user session and forwards events to the client WebSocket.

Protocol Reference
------------------
https://platform.openai.com/docs/guides/realtime
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

logger = logging.getLogger("recruittech.providers.openai_realtime")

# Default OpenAI Realtime GA model (Dec 2024+)
DEFAULT_REALTIME_MODEL = "gpt-4o-realtime-preview"
DEFAULT_REALTIME_URL = "wss://api.openai.com/v1/realtime"

# Audio formats
AUDIO_PCM16 = "pcm16"
AUDIO_G711_ULAW = "g711_ulaw"
AUDIO_G711_ALAW = "g711_alaw"

# Default voice (alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar)
DEFAULT_VOICE = "alloy"

# Server event types we care about
EVT_ERROR = "error"
EVT_SESSION_CREATED = "session.created"
EVT_SESSION_UPDATED = "session.updated"
EVT_CONVERSATION_ITEM = "conversation.item.created"
EVT_RESPONSE_CREATED = "response.created"
EVT_RESPONSE_TEXT_DELTA = "response.text.delta"
EVT_RESPONSE_TEXT_DONE = "response.text.done"
EVT_RESPONSE_AUDIO_DELTA = "response.audio.delta"
EVT_RESPONSE_AUDIO_DONE = "response.audio.done"
EVT_RESPONSE_DONE = "response.done"
EVT_INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
EVT_INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
EVT_INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE = "response.function_call_arguments.done"
EVT_RATE_LIMITS = "rate_limits.updated"


@dataclass(slots=True)
class RealtimeUsage:
    """Token / audio usage from the Realtime API."""

    input_tokens: int = 0
    output_tokens: int = 0
    audio_input_seconds: float = 0.0
    audio_output_seconds: float = 0.0
    total_tokens: int = 0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "audio_input_seconds": round(self.audio_input_seconds, 3),
            "audio_output_seconds": round(self.audio_output_seconds, 3),
            "total_tokens": self.total_tokens,
            "last_updated": self.last_updated,
        }


@dataclass(slots=True)
class RealtimeSessionConfig:
    """User-controllable session configuration.

    Mirrors the OpenAI Realtime ``session.update`` event body.
    """

    model: str = DEFAULT_REALTIME_MODEL
    voice: str = DEFAULT_VOICE
    instructions: str = (
        "You are a helpful, concise AI assistant. Speak in the same language as the user."
    )
    modalities: list[str] = field(default_factory=lambda: ["audio", "text"])
    input_audio_format: str = AUDIO_PCM16
    output_audio_format: str = AUDIO_PCM16
    temperature: float = 0.7
    max_response_output_tokens: int = 4096
    turn_detection: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
        }
    )
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_choice: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_session_update(self) -> dict[str, Any]:
        """Render as the body of a ``session.update`` event."""
        body: dict[str, Any] = {
            "model": self.model,
            "voice": self.voice,
            "instructions": self.instructions,
            "modalities": self.modalities,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "temperature": self.temperature,
            "max_response_output_tokens": self.max_response_output_tokens,
            "turn_detection": self.turn_detection,
            "tool_choice": self.tool_choice,
        }
        if self.tools:
            body["tools"] = self.tools
        if self.metadata:
            body["metadata"] = self.metadata
        return body


@dataclass(slots=True)
class RealtimeEvent:
    """A normalized event from the OpenAI Realtime API."""

    type: str
    raw: dict[str, Any] = field(default_factory=dict)
    delta: str | None = None             # text delta
    audio_b64: str | None = None         # audio delta (base64)
    item_id: str | None = None
    response_id: str | None = None
    call_id: str | None = None           # for function calls
    arguments: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "RealtimeEvent":
        etype = raw.get("type", "unknown")
        delta = None
        audio_b64 = None
        call_id = None
        arguments = None
        usage = None
        if etype == EVT_RESPONSE_TEXT_DELTA:
            delta = raw.get("delta")
        elif etype == EVT_RESPONSE_AUDIO_DELTA:
            audio_b64 = raw.get("delta")
        elif etype == EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE:
            call_id = raw.get("call_id")
            try:
                arguments = json.loads(raw.get("arguments", "{}") or "{}")
            except Exception:  # noqa: BLE001
                arguments = {"_raw": raw.get("arguments", "")}
        elif etype == EVT_RESPONSE_DONE:
            response = raw.get("response", {}) or {}
            u = response.get("usage")
            if u:
                usage = u
        return cls(
            type=etype,
            raw=raw,
            delta=delta,
            audio_b64=audio_b64,
            item_id=raw.get("item_id"),
            response_id=raw.get("response_id") or (raw.get("response") or {}).get("id"),
            call_id=call_id,
            arguments=arguments,
            error=raw.get("error"),
            usage=usage,
        )


# Type for an "agent bridge": takes a function name + args, returns text result.
AgentBridge = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[str]]


class MockRealtimeProvider:
    """Drop-in mock that simulates the OpenAI Realtime API.

    Used when ``OPENAI_API_KEY`` is missing or for tests. Echoes the user's
    transcript back, but also handles tool calls by invoking a registered
    handler and returning its result.
    """

    provider_name = "mock_realtime"
    is_mock = True

    def __init__(self, config: RealtimeSessionConfig | None = None) -> None:
        self.config = config or RealtimeSessionConfig(model="mock-realtime-v1")
        self._usage = RealtimeUsage()
        self._agent_bridge: AgentBridge | None = None
        self._connected = False

    async def connect(self) -> "MockRealtimeProvider":
        self._connected = True
        return self

    def is_connected(self) -> bool:
        return self._connected

    def set_agent_bridge(self, bridge: AgentBridge) -> None:
        self._agent_bridge = bridge

    def get_usage(self) -> RealtimeUsage:
        return self._usage

    async def send_audio(self, pcm_b64: str) -> None:
        # 24kHz, 16-bit, mono = 48000 bytes/sec
        bytes_len = len(pcm_b64) * 3 // 4
        self._usage.audio_input_seconds += bytes_len / 48000.0
        self._usage.last_updated = time.time()

    async def commit_audio(self) -> None:
        # Pretend we got a transcript
        transcript = "[mock transcript: candidate said something]"
        await self._simulate_response(transcript)

    async def send_user_text(self, text: str) -> None:
        """Echo a canned response for text user messages."""
        self._usage.input_tokens += max(1, len(text) // 4)
        self._usage.last_updated = time.time()
        await self._simulate_response(text)

    async def _simulate_response(self, transcript: str) -> None:
        # Mock provider just records the response; consumers don't iterate.
        self._emit_text = f"你刚才说到:{transcript}。请继续。"
        self._usage.output_tokens += len(self._emit_text) // 2
        self._usage.audio_output_seconds += 1.5
        self._usage.last_updated = time.time()

    async def cancel_response(self) -> None:
        return None

    async def close(self) -> None:
        self._connected = False


class OpenAIRealtimeProvider:
    """Real OpenAI Realtime WebSocket provider.

    Requires the ``websockets`` library and a valid ``OPENAI_API_KEY``.
    Falls back to :class:`MockRealtimeProvider` when the key is missing.
    """

    provider_name = "openai_realtime"
    is_mock = False

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_REALTIME_MODEL,
        config: RealtimeSessionConfig | None = None,
        base_url: str = DEFAULT_REALTIME_URL,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.config = config or RealtimeSessionConfig(model=model)
        self._ws: Any = None
        self._usage = RealtimeUsage()
        self._agent_bridge: AgentBridge | None = None
        self._connected = False
        self._send_lock = asyncio.Lock()
        self._recv_task: asyncio.Task[None] | None = None
        self._out_queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def is_connected(self) -> bool:
        return self._connected

    def get_usage(self) -> RealtimeUsage:
        return self._usage

    def set_agent_bridge(self, bridge: AgentBridge) -> None:
        """Register a callable that handles function calls from the model.

        The bridge receives ``(function_name, arguments, context)`` and must
        return a string result that will be fed back to the model as
        ``conversation.item.create`` of role ``function``.
        """
        self._agent_bridge = bridge

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> AsyncIterator[RealtimeEvent]:
        """Open the WebSocket and yield events as they arrive.

        The first event yielded is always ``session.created`` (or
        ``error`` if connection failed).
        """
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; cannot connect to OpenAI Realtime API"
            )
        try:
            import websockets  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'websockets' library is required for OpenAI Realtime"
            ) from exc

        url = f"{self.base_url}?model={self.config.model}"
        headers = [
            ("Authorization", f"Bearer {self.api_key}"),
            ("OpenAI-Beta", "realtime=v1"),
        ]
        try:
            self._ws = await websockets.connect(
                url, extra_headers=headers, max_size=2**24
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Realtime WS connect failed: %s", e)
            yield RealtimeEvent(
                type=EVT_ERROR, raw={"type": EVT_ERROR}, error={"message": str(e)}
            )
            return
        self._connected = True
        # Apply session config
        await self._send_event(
            {
                "type": "session.update",
                "session": self.config.to_session_update(),
            }
        )
        # Spawn background reader
        self._recv_task = asyncio.create_task(self._reader_loop())
        # Yield events from queue
        while self._connected:
            try:
                evt = await asyncio.wait_for(self._out_queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                continue
            yield evt
            if evt.type == EVT_ERROR and not self._connected:
                break

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    payload = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                evt = RealtimeEvent.from_raw(payload)
                self._update_usage(evt)
                # If it's a function call, dispatch and feed result back.
                if (
                    evt.type == EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE
                    and evt.call_id
                    and self._agent_bridge
                ):
                    await self._dispatch_function_call(evt)
                await self._out_queue.put(evt)
        except Exception as e:  # noqa: BLE001
            logger.warning("Realtime reader loop ended: %s", e)
            self._connected = False
            await self._out_queue.put(
                RealtimeEvent(type=EVT_ERROR, raw={"type": EVT_ERROR}, error={"message": str(e)})
            )

    def _update_usage(self, evt: RealtimeEvent) -> None:
        if not evt.usage:
            return
        u = evt.usage
        self._usage.input_tokens = int(u.get("input_tokens", self._usage.input_tokens))
        self._usage.output_tokens = int(u.get("output_tokens", self._usage.output_tokens))
        # Realtime GA returns input_token_details / output_token_details with audio tokens
        in_det = u.get("input_token_details") or {}
        out_det = u.get("output_token_details") or {}
        if isinstance(in_det, dict) and in_det.get("audio_tokens") is not None:
            # approximate: 50 tokens/sec audio
            self._usage.audio_input_seconds = max(
                self._usage.audio_input_seconds,
                float(in_det.get("audio_tokens", 0)) / 50.0,
            )
        if isinstance(out_det, dict) and out_det.get("audio_tokens") is not None:
            self._usage.audio_output_seconds = max(
                self._usage.audio_output_seconds,
                float(out_det.get("audio_tokens", 0)) / 50.0,
            )
        self._usage.total_tokens = (
            self._usage.input_tokens + self._usage.output_tokens
        )
        self._usage.last_updated = time.time()

    async def _dispatch_function_call(self, evt: RealtimeEvent) -> None:
        if not self._agent_bridge or not evt.call_id:
            return
        try:
            result_text = await self._agent_bridge(
                (evt.raw.get("name") or ""), evt.arguments or {}, {"response_id": evt.response_id}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("agent_bridge error: %s", e)
            result_text = json.dumps({"error": str(e)}, ensure_ascii=False)
        # Feed result back to the model
        await self._send_event(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": evt.call_id,
                    "output": result_text[:8000],
                },
            }
        )
        # Trigger a new response
        await self._send_event({"type": "response.create"})

    # ------------------------------------------------------------------
    # Outbound events
    # ------------------------------------------------------------------
    async def _send_event(self, event: dict[str, Any]) -> None:
        if not self._ws:
            return
        async with self._send_lock:
            await self._ws.send(json.dumps(event))

    async def send_audio(self, pcm_b64: str) -> None:
        """Append a base64-encoded audio chunk to the input buffer."""
        await self._send_event(
            {"type": "input_audio_buffer.append", "audio": pcm_b64}
        )
        # 24kHz PCM16 mono = 48000 bytes/sec
        try:
            n_bytes = len(pcm_b64) * 3 // 4
            self._usage.audio_input_seconds += n_bytes / 48000.0
        except Exception:  # noqa: BLE001
            pass

    async def commit_audio(self) -> None:
        """Commit the current input buffer (with server VAD off)."""
        await self._send_event({"type": "input_audio_buffer.commit"})

    async def cancel_response(self) -> None:
        await self._send_event({"type": "response.cancel"})

    async def send_user_text(self, text: str) -> None:
        """Send a text user message (bypasses audio)."""
        await self._send_event(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        await self._send_event({"type": "response.create"})

    async def close(self) -> None:
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_realtime_provider(
    *,
    model: str | None = None,
    voice: str | None = None,
    instructions: str | None = None,
    force_mock: bool = False,
) -> "OpenAIRealtimeProvider | MockRealtimeProvider":
    """Return the best Realtime provider based on env / config.

    If ``force_mock`` is True or ``OPENAI_API_KEY`` is missing, returns a
    :class:`MockRealtimeProvider` so that tests and local dev still work.
    """
    config = RealtimeSessionConfig(
        model=model or DEFAULT_REALTIME_MODEL,
        voice=voice or DEFAULT_VOICE,
        instructions=instructions or RealtimeSessionConfig().instructions,
    )
    if force_mock or not os.environ.get("OPENAI_API_KEY"):
        logger.info("Realtime: using MockRealtimeProvider (no key or force_mock)")
        return MockRealtimeProvider(config=config)
    return OpenAIRealtimeProvider(config=config, model=config.model)


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def encode_pcm16_base64(pcm_bytes: bytes) -> str:
    """Encode raw PCM16 bytes to base64 for the Realtime API."""
    return base64.b64encode(pcm_bytes).decode("ascii")


def decode_audio_base64(audio_b64: str) -> bytes:
    """Decode base64 audio delta from the Realtime API."""
    try:
        return base64.b64decode(audio_b64)
    except Exception:  # noqa: BLE001
        return b""
