"""Voice API (T701) — 上传音频 → 转写 → 自动触发 Daily Journal + Emotion Agent.

Endpoints:
    POST /api/voice/transcribe    multipart upload → 转写文本
    POST /api/voice/submit        JSON {text, ...} → 触发 agents
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from services.transcribe import transcribe_audio

logger = logging.getLogger("recruittech.api.voice")
router = APIRouter()

# 允许的 mime / 大小
ALLOWED_MIMES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-m4a"}
MAX_BYTES = 25 * 1024 * 1024  # 25MB


class VoiceSubmitBody(BaseModel):
    text: str
    mood_score: Optional[float] = None
    language: Optional[str] = "auto"
    provider: Optional[str] = None
    duration_sec: Optional[float] = None


@router.post("/transcribe")
async def transcribe_endpoint(
    audio: UploadFile = File(...),
    language: str = Form("auto"),
    primary_provider: Optional[str] = Form(None),
    user: CurrentUser = Depends(get_current_user),
):
    """上传音频 → 转写 → 返回文本 + provider。

    失败 (provider 全挂) → 返回 success=False,前端提示改用文本。
    """
    blob = await audio.read()
    if not blob:
        raise HTTPException(status_code=400, detail="empty audio")
    if len(blob) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"audio too large > {MAX_BYTES}")

    mime = (audio.content_type or "audio/webm").lower()
    if mime not in ALLOWED_MIMES:
        # 允许常见 mime
        mime = "audio/webm"

    result = await transcribe_audio(
        blob,
        mime=mime,
        language=language or "auto",
        primary_provider=primary_provider,
    )

    if not result.text and result.provider == "none":
        return {
            "success": False,
            "text": "",
            "provider": "none",
            "fallback_used": True,
            "fallback_reason": result.fallback_reason or "all_failed",
            "errors": result.errors,
            "message": "语音转写暂时不可用,请改用文本输入",
        }

    return {
        "success": True,
        "text": result.text,
        "provider": result.provider,
        "language": result.language,
        "duration_sec": result.duration_sec,
        "fallback_used": result.fallback_used,
        "fallback_reason": result.fallback_reason,
    }


@router.post("/submit")
async def submit_voice_journal(
    body: VoiceSubmitBody,
    user: CurrentUser = Depends(get_current_user),
):
    """转写后的文本 → 触发 Daily Journal Agent + Emotion Agent."""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    journal_artifacts: dict = {}
    emotion_artifacts: dict = {}

    # Daily Journal Agent
    try:
        journal_agent = registry.get_or_raise("daily_journal_agent")
        out = await journal_agent.run(AgentInput(
            user_id=str(user.id),
            persona=user.role.value,
            text=body.text,
            context={
                "mood_score": body.mood_score,
                "source": "voice",
                "provider": body.provider,
                "duration_sec": body.duration_sec,
                "language": body.language,
            },
        ))
        journal_artifacts = out.artifacts or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"voice.submit journal_agent failed: {e}")
        journal_artifacts = {"error": str(e)}

    # Emotion Agent
    try:
        emotion_agent = registry.get_or_raise("emotion_agent")
        out = await emotion_agent.run(AgentInput(
            user_id=str(user.id),
            persona=user.role.value,
            text=body.text,
        ))
        emotion_artifacts = out.artifacts or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"voice.submit emotion_agent failed: {e}")
        emotion_artifacts = {"error": str(e)}

    return {
        "success": True,
        "journal": {
            "rating": journal_artifacts.get("rating"),
            "advice": journal_artifacts.get("advice"),
            "warnings": journal_artifacts.get("warnings", []),
            "action_items": journal_artifacts.get("action_items", []),
        },
        "emotion": {
            "valence": emotion_artifacts.get("valence"),
            "arousal": emotion_artifacts.get("arousal"),
            "flags": emotion_artifacts.get("flags", []),
            "summary": emotion_artifacts.get("summary"),
        },
    }