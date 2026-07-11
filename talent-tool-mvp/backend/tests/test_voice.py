"""T701 — Voice Journal end-to-end tests.

覆盖:
    - transcribe_audio service (success / fallback / all-failed)
    - /api/voice/transcribe (multipart upload → response shape)
    - /api/voice/submit (triggers journal + emotion agents)
    - error path: empty audio, too-large, missing text
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------
class _FakeSTT:
    provider_name = "whisper"

    def __init__(self, text="hello world", language="en", duration=2.5, exc=None):
        self.text = text
        self.language = language
        self.duration = duration
        self.exc = exc

    async def transcribe(self, audio, *, mime="audio/webm", language="auto", **kw):
        from providers.stt.base import STTResult

        if self.exc:
            raise self.exc
        return STTResult(text=self.text, language=self.language, duration=self.duration)


class _FakeAliyun(_FakeSTT):
    provider_name = "aliyun_stt"


@pytest.mark.asyncio
async def test_transcribe_primary_success():
    from services.transcribe import transcribe_audio

    with patch("services.transcribe._init_specific", return_value=_FakeSTT("hi")):
        res = await transcribe_audio(b"\x00\x00", mime="audio/webm", primary_provider="whisper")
    assert res.text == "hi"
    assert res.provider == "whisper"
    assert res.fallback_used is False
    assert res.errors == []


@pytest.mark.asyncio
async def test_transcribe_fallback_to_aliyun_on_primary_failure():
    from services.transcribe import transcribe_audio

    primary = _FakeSTT(exc=RuntimeError("upstream down"))
    aliyun = _FakeAliyun("降级文本")
    calls = {"primary": 0, "aliyun": 0}

    def fake_init(name):
        calls[name] = calls.get(name, 0) + 1
        if name == "whisper":
            return primary
        if name == "aliyun":
            return aliyun
        raise ValueError(name)

    with patch("services.transcribe._init_specific", side_effect=fake_init):
        res = await transcribe_audio(b"\x00\x00", primary_provider="whisper")
    assert res.text == "降级文本"
    assert res.provider == "aliyun_stt"
    assert res.fallback_used is True
    assert "primary_failed" in (res.errors[0] if res.errors else "")


@pytest.mark.asyncio
async def test_transcribe_all_failed_returns_empty():
    from services.transcribe import transcribe_audio

    primary = _FakeSTT(exc=RuntimeError("a"))
    aliyun = _FakeAliyun(exc=RuntimeError("b"))

    def fake_init(name):
        return primary if name == "whisper" else aliyun

    with patch("services.transcribe._init_specific", side_effect=fake_init):
        res = await transcribe_audio(b"\x00\x00", primary_provider="whisper")
    assert res.text == ""
    assert res.provider == "none"
    assert res.fallback_used is True
    assert res.fallback_reason == "all_failed"


@pytest.mark.asyncio
async def test_transcribe_init_specific_unknown_raises():
    from services.transcribe import _init_specific

    with pytest.raises(ValueError):
        _init_specific("doesnotexist")


@pytest.mark.asyncio
async def test_transcribe_result_dataclass_defaults():
    from services.transcribe import TranscribeResult

    r = TranscribeResult(text="x", provider="mock_stt")
    assert r.duration_sec == 0.0
    assert r.fallback_used is False
    assert r.errors == []
    assert r.segments is None


# ---------------------------------------------------------------------------
# API layer — /api/voice/transcribe
# ---------------------------------------------------------------------------
def _make_upload(content: bytes, mime: str = "audio/webm"):
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    f = io.BytesIO(content)
    uf = UploadFile(filename="voice.webm", file=f)
    # manually patch content_type
    uf.headers = Headers({"content-type": mime})
    return uf


@pytest.mark.asyncio
async def test_voice_transcribe_success():
    from api.voice import transcribe_endpoint

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"

    upload = _make_upload(b"\x00\x01\x02")

    with patch("api.voice.transcribe_audio", new=AsyncMock(return_value=MagicMock(
        text="识别结果",
        provider="whisper",
        language="zh",
        duration=3.0,
        fallback_used=False,
        fallback_reason=None,
        errors=[],
    ))):
        out = await transcribe_endpoint(
            audio=upload,
            language="zh",
            primary_provider=None,
            user=fake_user,
        )
    assert out["success"] is True
    assert out["text"] == "识别结果"
    assert out["provider"] == "whisper"


@pytest.mark.asyncio
async def test_voice_transcribe_empty_audio_rejected():
    from api.voice import transcribe_endpoint
    from fastapi import HTTPException

    upload = _make_upload(b"")
    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"
    with pytest.raises(HTTPException) as exc:
        await transcribe_endpoint(
            audio=upload,
            language="auto",
            primary_provider=None,
            user=fake_user,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_voice_transcribe_all_failed_returns_shape():
    from api.voice import transcribe_endpoint

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"
    upload = _make_upload(b"\x00\x01")

    with patch("api.voice.transcribe_audio", new=AsyncMock(return_value=MagicMock(
        text="",
        provider="none",
        fallback_used=True,
        fallback_reason="all_failed",
        errors=["x"],
    ))):
        out = await transcribe_endpoint(
            audio=upload,
            language="auto",
            primary_provider=None,
            user=fake_user,
        )
    assert out["success"] is False
    assert out["provider"] == "none"
    assert "改用文本" in out["message"]


# ---------------------------------------------------------------------------
# API layer — /api/voice/submit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_voice_submit_success_runs_both_agents():
    from api.voice import submit_voice_journal, VoiceSubmitBody

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"

    journal_out = MagicMock(artifacts={
        "rating": "good",
        "advice": "继续保持",
        "warnings": [],
        "action_items": ["行动A"],
    })
    emotion_out = MagicMock(artifacts={
        "valence": 0.7,
        "arousal": 0.3,
        "flags": [],
        "summary": "积极",
    })

    with patch("api.voice.registry") as reg:
        reg.get_or_raise.side_effect = lambda n: {
            "daily_journal_agent": AsyncMock(run=AsyncMock(return_value=journal_out)),
            "emotion_agent": AsyncMock(run=AsyncMock(return_value=emotion_out)),
        }[n]
        out = await submit_voice_journal(
            VoiceSubmitBody(text="今天心情不错"),
            user=fake_user,
        )
    assert out["success"] is True
    assert out["journal"]["rating"] == "good"
    assert out["journal"]["action_items"] == ["行动A"]
    assert out["emotion"]["valence"] == 0.7


@pytest.mark.asyncio
async def test_voice_submit_empty_text_rejected():
    from api.voice import submit_voice_journal, VoiceSubmitBody
    from fastapi import HTTPException

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"

    with pytest.raises(HTTPException):
        await submit_voice_journal(
            VoiceSubmitBody(text="   "),
            user=fake_user,
        )


@pytest.mark.asyncio
async def test_voice_submit_agent_failure_does_not_break():
    from api.voice import submit_voice_journal, VoiceSubmitBody

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"

    with patch("api.voice.registry") as reg:
        reg.get_or_raise.side_effect = RuntimeError("agent broken")
        out = await submit_voice_journal(
            VoiceSubmitBody(text="hi"),
            user=fake_user,
        )
    # 全部失败 → success=True (因为 agents 是 best-effort) 但 artifacts 都空
    assert out["success"] is True
    # rating/advice default to None when no agent output
    assert out["journal"]["rating"] is None
    assert out["journal"]["advice"] is None
    assert out["journal"]["warnings"] == []
    assert out["emotion"]["valence"] is None


# ---------------------------------------------------------------------------
# Edge case: very large audio is rejected with 413
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_voice_transcribe_oversized_audio():
    from api.voice import transcribe_endpoint
    from fastapi import HTTPException

    big = b"\x00" * (26 * 1024 * 1024)  # 26MB > 25MB limit
    upload = _make_upload(big)
    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "jobseeker"
    with pytest.raises(HTTPException) as exc:
        await transcribe_endpoint(
            audio=upload,
            language="auto",
            primary_provider=None,
            user=fake_user,
        )
    assert exc.value.status_code == 413