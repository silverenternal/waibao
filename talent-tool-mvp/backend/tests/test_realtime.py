"""T2201 — GPT-4o Realtime tests.

Covers:
- Mock realtime provider (default; no API key needed)
- RealtimeSession lifecycle
- HTTP session CRUD endpoints
- WebSocket bidirectional flow
- Latency / usage tracking
- Agent bridge (function call) roundtrip

There is also one optional integration test (skipped unless
``OPENAI_API_KEY`` is set in the environment).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Mock provider unit tests
# ---------------------------------------------------------------------------
def test_realtime_event_from_raw_text_delta():
    from providers.llm.openai_realtime import (
        EVT_RESPONSE_TEXT_DELTA,
        RealtimeEvent,
    )
    raw = {"type": "response.text.delta", "delta": "你好", "response_id": "r1"}
    evt = RealtimeEvent.from_raw(raw)
    assert evt.type == EVT_RESPONSE_TEXT_DELTA
    assert evt.delta == "你好"
    assert evt.response_id == "r1"


def test_realtime_event_from_raw_audio_delta():
    from providers.llm.openai_realtime import (
        EVT_RESPONSE_AUDIO_DELTA,
        RealtimeEvent,
    )
    raw = {"type": "response.audio.delta", "delta": "AAA="}
    evt = RealtimeEvent.from_raw(raw)
    assert evt.type == EVT_RESPONSE_AUDIO_DELTA
    assert evt.audio_b64 == "AAA="


def test_realtime_event_from_raw_function_call():
    from providers.llm.openai_realtime import (
        EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE,
        RealtimeEvent,
    )
    raw = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_123",
        "name": "get_weather",
        "arguments": '{"city": "北京"}',
    }
    evt = RealtimeEvent.from_raw(raw)
    assert evt.type == EVT_RESPONSE_FUNCTION_CALL_ARGS_DONE
    assert evt.call_id == "call_123"
    assert evt.arguments == {"city": "北京"}


def test_realtime_event_bad_json_args():
    from providers.llm.openai_realtime import RealtimeEvent
    raw = {
        "type": "response.function_call_arguments.done",
        "call_id": "c1",
        "name": "x",
        "arguments": "{not json",
    }
    evt = RealtimeEvent.from_raw(raw)
    assert evt.arguments == {"_raw": "{not json"}


def test_session_config_to_session_update():
    from providers.llm.openai_realtime import RealtimeSessionConfig
    cfg = RealtimeSessionConfig(voice="shimmer", temperature=0.5)
    body = cfg.to_session_update()
    assert body["voice"] == "shimmer"
    assert body["temperature"] == 0.5
    assert body["model"].startswith("gpt-4o")
    assert "tools" not in body
    cfg2 = RealtimeSessionConfig(tools=[{"type": "function", "name": "f"}])
    body2 = cfg2.to_session_update()
    assert body2["tools"] == [{"type": "function", "name": "f"}]


def test_encode_decode_pcm16():
    from providers.llm.openai_realtime import (
        decode_audio_base64,
        encode_pcm16_base64,
    )
    raw = b"\x00\x01\x02hello world\xff\xfe"
    b64 = encode_pcm16_base64(raw)
    assert isinstance(b64, str)
    assert decode_audio_base64(b64) == raw


def test_get_realtime_provider_mock_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from providers.llm.openai_realtime import (
        MockRealtimeProvider,
        get_realtime_provider,
    )
    p = get_realtime_provider()
    assert isinstance(p, MockRealtimeProvider)
    assert p.is_connected() is False
    p2 = get_realtime_provider(force_mock=True)
    assert isinstance(p2, MockRealtimeProvider)


def test_usage_to_dict():
    from providers.llm.openai_realtime import RealtimeUsage
    u = RealtimeUsage(input_tokens=100, output_tokens=50, total_tokens=150, audio_input_seconds=2.0, audio_output_seconds=3.5)
    d = u.to_dict()
    assert d["input_tokens"] == 100
    assert d["output_tokens"] == 50
    assert d["total_tokens"] == 150
    assert d["audio_input_seconds"] == 2.0
    assert d["audio_output_seconds"] == 3.5


# ---------------------------------------------------------------------------
# Session service tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_start_stop_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import RealtimeSession

    cfg = RealtimeSessionConfig(voice="alloy")
    sess = RealtimeSession(
        session_id="rts_test1",
        user_id="u1",
        conversation_id="c1",
        config=cfg,
        force_mock=True,
    )
    # Track dispatches
    events: list[dict[str, Any]] = []

    async def dispatch(p: dict[str, Any]) -> None:
        events.append(p)

    sess.dispatch = dispatch
    await sess.start()
    await asyncio.sleep(0.2)
    # Push some audio (PCM16 base64)
    pcm = base64.b64encode(b"\x00\x10" * 480).decode("ascii")  # ~0.01 sec
    await sess.push_audio(pcm)
    await sess.push_text("你好")
    await sess.interrupt()
    await asyncio.sleep(0.3)
    await sess.stop()
    # Should have emitted at least: ready, vad_speech_start, vad_speech_stop, text_delta
    types = [e["type"] for e in events]
    assert "ready" in types
    assert "interrupted" in types
    # First audio latency should be set
    assert sess.metrics.first_audio_latency_ms is not None
    assert sess.metrics.first_audio_latency_ms >= 0
    # At least one audio chunk was tracked
    assert sess.metrics.audio_input_chunks >= 1


@pytest.mark.asyncio
async def test_session_compressor_truncates():
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import (
        ContextCompressor,
        RealtimeSession,
        TranscriptTurn,
    )
    cfg = RealtimeSessionConfig()
    sess = RealtimeSession(
        session_id="rts_test2",
        user_id="u1",
        conversation_id="c1",
        config=cfg,
        force_mock=True,
    )
    for i in range(50):
        sess.compressor.add(TranscriptTurn(role="user", text=f"turn {i} " * 10))
    # After 50 > max_turns * 2, compressor should have summarised
    assert sess.compressor.summary != ""
    assert len(sess.compressor.turns) <= 40


@pytest.mark.asyncio
async def test_session_get_transcript_returns_dicts():
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import (
        RealtimeSession,
        TranscriptTurn,
    )
    sess = RealtimeSession(
        session_id="rts_test3",
        user_id="u1",
        conversation_id="c1",
        config=RealtimeSessionConfig(),
        force_mock=True,
    )
    sess.compressor.add(TranscriptTurn(role="user", text="hi"))
    sess.compressor.add(TranscriptTurn(role="assistant", text="hello"))
    transcript = sess.get_transcript()
    assert len(transcript) == 2
    assert transcript[0]["role"] == "user"
    assert transcript[1]["role"] == "assistant"
    assert "audio_bytes" in transcript[0]


@pytest.mark.asyncio
async def test_session_metrics_to_dict():
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import RealtimeSession
    sess = RealtimeSession(
        session_id="rts_test4",
        user_id="u1",
        conversation_id="c1",
        config=RealtimeSessionConfig(),
        force_mock=True,
    )
    sess.metrics.audio_input_chunks = 5
    sess.metrics.audio_output_chunks = 3
    sess.metrics.function_calls = 1
    d = sess.metrics.to_dict()
    assert d["audio_input_chunks"] == 5
    assert d["audio_output_chunks"] == 3
    assert d["function_calls"] == 1
    assert "usage" in d


@pytest.mark.asyncio
async def test_session_registry_register_unregister():
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import (
        RealtimeSession,
        SessionRegistry,
    )
    reg = SessionRegistry()
    sess = RealtimeSession(
        session_id="rts_test5",
        user_id="u1",
        conversation_id="c1",
        config=RealtimeSessionConfig(),
        force_mock=True,
    )
    await reg.register(sess)
    assert reg.get("rts_test5") is sess
    await reg.unregister("rts_test5")
    assert reg.get("rts_test5") is None


def test_make_session_id_format():
    from services.platform.realtime_session import make_session_id
    sid = make_session_id()
    assert sid.startswith("rts_")
    assert len(sid) >= 10


# ---------------------------------------------------------------------------
# API HTTP tests (FastAPI TestClient)
# ---------------------------------------------------------------------------
def test_api_create_session(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from main import app

    # Skip auth for unit test by patching the dependency
    from api.auth import get_current_user
    from api.auth import CurrentUser

    class DummyUser:
        id = "test-user"
        email = "test@example.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/realtime-v2/sessions",
            json={"model": "gpt-4o-realtime-preview", "voice": "alloy"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"].startswith("rts_")
        assert data["model"] == "gpt-4o-realtime-preview"
        assert data["voice"] == "alloy"
        assert data["ws_path"].startswith("/api/realtime-v2/ws/")

        # list
        r2 = client.get("/api/realtime-v2/sessions")
        assert r2.status_code == 200
        assert r2.json()["count"] == 1

        # get
        r3 = client.get(f"/api/realtime-v2/sessions/{data['id']}")
        assert r3.status_code == 200
        assert r3.json()["id"] == data["id"]

        # delete
        r4 = client.delete(f"/api/realtime-v2/sessions/{data['id']}")
        assert r4.status_code == 200
        assert r4.json()["ok"] is True
    finally:
        app.dependency_overrides.clear()


def test_api_create_session_with_tools(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/realtime-v2/sessions",
            json={
                "model": "gpt-4o-realtime-preview",
                "voice": "shimmer",
                "tools": [
                    {
                        "type": "function",
                        "name": "get_weather",
                        "description": "Get current weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    }
                ],
            },
        )
        assert r.status_code == 200
        cfg = r.json()["config"]
        assert cfg["voice"] == "shimmer"
        assert len(cfg["tools"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_api_get_unknown_session(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.get("/api/realtime-v2/sessions/rts_does_not_exist")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# WebSocket end-to-end
# ---------------------------------------------------------------------------
def test_websocket_roundtrip(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-ws"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post("/api/realtime-v2/sessions", json={})
        assert r.status_code == 200
        sid = r.json()["id"]

        with client.websocket_connect(
            f"/api/realtime-v2/ws/{sid}?token=dev%3Au-ws"
        ) as ws:
            # Drain 'connected' and 'ready' with a hard timeout
            connected = ws.receive_json()
            assert connected["type"] == "connected"
            ready = ws.receive_json()
            # 'ready' or 'vad_speech_start' depending on timing
            assert ready["type"] in {"ready", "vad_speech_start", "audio_committed"}
            # Send a text message → expect 'user_text' back
            ws.send_json({"type": "text", "text": "你好"})
            seen_user_text = False
            deadline = time.time() + 4
            while time.time() < deadline and not seen_user_text:
                try:
                    msg = ws.receive_json()
                    if msg.get("type") == "user_text":
                        seen_user_text = True
                        break
                except Exception:
                    break
            assert seen_user_text, "expected 'user_text' event after text send"
            # Stop
            ws.send_json({"type": "stop"})
            try:
                ws.receive_json()
            except Exception:
                pass
    finally:
        app.dependency_overrides.clear()


def test_websocket_interrupt_event(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-int"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post("/api/realtime-v2/sessions", json={})
        sid = r.json()["id"]
        with client.websocket_connect(
            f"/api/realtime-v2/ws/{sid}?token=dev%3Au-int"
        ) as ws:
            ws.receive_json()  # connected
            # Skip 'ready' — send interrupt directly
            ws.send_json({"type": "interrupt"})
            deadline = time.time() + 3
            got = False
            while time.time() < deadline:
                try:
                    m = ws.receive_json()
                    if m.get("type") == "interrupted":
                        got = True
                        break
                except Exception:
                    break
            assert got, "expected 'interrupted' event"
            ws.send_json({"type": "stop"})
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Latency benchmark (mock)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_latency_first_audio_under_threshold(monkeypatch):
    """Even with mock, first-audio latency should be well under 500ms."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from providers.llm.openai_realtime import RealtimeSessionConfig
    from services.platform.realtime_session import RealtimeSession

    sess = RealtimeSession(
        session_id="rts_lat",
        user_id="u",
        conversation_id="c",
        config=RealtimeSessionConfig(),
        force_mock=True,
    )

    async def _noop(_: dict[str, Any]) -> None:
        pass

    sess.dispatch = _noop
    await sess.start()
    # Wait for ready
    await asyncio.sleep(0.1)
    t0 = time.time()
    await sess.push_audio(base64.b64encode(b"\x00" * 480).decode("ascii"))
    latency_ms = (time.time() - t0) * 1000
    assert latency_ms < 500, f"first audio push too slow: {latency_ms}ms"
    assert sess.metrics.first_audio_latency_ms is not None
    assert sess.metrics.first_audio_latency_ms < 500
    await sess.stop()


# ---------------------------------------------------------------------------
# Optional real GPT-4o Realtime integration test
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ
    or os.environ.get("OPENAI_API_KEY", "").startswith("sk-test"),
    reason="OPENAI_API_KEY not set or is a test dummy; skipping real GPT-4o Realtime integration test",
)
@pytest.mark.asyncio
async def test_real_gpt4o_realtime_connect_and_disconnect():
    """Real integration smoke test — connects, emits session.created, closes."""
    from providers.llm.openai_realtime import (
        EVT_SESSION_CREATED,
        OpenAIRealtimeProvider,
        RealtimeSessionConfig,
    )

    cfg = RealtimeSessionConfig(model="gpt-4o-realtime-preview", voice="alloy")
    provider = OpenAIRealtimeProvider(config=cfg)
    assert provider.is_connected() is False
    seen_created = False
    try:
        async for evt in provider.connect():
            if evt.type == EVT_SESSION_CREATED:
                seen_created = True
                break
            if evt.type == "error":
                pytest.skip(f"realtime error: {evt.error}")
                return
            # timeout
            if not provider.is_connected():
                break
    finally:
        await provider.close()
    assert seen_created, "did not receive session.created event"
