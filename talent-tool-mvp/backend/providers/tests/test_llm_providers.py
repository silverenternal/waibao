"""6 家真实 LLM Provider 单测.

验证目标:
    - 每个 provider 都能实例化,且 API key 缺失时抛 InvalidRequestError
    - supported_models 与 pricing 一致,每家 ≥3 个模型
    - chat / stream_chat / tool_call 三个方法协议完整
    - 异常映射到 ProviderError 体系 (Auth / RateLimit / InvalidRequest / Timeout / UpstreamUnavailable)
    - @with_resilience 用各自的 provider_name 做 key (熔断/限流/metrics 隔离)
    - cost 计算与 pricing 表一致
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from backend.providers.exceptions import (
    AuthError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TimeoutError,
    UpstreamUnavailableError,
)
from backend.providers.llm.base import Message, ToolCall, ToolDefinition, Usage
from backend.providers.llm.openai_provider import (
    OpenAIProvider,
    map_openai_exception,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """每个 case 都注入 fake api key,保证可以正常实例化真实 provider."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu")
    monkeypatch.setenv("TONGYI_API_KEY", "sk-test-tongyi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test-moonshot")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")


# ---------------------------------------------------------------------------
# Provider 元数据
# ---------------------------------------------------------------------------
PROVIDERS: list[tuple[str, type, str]] = [
    ("openai", OpenAIProvider, "https://api.openai.com"),
    ("deepseek", __import__("backend.providers.llm.deepseek_provider", fromlist=["DeepSeekProvider"]).DeepSeekProvider, "https://api.deepseek.com"),
    ("zhipu", __import__("backend.providers.llm.zhipu_provider", fromlist=["ZhipuProvider"]).ZhipuProvider, "https://open.bigmodel.cn/api/paas/v4"),
    ("tongyi", __import__("backend.providers.llm.tongyi_provider", fromlist=["TongyiProvider"]).TongyiProvider, "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("moonshot", __import__("backend.providers.llm.moonshot_provider", fromlist=["MoonshotProvider"]).MoonshotProvider, "https://api.moonshot.cn/v1"),
]


@pytest.mark.parametrize("name,cls,base_url", PROVIDERS)
def test_provider_metadata(name, cls, base_url):
    """每家: provider_name + base_url + ≥3 模型 + pricing 一致."""
    p = cls()
    assert p.provider_name == name
    if name == "openai":
        # base_url=None 表示走 SDK 默认 (OpenAI 官方)
        assert p.base_url in (None, "https://api.openai.com/v1")
    else:
        assert p.base_url == base_url
    assert len(p.supported_models) >= 3, f"{name} only has {len(p.supported_models)} models"
    assert set(p.supported_models) == set(p.pricing.keys()), (
        f"{name} supported_models and pricing out of sync"
    )
    for model, (in_p, out_p) in p.pricing.items():
        assert in_p >= 0 and out_p >= 0, f"{name}.{model} has negative price"


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
def test_provider_missing_api_key_raises(name, cls, _, monkeypatch):
    """每家: API key 缺失抛 InvalidRequestError."""
    monkeypatch.delenv(cls.ENV_KEY, raising=False)
    with pytest.raises(InvalidRequestError):
        cls()


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
def test_provider_cost_calculation(name, cls, _):
    """cost = (prompt * in + completion * out) / 1e6."""
    p = cls()
    model = p.default_model
    usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000)
    in_p, out_p = p.pricing[model]
    expected = in_p + out_p
    assert p.calculate_cost(model, usage) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# chat / stream_chat / tool_call — Mock SDK 客户端
# ---------------------------------------------------------------------------
def _fake_openai_response(content: str = "hi", model: str = "gpt-4o-mini", tool_calls=None):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls or [],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _fake_stream_chunks():
    return [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hello "))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="world"))]),
        SimpleNamespace(choices=[]),
    ]


class FakeCompletions:
    def __init__(self, *, content: str = "hi", chunks=None, exc: Exception | None = None, tool_calls=None):
        self._content = content
        self._chunks = chunks or []
        self._exc = exc
        self._tool_calls = tool_calls or []
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        if kwargs.get("stream"):
            return self._async_iter(self._chunks)
        return _fake_openai_response(
            content=self._content,
            model=kwargs["model"],
            tool_calls=self._tool_calls,
        )

    @staticmethod
    async def _async_iter(items):
        for x in items:
            yield x


class FakeChatNamespace:
    """Mimics AsyncOpenAI's client.chat.completions."""

    def __init__(self, *, content="hi", chunks=None, exc: Exception | None = None, tool_calls=None):
        self.completions = FakeCompletions(
            content=content, chunks=chunks, exc=exc, tool_calls=tool_calls
        )


