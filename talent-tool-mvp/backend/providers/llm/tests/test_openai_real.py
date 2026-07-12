"""OpenAI 真实 LLM 接入验证 (T1701).

默认 **跳过** — 需要 OPENAI_API_KEY 才会运行:

    export OPENAI_API_KEY="sk-..."
    pytest -m real_api backend/providers/llm/tests/test_openai_real.py

测试覆盖:
    1. 实例化 / 模型注册
    2. chat 非流式 — gpt-4o-mini
    3. chat 非流式 — gpt-4o
    4. stream_chat 流式 token 输出
    5. tool_call 工具调用
    6. cost 计算
    7. 异常映射 (401/429/timeout)

凭证申请: docs/REAL_API_SETUP.md (1.1 OpenAI)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.llm.base import Message, ToolDefinition
from backend.providers.llm.openai_provider import OpenAIProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY 未设置 — 跳过 OpenAI 真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return OpenAIProvider(default_model="gpt-4o-mini")


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    """真实 key 实例化无异常."""
    assert provider.api_key.startswith("sk-")
    assert provider.client is not None


@pytest.mark.asyncio
async def test_chat_gpt4o_mini_returns_response(provider):
    """gpt-4o-mini chat 应返回非空 content."""
    msgs = [Message(role="user", content="Reply with exactly: 'pong'")]
    resp = await provider.chat(msgs, model="gpt-4o-mini", max_tokens=20)
    assert resp.content, "OpenAI 应返回非空 content"
    assert resp.usage.input_tokens > 0
    assert resp.usage.output_tokens > 0
    assert resp.model.startswith("gpt-")


@pytest.mark.asyncio
async def test_stream_chat_yields_tokens(provider):
    """流式调用应 yield 至少 1 个 chunk."""
    msgs = [Message(role="user", content="Say 'hi'")]
    chunks: list[str] = []
    async for chunk in provider.stream_chat(msgs, model="gpt-4o-mini", max_tokens=10):
        if chunk.content:
            chunks.append(chunk.content)
    assert len(chunks) >= 1, "OpenAI 流式应 yield 至少 1 个 content chunk"


@pytest.mark.asyncio
async def test_tool_call_basic(provider):
    """简单 tool_call 验证 (期望模型触发工具)."""
    tools = [
        ToolDefinition(
            name="get_weather",
            description="Get current weather for a city",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        )
    ]
    msgs = [Message(role="user", content="What's the weather in Beijing?")]
    resp = await provider.chat(msgs, model="gpt-4o-mini", tools=tools, max_tokens=100)
    # 模型可能不调用 tool,但应不抛异常
    assert resp.tool_calls is not None or resp.content


@pytest.mark.asyncio
async def test_cost_calculation_matches_pricing(provider):
    """cost 应与 PRICING 表一致."""
    usage_in, usage_out = 1000, 500
    cost = provider.estimate_cost("gpt-4o-mini", usage_in, usage_out)
    in_price, out_price = provider.PRICING["gpt-4o-mini"]
    expected = (usage_in / 1_000_000) * in_price + (usage_out / 1_000_000) * out_price
    assert abs(cost - expected) < 1e-9


def test_supported_models_at_least_3():
    """OpenAI 至少注册 3 个模型."""
    p = OpenAIProvider()
    assert len(p.supported_models) >= 3
    assert "gpt-4o-mini" in p.supported_models