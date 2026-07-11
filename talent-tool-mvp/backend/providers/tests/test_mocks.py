"""mock 适配器 smoke test — 验证协议实现完整性."""
from __future__ import annotations

import pytest

from backend.providers.embedding.mock_provider import MockEmbeddingProvider
from backend.providers.llm.base import Message
from backend.providers.llm.mock_provider import MockLLMProvider
from backend.providers.lookup.mock_provider import MockLookupProvider
from backend.providers.notify.mock_provider import (
    MOCK_NOTIFY_REGISTRY,
    MockNotifyProvider,
    get_mock_notify_provider,
)
from backend.providers.notify.base import NotifyMessage
from backend.providers.ocr.mock_provider import MockOCRProvider
from backend.providers.stt.mock_provider import MockSTTProvider
from backend.providers.vision.base import ImageInput, VisionMessage
from backend.providers.vision.mock_provider import MockVisionProvider


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_llm_chat_reuses_runtime_router():
    """验证当 system 含 '情感智能助手' 时,会走 emotion 路由(返回 JSON)."""
    p = MockLLMProvider()
    msgs = [
        Message(role="system", content="你是一个情感智能助手"),
        Message(role="user", content="今天很开心"),
    ]
    resp = await p.chat(msgs)
    assert resp.model == "mock-model"
    assert '"joy"' in resp.content  # emotion 路由的 mock 输出含 joy


@pytest.mark.asyncio
async def test_mock_llm_stream_yields_chars():
    p = MockLLMProvider()
    msgs = [Message(role="user", content="hello")]
    chunks: list[str] = []
    async for ch in p.stream_chat(msgs):
        chunks.append(ch)
    assert "".join(chunks) == (await p.chat(msgs)).content


@pytest.mark.asyncio
async def test_mock_llm_tool_call_returns_empty():
    p = MockLLMProvider()
    msgs = [Message(role="user", content="hi")]
    tools = []
    result = await p.tool_call(msgs, tools)
    assert result.tool_calls == []


def test_mock_llm_supported_models_and_pricing():
    p = MockLLMProvider()
    assert "mock-model" in p.supported_models
    assert p.pricing["mock-model"] == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_embedding_deterministic():
    p = MockEmbeddingProvider()
    v1 = await p.embed_one("hello world")
    v2 = await p.embed_one("hello world")
    assert v1 == v2


@pytest.mark.asyncio
async def test_mock_embedding_different_inputs_different_vectors():
    p = MockEmbeddingProvider()
    v1 = await p.embed_one("hello")
    v2 = await p.embed_one("goodbye")
    assert v1 != v2
    assert len(v1) == p.dimensions


@pytest.mark.asyncio
async def test_mock_embedding_bulk():
    p = MockEmbeddingProvider()
    res = await p.embed(["a", "b", "c"])
    assert len(res.vectors) == 3
    assert res.dimensions == 16


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_vision_chat_with_images():
    p = MockVisionProvider()
    msgs = [
        VisionMessage(role="user", text="what is this", images=[ImageInput(url="http://x")])
    ]
    resp = await p.chat_with_images(msgs)
    assert "what is this" in resp.content
    assert resp.model == "mock-vision"


@pytest.mark.asyncio
async def test_mock_vision_ocr_returns_string():
    p = MockVisionProvider()
    text = await p.ocr(ImageInput(url="http://x/y.png"))
    assert isinstance(text, str)
    assert "http://x/y.png" in text


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_ocr_recognize_bytes():
    p = MockOCRProvider()
    res = await p.recognize(b"fake-bytes", mime="image/png", language="zh")
    assert "bytes=" in res.text and "image/png" in res.text
    assert res.confidence > 0.9


@pytest.mark.asyncio
async def test_mock_ocr_recognize_url():
    p = MockOCRProvider()
    res = await p.recognize_url("https://example.com/x.png", language="en")
    assert "example.com" in res.text


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_stt_transcribe():
    p = MockSTTProvider()
    res = await p.transcribe(b"\x00\x00", mime="audio/mpeg", language="zh")
    assert "zh" in res.text or "audio" in res.text
    assert res.duration >= 0.0


@pytest.mark.asyncio
async def test_mock_stt_transcribe_url():
    p = MockSTTProvider()
    res = await p.transcribe_url("https://example.com/audio.mp3")
    assert "example.com" in res.text


# ---------------------------------------------------------------------------
# Notify (5 通道)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["smtp", "dingtalk", "feishu", "wecom", "webhook"])
async def test_mock_notify_5_channels(channel: str):
    p = get_mock_notify_provider(channel)
    msg = NotifyMessage(subject="hi", body="hello", to=["a@x.com"])
    result = await p.send(msg)
    assert result.success is True
    assert result.channel == channel
    assert result.message_id is not None
    assert result.message_id.startswith(f"mock-{channel}-")


def test_mock_notify_registry_has_5_channels():
    assert len(MOCK_NOTIFY_REGISTRY) == 5
    assert set(MOCK_NOTIFY_REGISTRY) == {"smtp", "dingtalk", "feishu", "wecom", "webhook"}


def test_mock_notify_unknown_channel_falls_back_to_generic():
    p = get_mock_notify_provider("unknown-channel")
    assert isinstance(p, MockNotifyProvider)
    assert p.channel == "unknown-channel"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_lookup_search_returns_deterministic_count():
    p = MockLookupProvider()
    r1 = await p.search("Acme")
    r2 = await p.search("Acme")
    assert len(r1) == len(r2)
    assert len(r1) >= 1
    assert all(c.name.startswith("Acme") for c in r1)


@pytest.mark.asyncio
async def test_mock_lookup_get_detail():
    p = MockLookupProvider()
    info = await p.get_detail("MOCK0001")
    assert "MOCK0001" in info.name
    assert info.unified_social_credit_code == "MOCK0001"