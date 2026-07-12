"""语音转写服务 (T701).

设计:
    - 主 provider: STT_PROVIDER env 控制 (默认 mock)
    - 失败 → 自动降级到 aliyun_stt
    - 再失败 → 返回空文本 + fallback_reason,前端提示改用文本

API:
    transcribe_audio(audio: bytes, *, mime, language) -> TranscribeResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("recruittech.services.transcribe")


@dataclass
class TranscribeResult:
    text: str
    provider: str
    language: str | None = None
    duration_sec: float = 0.0
    segments: list[dict[str, Any]] | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------
async def transcribe_audio(
    audio: bytes,
    *,
    mime: str = "audio/webm",
    language: str = "auto",
    primary_provider: str | None = None,
) -> TranscribeResult:
    """先尝试 primary (默认 = STT_PROVIDER env),失败降级到 aliyun_stt.

    Returns:
        TranscribeResult(text="...", provider="whisper"|"aliyun_stt"|"mock_stt")
    """
    import os

    from providers.registry import get_stt_provider

    target = (primary_provider or os.getenv("STT_PROVIDER") or "mock").lower()
    errors: list[str] = []

    # 1) primary
    primary = None
    try:
        primary = get_stt_provider()
    except Exception as e:  # noqa: BLE001
        errors.append(f"primary_init_failed: {e}")

    if primary is not None and getattr(primary, "provider_name", "") != target and target not in ("mock", ""):
        # 如果用户传了 specific provider 但当前实例不是它,跳过走 fallback
        try:
            primary = _init_specific(target)
        except Exception as e:  # noqa: BLE001
            errors.append(f"init_specific({target}): {e}")
            primary = None

    if primary is not None:
        try:
            res = await primary.transcribe(audio, mime=mime, language=language)
            return TranscribeResult(
                text=res.text or "",
                provider=getattr(primary, "provider_name", target),
                language=res.language,
                duration_sec=res.duration,
                segments=res.segments,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"primary_failed: {e}")
            logger.warning(f"transcribe primary failed: {e}")

    # 2) fallback aliyun (只要 primary 不是 aliyun)
    if target != "aliyun":
        try:
            fallback = _init_specific("aliyun")
            res = await fallback.transcribe(audio, mime=mime, language=language)
            return TranscribeResult(
                text=res.text or "",
                provider="aliyun_stt",
                language=res.language,
                duration_sec=res.duration,
                segments=res.segments,
                fallback_used=True,
                fallback_reason=errors[-1] if errors else "primary_unavailable",
                errors=errors,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"aliyun_failed: {e}")
            logger.warning(f"transcribe aliyun fallback failed: {e}")

    # 3) 全失败 → mock 兜底,返回空但 success=False 标志
    return TranscribeResult(
        text="",
        provider="none",
        fallback_used=True,
        fallback_reason="all_failed",
        errors=errors,
    )


def _init_specific(name: str) -> Any:
    """按 provider name 临时构造一个 STT 实例(不走 registry 缓存)。"""
    from providers.stt import AliyunSTTProvider, WhisperProvider

    mapping = {
        "whisper": WhisperProvider,
        "aliyun": AliyunSTTProvider,
    }
    cls = mapping.get(name)
    if cls is None:
        raise ValueError(f"unknown STT provider: {name}")
    return cls()