class FakeAsyncOpenAI:
    """Injectable AsyncOpenAI replacement."""

    def __init__(self, *, content="hi", chunks=None, exc: Exception | None = None, tool_calls=None):
        self.chat = FakeChatNamespace(
            content=content, chunks=chunks, exc=exc, tool_calls=tool_calls
        )

    @property
    def calls(self):
        return self.chat.completions.calls


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_chat_returns_llm_response(name, cls, _, monkeypatch):
    """chat 调用 SDK,返回 LLMResponse, content/usage 正确填充."""
    fake = FakeAsyncOpenAI(content="hello from " + name)
    p = cls()
    p.client = fake  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    resp = await p.chat(msgs, model=p.default_model, max_tokens=64)
    assert resp.content == "hello from " + name
    assert resp.usage.total_tokens == 15


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_stream_chat_yields_text(name, cls, _):
    p = cls()
    p.client = FakeAsyncOpenAI(chunks=_fake_stream_chunks())  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    parts: list[str] = []
    async for ch in p.stream_chat(msgs, model=p.default_model, max_tokens=64):
        parts.append(ch)
    assert "".join(parts) == "hello world"


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_tool_call_invokes_chat_with_tools(name, cls, _):
    tool = ToolDefinition(
        name="get_weather",
        description="get weather",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
    )
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="get_weather", arguments='{"city":"London"}'),
    )
    p = cls()
    p.client = FakeAsyncOpenAI(content="", tool_calls=[tc])  # type: ignore[assignment]
    msgs = [Message(role="user", content="weather?")]
    result = await p.tool_call(msgs, [tool], model=p.default_model)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_weather"
    assert result.tool_calls[0].arguments == {"city": "London"}


# ---------------------------------------------------------------------------
# 异常映射
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_exception_mapping_to_provider_error(name, cls, _):
    """SDK 抛错 -> ProviderError 子类."""
    p = cls()
    exc = Exception("401 Authentication failed: bad api_key")
    p.client = FakeAsyncOpenAI(exc=exc)  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    with pytest.raises(AuthError) as ei:
        await p.chat(msgs, model=p.default_model)
    assert ei.value.provider == name
    assert ei.value.retryable is False


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_rate_limit_maps_and_is_retryable(name, cls, _):
    p = cls()
    exc = Exception("429 Rate limit reached")
    p.client = FakeAsyncOpenAI(exc=exc)  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    with pytest.raises(RateLimitError) as ei:
        await p.chat(msgs, model=p.default_model)
    assert ei.value.retryable is True
    assert ei.value.status_code == 429


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_invalid_request_not_retryable(name, cls, _):
    p = cls()
    exc = Exception("400 BadRequest invalid param")
    p.client = FakeAsyncOpenAI(exc=exc)  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    with pytest.raises(InvalidRequestError) as ei:
        await p.chat(msgs, model=p.default_model)
    assert ei.value.retryable is False


@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_upstream_5xx_maps_and_is_retryable(name, cls, _):
    p = cls()
    exc = Exception("500 Internal Server Error")
    p.client = FakeAsyncOpenAI(exc=exc)  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    with pytest.raises(UpstreamUnavailableError) as ei:
        await p.chat(msgs, model=p.default_model)
    assert ei.value.retryable is True


# ---------------------------------------------------------------------------
# 独立测试:map_openai_exception 覆盖度
# ---------------------------------------------------------------------------
def test_map_openai_exception_timeout():
    assert isinstance(map_openai_exception(Exception("ReadTimeout"), provider="openai"), TimeoutError)


def test_map_openai_exception_quota():
    from backend.providers.exceptions import QuotaExceededError
    assert isinstance(map_openai_exception(Exception("insufficient_quota"), provider="openai"), QuotaExceededError)


def test_map_openai_exception_default_fallback():
    e = map_openai_exception(Exception("something weird"), provider="openai")
    assert isinstance(e, UpstreamUnavailableError)
    assert e.provider == "openai"


# ---------------------------------------------------------------------------
# 装饰器 key 隔离
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,cls,_", PROVIDERS)
def test_resilience_decorator_uses_own_provider_name(name, cls, _):
    """@with_resilience(provider=...) 必须用各自 provider_name,否则 5 家共用一个熔断器."""
    import inspect

    src = inspect.getsource(cls)
    assert f'@with_resilience(provider="{name}", method="chat"' in src, (
        f"{cls.__name__}.chat missing @with_resilience(provider={name}, method=chat)"
    )
    # stream_chat 不再装饰 (async generator 与 with_resilience 不兼容)


# ---------------------------------------------------------------------------
# model 参数切换
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,cls,_", PROVIDERS)
@pytest.mark.asyncio
async def test_model_parameter_switching(name, cls, _):
    """显式传 model 参数,SDK 收到对应的 model 字符串."""
    fake = FakeAsyncOpenAI(content="ok")
    p = cls()
    p.client = fake  # type: ignore[assignment]
    msgs = [Message(role="user", content="hi")]
    models_to_test = list(p.pricing.keys())[:3]
    for m in models_to_test:
        await p.chat(msgs, model=m)
    received = [c["model"] for c in fake.calls]
    assert received == models_to_test