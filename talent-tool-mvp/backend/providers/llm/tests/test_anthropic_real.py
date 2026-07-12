"""Anthropic Claude 真实 LLM 接入验证 (T1701).

默认 **跳过** — 需要 ANTHROPIC_API_KEY:

    export ANTHROPIC_API_KEY="sk-ant-..."
    pytest -m real_api backend/providers/llm/tests/test_anthropic_real.py

凭证申请: docs/REAL_API_SETUP.md (1.2 Anthropic)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.llm.anthropic_provider import AnthropicProvider
from backend.providers.llm.base import Message, ToolDefinition


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY 未设置 — 跳过 Anthropic 真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return AnthropicProvider(default_model="claude-3-5-haiku-latest")


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    assert provider.api_key.startswith("sk-ant-")
    assert provider.client is not None


@pytest.mark.asyncio
async def test_chat_haiku_returns_response(provider):
    """claude-3-5-haiku 真实 chat."""
    msgs = [Message(role="user", content="Reply with exactly one word: 'pong'")]
    resp = await provider.chat(msgs, model="claude-3-5-haiku-latest", max_tokens=20)
    assert resp.content
    assert resp.usage.input_tokens > 0


@pytest.mark.asyncio
async def test_stream_chat_yields_chunks(provider):
    msgs = [Message(role="user", content="Count: 1 2 3")]
    chunks: list[str] = []
    async for chunk in provider.stream_chat(msgs, model="claude-3-5-haiku-latest", max_tokens=30):
        if chunk.content:
            chunks.append(chunk.content)
    assert chunks


@pytest.mark.asyncio
async def test_tool_call_basic(provider):
    tools = [
        ToolDefinition(
            name="sum",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
        )
    ]
    msgs = [Message(role="user", content="What is 2+3? Use the sum tool.")]
    resp = await provider.chat(msgs, model="claude-3-5-haiku-latest", tools=tools, max_tokens=200)
    # 期望调用工具 (或不调用但正常返回 content)
    assert resp.tool_calls is not None or resp.content


def test_pricing_registered():
    p = AnthropicProvider()
    assert "claude-3-5-haiku-latest" in p.PRICING
    in_price, out_price = p.PRICING["claude-3-5-haiku-latest"]
    assert in_price > 0 and out_price > 0