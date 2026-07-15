"""OllamaProvider 单元测试 (v11.0 / T6101).

完全 mock Ollama 的 OpenAI 兼容接口,验证:
  - chat / stream_chat / tool_call 行为正确
  - 异常映射走 map_openai_exception
  - base_url 规范化 (自动补 /v1)
  - registry: LLM_PROVIDER=ollama 时返回 OllamaProvider

不需要真实 Ollama 服务 —— 所有 HTTP 通过 ``AsyncOpenAI`` 的 mock 完成。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.providers.llm.base import Message, ToolDefinition
from backend.providers.llm.ollama_provider import (
    OllamaProvider,
    _normalize_base_url,
)


# ---------------------------------------------------------------------------
# helpers —— 构造假 OpenAI 响应对象
# ---------------------------------------------------------------------------
def _fake_chat_response(
    *,
    content: str = "你好,我是本地 Ollama。",
    tool_calls: list[dict[str, Any]] | None = None,
    model: str = "qwen2.5:7b-instruct",
    finish_reason: str = "stop",
) -> Any:
    tc_objs = []
    for tc in tool_calls or []:
        tc_objs.append(
            SimpleNamespace(
                id=tc["id"],
                function=SimpleNamespace(
                    name=tc["name"],
                    arguments=tc.get("arguments", "{}"),
                ),
            )
        )
    message = SimpleNamespace(content=content, tool_calls=tc_objs)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=8, total_tokens=18)
    return SimpleNamespace(
        choices=[choice], usage=usage, model=model
    )


def _fake_stream_chunks(tokens: list[str]) -> list[Any]:
    chunks = []
    for tok in tokens:
        delta = SimpleNamespace(content=tok)
        chunks.append(SimpleNamespace(choices=[SimpleNamespace(delta=delta)]))
    # 末尾一个空 choices (模拟 keepalive),不应产出
    chunks.append(SimpleNamespace(choices=[]))
    return chunks


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> OllamaProvider:
    # 固定 base_url 避免读到宿主环境变量
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    return OllamaProvider(base_url="http://ollama:11434")


# ---------------------------------------------------------------------------
# 构造 / 配置
# ---------------------------------------------------------------------------
def test_normalize_base_url_variants():
    assert _normalize_base_url("http://ollama:11434") == "http://ollama:11434/v1"
    assert _normalize_base_url("http://ollama:11434/") == "http://ollama:11434/v1"
    assert _normalize_base_url("http://ollama:11434/v1") == "http://ollama:11434/v1"
    assert _normalize_base_url("http://localhost:11434/v1/") == "http://localhost:11434/v1"


def test_provider_uses_env_base_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://my-ollama:11434")
    p = OllamaProvider()
    assert p.base_url == "http://my-ollama:11434/v1"


def test_provider_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    p = OllamaProvider()
    assert p.base_url == "http://ollama:11434/v1"
    assert p.default_model == "qwen2.5:7b-instruct"
    assert p.provider_name == "ollama"
    # 不需要真实 key,但字段非空
    assert p.api_key


def test_provider_supported_models_and_pricing(provider: OllamaProvider):
    assert "qwen2.5:7b-instruct" in provider.supported_models
    assert "glm4:9b" in provider.supported_models
    assert "llama3.1:8b" in provider.supported_models
    # 本地自托管 -> 0 成本
    for m in provider.supported_models:
        assert provider.pricing[m] == (0.0, 0.0)


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_returns_parsed_response(provider: OllamaProvider):
    fake = _fake_chat_response(content="本地回复")
    with patch.object(
        provider.client.chat.completions, "create", new=AsyncMock(return_value=fake)
    ) as m:
        resp = await provider.chat([Message(role="user", content="hi")])
    assert resp.content == "本地回复"
    assert resp.model == "qwen2.5:7b-instruct"
    assert resp.usage.total_tokens == 18
    assert resp.finish_reason == "stop"
    # 验证请求里带了 model 与 messages
    call_kwargs = m.call_args.kwargs
    assert call_kwargs["model"] == "qwen2.5:7b-instruct"
    assert call_kwargs["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_chat_serializes_tools_and_passes_tool_choice(provider: OllamaProvider):
    fake = _fake_chat_response()
    tools = [
        ToolDefinition(
            name="search_jobs",
            description="搜索职位",
            parameters={"type": "object", "properties": {}},
        )
    ]
    with patch.object(
        provider.client.chat.completions, "create", new=AsyncMock(return_value=fake)
    ) as m:
        await provider.chat([Message(role="user", content="找职位")], tools=tools)
    sent_tools = m.call_args.kwargs["tools"]
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["name"] == "search_jobs"


@pytest.mark.asyncio
async def test_chat_maps_exception_to_provider_error(provider: OllamaProvider):
    from backend.providers.exceptions import ProviderError

    def boom(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("Connection refused: ollama down")

    with patch.object(provider.client.chat.completions, "create", new=boom):
        with pytest.raises(ProviderError):
            await provider.chat([Message(role="user", content="hi")])


# ---------------------------------------------------------------------------
# stream_chat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stream_chat_yields_tokens(provider: OllamaProvider):
    chunks = _fake_stream_chunks(["本", "地", "Ollama"])

    class _Stream:
        def __init__(self, _chunks: list[Any]) -> None:
            self._it = iter(_chunks)

        def __aiter__(self) -> "_Stream":
            return self

        async def __anext__(self) -> Any:
            try:
                return next(self._it)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    with patch.object(
        provider.client.chat.completions, "create", new=AsyncMock(return_value=_Stream(chunks))
    ) as m:
        tokens = [t async for t in provider.stream_chat([Message(role="user", content="hi")])]

    assert "".join(tokens) == "本地Ollama"
    assert m.call_args.kwargs["stream"] is True


# ---------------------------------------------------------------------------
# tool_call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_call_returns_tool_calls(provider: OllamaProvider):
    fake = _fake_chat_response(
        content="",
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "call_1",
                "name": "search_jobs",
                "arguments": json.dumps({"q": "python"}),
            }
        ],
    )
    tools = [
        ToolDefinition(
            name="search_jobs",
            description="搜索职位",
            parameters={"type": "object"},
        )
    ]
    with patch.object(
        provider.client.chat.completions, "create", new=AsyncMock(return_value=fake)
    ) as m:
        result = await provider.tool_call(
            [Message(role="user", content="找 python 职位")], tools
        )
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search_jobs"
    assert result.tool_calls[0].arguments == {"q": "python"}
    # tool_call 内部走 chat 并强制 tool_choice=auto
    assert m.call_args.kwargs.get("tool_choice") == "auto"


# ---------------------------------------------------------------------------
# registry 接入
# ---------------------------------------------------------------------------
def test_registry_returns_ollama_when_provider_ollama(monkeypatch: pytest.MonkeyPatch):
    from backend.providers import registry
    from backend.providers.llm.ollama_provider import OllamaProvider

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WAIBAO_PROVIDER_MOCK", "1")
    registry.reset_cache()
    try:
        provider = registry.get_llm_provider()
        assert isinstance(provider, OllamaProvider)
    finally:
        registry.reset_cache()


def test_registry_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch):
    """v11.0: 未配置 LLM_PROVIDER 时默认回落到 ollama (本地优先)."""
    from backend.providers import registry
    from backend.providers.llm.ollama_provider import OllamaProvider

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    registry.reset_cache()
    try:
        provider = registry.get_llm_provider()
        assert isinstance(provider, OllamaProvider)
    finally:
        registry.reset_cache()
