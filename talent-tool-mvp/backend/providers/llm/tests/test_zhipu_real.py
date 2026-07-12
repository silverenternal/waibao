"""智谱 GLM 真实 LLM 接入验证 (T1701).

默认 **跳过** — 需要 ZHIPU_API_KEY:

    export ZHIPU_API_KEY="..."
    pytest -m real_api backend/providers/llm/tests/test_zhipu_real.py

凭证申请: docs/REAL_API_SETUP.md (1.4 智谱 GLM)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.llm.base import Message
from backend.providers.llm.zhipu_provider import ZhipuProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("ZHIPU_API_KEY"),
        reason="ZHIPU_API_KEY 未设置 — 跳过智谱真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return ZhipuProvider(default_model="glm-4-flash")


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    assert provider.api_key


@pytest.mark.asyncio
async def test_chat_glm4_flash(provider):
    """GLM-4-Flash 真实 chat (新人免费)."""
    msgs = [Message(role="user", content="用一句话自我介绍")]
    resp = await provider.chat(msgs, model="glm-4-flash", max_tokens=100)
    assert resp.content


@pytest.mark.asyncio
async def test_stream_chat_yields_chunks(provider):
    msgs = [Message(role="user", content="数 1 到 5")]
    chunks: list[str] = []
    async for chunk in provider.stream_chat(msgs, model="glm-4-flash", max_tokens=50):
        if chunk.content:
            chunks.append(chunk.content)
    assert chunks


def test_pricing_glm4_flash_cheap():
    """GLM-4-Flash 应是低价格档."""
    p = ZhipuProvider()
    in_p, _ = p.PRICING["glm-4-flash"]
    assert in_p <= 0.2, "GLM-4-Flash 应 < $0.2/M tokens"