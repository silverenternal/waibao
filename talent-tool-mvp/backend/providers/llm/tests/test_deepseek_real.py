"""DeepSeek 真实 LLM 接入验证 (T1701).

默认 **跳过** — 需要 DEEPSEEK_API_KEY:

    export DEEPSEEK_API_KEY="sk-..."
    pytest -m real_api backend/providers/llm/tests/test_deepseek_real.py

凭证申请: docs/REAL_API_SETUP.md (1.3 DeepSeek)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.llm.base import Message
from backend.providers.llm.deepseek_provider import DeepSeekProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("DEEPSEEK_API_KEY"),
        reason="DEEPSEEK_API_KEY 未设置 — 跳过 DeepSeek 真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return DeepSeekProvider(default_model="deepseek-chat")


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    assert provider.api_key.startswith("sk-")


@pytest.mark.asyncio
async def test_chat_deepseek_chat(provider):
    msgs = [Message(role="user", content="一句话回复 'pong'")]
    resp = await provider.chat(msgs, model="deepseek-chat", max_tokens=20)
    assert resp.content
    assert resp.usage.input_tokens > 0


@pytest.mark.asyncio
async def test_stream_chat_yields_chunks(provider):
    msgs = [Message(role="user", content="你好")]
    chunks: list[str] = []
    async for chunk in provider.stream_chat(msgs, model="deepseek-chat", max_tokens=30):
        if chunk.content:
            chunks.append(chunk.content)
    assert chunks


@pytest.mark.asyncio
async def test_pricing_for_deepseek_chat(provider):
    """deepseek-chat 价格应符合官方公开价目."""
    in_p, out_p = provider.PRICING["deepseek-chat"]
    # 2026-07 价位: cache miss ≈ $0.14 / $0.28 (USD per 1M)
    assert 0.10 < in_p < 0.20
    assert 0.20 < out_p < 0.40