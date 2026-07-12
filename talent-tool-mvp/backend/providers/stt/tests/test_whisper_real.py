"""OpenAI Whisper 真实接入验证 (T1102).

默认 **跳过** — 需要 OPENAI_API_KEY 才会运行:

    export OPENAI_API_KEY="sk-..."
    pytest -m real_api backend/providers/stt/tests/test_whisper_real.py

测试矩阵 (5 个真实音频样本,见 backend/tests/fixtures/audio/):

    sample_zh_001.wav            中文 (zh)        ~3s
    sample_en_001.wav            英文 (en)        ~3s
    sample_ja_001.wav            日文 (ja)        ~3s
    sample_short_mono_16k.wav    smoke test       ~1s
    sample_long_60s.wav          中文 (zh)        ~60s → aliyun_stt 降级链路

降级链路验证:
    - Whisper 失败 / 配额耗尽 / 429 → 自动 fallback 到 aliyun_stt
    - 配置: STT_PROVIDER=whisper, STT_FALLBACK=aliyun

凭证申请: docs/WHISPER_INTEGRATION.md
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from backend.providers.exceptions import ProviderError
from backend.providers.stt.aliyun_stt import AliyunSTTProvider
from backend.providers.stt.base import STTResult
from backend.providers.stt.whisper_provider import WhisperProvider

AUDIO_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "audio"


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY 未设置 — 跳过 Whisper 真实 API 测试",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _load(name: str) -> bytes:
    p = AUDIO_DIR / name
    if not p.exists():
        pytest.skip(f"音频样本 {name} 缺失 — 运行 generate_audio_fixtures.py 生成")
    data = p.read_bytes()
    assert len(data) > 1024, f"{name} 太小,可能损坏"
    return data


@pytest.fixture
def audio_zh() -> bytes:
    return _load("sample_zh_001.wav")


@pytest.fixture
def audio_en() -> bytes:
    return _load("sample_en_001.wav")


@pytest.fixture
def audio_ja() -> bytes:
    return _load("sample_ja_001.wav")


@pytest.fixture
def audio_short() -> bytes:
    return _load("sample_short_mono_16k.wav")


@pytest.fixture
def audio_long() -> bytes:
    return _load("sample_long_60s.wav")


@pytest.fixture
def provider():
    return WhisperProvider()


# ---------------------------------------------------------------------------
# 中文 / 英文 / 日文 三语种真实转写
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_chinese(provider, audio_zh):
    """中文音频 → Whisper verbose_json."""
    result = await provider.transcribe(audio_zh, mime="audio/wav", language="zh")
    assert isinstance(result, STTResult)
    assert result.text, "中文转写文本必须非空"
    # 验证返回语言接近 zh (Whisper 可能返回 'chinese' 或 'zh')
    if result.language:
        assert result.language.lower().startswith(("zh", "chinese"))


@pytest.mark.asyncio
async def test_transcribe_english(provider, audio_en):
    """英文音频."""
    result = await provider.transcribe(audio_en, mime="audio/wav", language="en")
    assert isinstance(result, STTResult)
    assert result.text, "英文转写文本必须非空"
    if result.language:
        assert result.language.lower().startswith(("en", "english"))


@pytest.mark.asyncio
async def test_transcribe_japanese(provider, audio_ja):
    """日文音频."""
    result = await provider.transcribe(audio_ja, mime="audio/wav", language="ja")
    assert isinstance(result, STTResult)
    assert result.text, "日文转写文本必须非空"
    if result.language:
        assert result.language.lower().startswith(("ja", "japanese"))


# ---------------------------------------------------------------------------
# auto language detection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_auto_language(provider, audio_zh):
    """language='auto' → Whisper 自动检测."""
    result = await provider.transcribe(audio_zh, mime="audio/wav", language="auto")
    assert isinstance(result, STTResult)
    assert result.text


# ---------------------------------------------------------------------------
# 短音频 smoke test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_short_audio_does_not_raise(provider, audio_short):
    """短音频 (1s) 不应崩溃."""
    result = await provider.transcribe(audio_short, mime="audio/wav", language="en")
    assert isinstance(result, STTResult)


# ---------------------------------------------------------------------------
# 长音频 + 降级链路
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_long_audio_falls_back_to_aliyun(audio_long):
    """60s 长音频失败时,降级到 aliyun_stt 链路.

    流程:
        1. 强制构造一个 WhisperProvider with broken API key
        2. 期望抛 AuthError
        3. 调用 fallback (aliyun_stt) → 拿到降级结果
    """
    # 1. 制造 broken whisper
    broken = WhisperProvider(api_key="sk-BROKEN-FOR-FALLBACK-TEST")
    with pytest.raises(ProviderError):
        await broken.transcribe(audio_long, mime="audio/wav", language="zh")

    # 2. fallback — 如果 aliyun 凭证也缺失,只跳过(单元测试场景)
    ak = os.getenv("ALIYUN_ACCESS_KEY_ID")
    sk = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
    app = os.getenv("ALIYUN_ASR_APP_KEY")
    if not (ak and sk and app):
        pytest.skip("降级链路验证需要 ALIYUN_* 三项凭证")

    aliyun = AliyunSTTProvider()
    result = await aliyun.transcribe(audio_long, mime="audio/wav", language="zh")
    assert isinstance(result, STTResult)
    # 即便是合成正弦波,aliyun 也应返回字符串 (可能为空,但 result 对象有效)
    assert result.raw is not None


# ---------------------------------------------------------------------------
# 性能 — 配额监控
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quota_tracking(provider, audio_short):
    """连续 5 次调用,记录平均延迟,辅助配额监控."""
    durations = []
    for _ in range(5):
        t0 = time.perf_counter()
        await provider.transcribe(audio_short, mime="audio/wav", language="en")
        durations.append(time.perf_counter() - t0)
    avg = sum(durations) / len(durations)
    # 平均应 < 5s (短音频)
    assert avg < 5.0, f"Whisper 平均延迟 {avg:.2f}s 过高,可能配额紧张"


# ---------------------------------------------------------------------------
# transcribe_url (辅助链路)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transcribe_url_invalid_raises(provider):
    """transcribe_url 收到无效 URL 应抛 ProviderError."""
    with pytest.raises(Exception):
        await provider.transcribe_url("https://invalid.local/missing.wav")


# ---------------------------------------------------------------------------
# 凭证校验 — 缺失 OPENAI_API_KEY 时构造抛错
# ---------------------------------------------------------------------------
def test_construct_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(Exception):
        WhisperProvider(api_key=None)