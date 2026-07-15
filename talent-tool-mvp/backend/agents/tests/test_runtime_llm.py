"""LLMClient 单测 — 验证走 Provider 抽象层后行为一致.

覆盖目标:
    - __init__ 默认从 env LLM_PROVIDER 读 (默认 mock)
    - __init__ 接受 provider 参数(字符串名 / LLMProvider 实例 / openai_client 兼容)
    - LLMClient.from_env() 类方法
    - .call() 仍返回 (text, in_tok, out_tok) 三元素
    - .chat() 返回 LLMResponse dataclass
    - .stream_chat() 走 provider.stream_chat()
    - 切换 provider 后行为一致(同一 messages 在 mock 和 fake openai 上得到相同结构)
    - 老的 _mock_response 路由逻辑被 MockLLMProvider 复用 (情感/职业/画像 等关键词路由)
    - cost/retry 委托给 provider.with_resilience 中间件(provider 是 mock 时退化为直调)
"""
from __future__ import annotations

import asyncio
import os
import pytest
from types import SimpleNamespace
from typing import Any


# ---------------------------------------------------------------------------
# 默认 provider / env 解析
# ---------------------------------------------------------------------------
def test_default_provider_is_mock(monkeypatch):
    """不传 provider,不设 LLM_PROVIDER env → 默认 mock."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    from agents.runtime import LLMClient
    from providers.llm.mock_provider import MockLLMProvider

    llm = LLMClient()
    assert isinstance(llm.provider, MockLLMProvider)
    assert llm.provider.provider_name == "mock"


def test_env_provider_resolved(monkeypatch):
    """LLM_PROVIDER=mock → 用 MockLLMProvider."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient
    from providers.llm.mock_provider import MockLLMProvider

    llm = LLMClient()
    assert isinstance(llm.provider, MockLLMProvider)


def test_from_env_classmethod(monkeypatch):
    """LLMClient.from_env() 自动从 env 构造."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient
    from providers.llm.mock_provider import MockLLMProvider

    llm = LLMClient.from_env()
    assert isinstance(llm.provider, MockLLMProvider)


# ---------------------------------------------------------------------------
# provider 参数 — 字符串 / 实例 / openai_client 兼容
# ---------------------------------------------------------------------------
def test_provider_kw_string():
    from agents.runtime import LLMClient
    from providers.llm.mock_provider import MockLLMProvider

    llm = LLMClient(provider="mock")
    assert isinstance(llm.provider, MockLLMProvider)


def test_provider_kw_instance():
    from agents.runtime import LLMClient
    from providers.llm.mock_provider import MockLLMProvider

    p = MockLLMProvider()
    llm = LLMClient(provider=p)
    assert llm.provider is p


def test_provider_kw_openai_client_legacy_compat(monkeypatch):
    """老的 LLMClient(openai_client=async_openai_instance) 写法仍能工作."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-legacy")
    from agents.runtime import LLMClient
    from providers.llm.openai_provider import OpenAIProvider

    # 假装一个 AsyncOpenAI
    class FakeAsyncOpenAI:
        api_key = "sk-test-legacy"

        class chat:
            class completions:
                async def create(*args, **kwargs):
                    pass

    llm = LLMClient(openai_client=FakeAsyncOpenAI(), model="gpt-4o")
    assert isinstance(llm.provider, OpenAIProvider)
    assert llm.provider.provider_name == "openai"
    assert llm.model == "gpt-4o"


def test_unknown_provider_string_falls_back_to_local():
    """v11.0: 未知 provider 字符串 → 兜底到本地默认 provider (不再崩溃).

    旧版默认回落 MockLLMProvider;v11.0 起 registry 默认 ollama (本地优先),
    因此未知 provider 字符串解析为 OllamaProvider (本地) 而非 MockLLMProvider。
    关键保证:不抛异常,Agent 拿到一个可用 provider。
    """
    from agents.runtime import LLMClient
    from providers.llm.base import LLMProvider

    llm = LLMClient(provider="nonexistent-provider-xyz")
    # 不崩溃 + 是合法 LLMProvider (v11.0 默认 ollama)
    assert isinstance(llm.provider, LLMProvider)


# ---------------------------------------------------------------------------
# call() 行为 — 向后兼容 (text, in_tok, out_tok) 三元素
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_returns_tuple(monkeypatch):
    """call() 仍返回 (text, input_tokens, output_tokens) — 老业务代码不破."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient

    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "你是情感分析专家"},
        {"role": "user", "content": "今天拿到 offer,太开心了!"},
    ]
    result = await llm.call(msgs)
    assert isinstance(result, tuple)
    assert len(result) == 3
    text, in_tok, out_tok = result
    assert isinstance(text, str) and len(text) > 0
    assert isinstance(in_tok, int)
    assert isinstance(out_tok, int)


@pytest.mark.asyncio
async def test_call_mock_emotion_routing(monkeypatch):
    """_mock_response 的情感路由被 MockLLMProvider 复用."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient
    import json

    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "你是情感分析专家"},
        {"role": "user", "content": "我已经崩溃了,什么都没意思了"},
    ]
    text, _, _ = await llm.call(msgs)
    parsed = json.loads(text)
    assert parsed["risk_level"] == "severe"
    assert parsed["primary_emotion"] == "hopelessness"


@pytest.mark.asyncio
async def test_call_mock_career_routing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient
    import json

    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "你是职业规划顾问,根据用户输入生成职业规划"},
        {"role": "user", "content": "我是 Python 后端,想转 AI 方向"},
    ]
    text, _, _ = await llm.call(msgs)
    parsed = json.loads(text)
    assert "short_term" in parsed
    assert "skill_gaps" in parsed


@pytest.mark.asyncio
async def test_call_mock_profile_routing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient
    import json

    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "你是 profile_agent,采集用户画像"},
        {"role": "user", "content": "我有 5 年 Python 经验"},
    ]
    text, _, _ = await llm.call(msgs)
    parsed = json.loads(text)
    assert "updated_profile" in parsed
    assert "next_questions" in parsed


# ---------------------------------------------------------------------------
# chat() — 新 API: 返回 LLMResponse dataclass
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_returns_agent_llm_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient, LLMResponse

    llm = LLMClient()
    msgs = [
        {"role": "system", "content": "你是情感分析专家"},
        {"role": "user", "content": "今天好累"},
    ]
    resp = await llm.chat(msgs)
    assert isinstance(resp, LLMResponse)
    assert resp.text
    assert resp.model
    assert resp.input_tokens >= 0
    assert resp.output_tokens >= 0
    assert resp.finish_reason == "stop"


@pytest.mark.asyncio
async def test_chat_message_dict_to_provider_conversion(monkeypatch):
    """chat() 把 dict messages 转成 provider 的 Message dataclass."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient

    # 把 MockLLMProvider 替换成 spy,检查收到的是 Message 列表
    from providers.llm.base import Message

    captured: dict = {}

    class SpyProvider:
        provider_name = "spy"
        default_model = "spy-model"

        @property
        def supported_models(self):
            return ["spy-model"]

        @property
        def pricing(self):
            return {"spy-model": (0.0, 0.0)}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, **kwargs):
            captured["messages"] = messages
            from providers.llm.base import LLMResponse, Usage

            return LLMResponse(
                content="ok",
                model=model or "spy-model",
                usage=Usage(prompt_tokens=10, completion_tokens=5),
            )

        async def stream_chat(self, messages, *, model=None, **kwargs):
            yield "ok"

    llm = LLMClient(provider=SpyProvider())
    msgs = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    resp = await llm.chat(msgs)
    assert all(isinstance(m, Message) for m in captured["messages"])
    assert captured["messages"][0].role == "system"
    assert captured["messages"][1].role == "user"


# ---------------------------------------------------------------------------
# stream_chat() — 走 provider.stream_chat()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stream_chat_yields_text(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from agents.runtime import LLMClient

    llm = LLMClient()
    msgs = [{"role": "user", "content": "hello"}]
    parts = []
    async for chunk in llm.stream_chat(msgs):
        parts.append(chunk)
    assert "".join(parts)  # mock stream 应该产出文本


@pytest.mark.asyncio
async def test_stream_chat_uses_provider(monkeypatch):
    """stream_chat() 必须委托给 self.provider.stream_chat()."""
    from agents.runtime import LLMClient

    called = {"stream": False}

    class StubProvider:
        provider_name = "stub"
        default_model = "stub-model"

        @property
        def supported_models(self):
            return ["stub-model"]

        @property
        def pricing(self):
            return {}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, **kwargs):
            from providers.llm.base import LLMResponse, Usage

            return LLMResponse(content="x", model="stub-model", usage=Usage())

        async def stream_chat(self, messages, *, model=None, **kwargs):
            called["stream"] = True
            for ch in "abc":
                yield ch

    llm = LLMClient(provider=StubProvider())
    parts = []
    async for ch in llm.stream_chat([{"role": "user", "content": "x"}]):
        parts.append(ch)
    assert called["stream"] is True
    assert "".join(parts) == "abc"


# ---------------------------------------------------------------------------
# 切换 provider 行为一致 — 同一 messages,不同 provider,拿到结构相似响应
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_switching_provider_yields_consistent_shape(monkeypatch):
    """把 provider 从 mock 切到 fake-openai,响应字段一致 (text+usage)."""
    from agents.runtime import LLMClient, LLMResponse
    from providers.llm.base import LLMResponse as ProviderResp, Usage

    class FakeOpenAIProvider:
        provider_name = "openai"
        default_model = "gpt-4o-mini"
        client = None

        @property
        def supported_models(self):
            return ["gpt-4o-mini"]

        @property
        def pricing(self):
            return {"gpt-4o-mini": (0.15, 0.6)}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, temperature=0.7, max_tokens=1024, **kwargs):
            return ProviderResp(
                content="hello from fake openai",
                model=model or self.default_model,
                finish_reason="stop",
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        async def stream_chat(self, messages, *, model=None, **kwargs):
            for ch in "hello from fake openai":
                yield ch

    msgs = [{"role": "user", "content": "hi"}]

    # Mock provider
    llm_mock = LLMClient(provider="mock")
    r_mock = await llm_mock.chat(msgs)

    # Fake OpenAI provider
    llm_oai = LLMClient(provider=FakeOpenAIProvider())
    r_oai = await llm_oai.chat(msgs)

    # 字段一致性
    assert isinstance(r_mock, LLMResponse)
    assert isinstance(r_oai, LLMResponse)
    for r in (r_mock, r_oai):
        assert r.text
        assert r.model
        assert r.input_tokens >= 0
        assert r.output_tokens >= 0
        assert r.finish_reason == "stop"

    assert r_oai.text == "hello from fake openai"
    assert r_oai.model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# cost / retry 委托给 provider 中间件
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cost_estimation_uses_provider_pricing(monkeypatch):
    """cost_usd() 应该走 provider.calculate_cost(),而不是 self.price."""
    from agents.runtime import LLMClient

    class PricedProvider:
        provider_name = "priced"
        default_model = "priced-model"

        @property
        def supported_models(self):
            return ["priced-model"]

        @property
        def pricing(self):
            return {"priced-model": (1.0, 2.0)}  # 1 USD/M input, 2 USD/M output

        def calculate_cost(self, model, usage):
            price = self.pricing.get(model, (0.0, 0.0))
            return (usage.prompt_tokens * price[0] + usage.completion_tokens * price[1]) / 1_000_000

        async def chat(self, messages, *, model=None, **kwargs):
            from providers.llm.base import LLMResponse, Usage

            return LLMResponse(content="x", model="priced-model", usage=Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000))

        async def stream_chat(self, messages, *, model=None, **kwargs):
            yield "x"

    llm = LLMClient(provider=PricedProvider())
    cost = llm.cost_usd("priced-model", 1_000_000, 1_000_000)
    assert cost == pytest.approx(3.0)  # 1 + 2


def test_estimate_cost_cents_legacy_field():
    """老代码还会读 self.estimate_cost_cents() — 必须保留."""
    from agents.runtime import LLMClient

    llm = LLMClient()
    assert llm.estimate_cost_cents(1000, 500) == int((1500 / 1000) * 0.5)


@pytest.mark.asyncio
async def test_retry_policy_owned_by_provider(monkeypatch):
    """重试策略由 provider 装饰器控制,LLMClient 自己不再做 retry loop.

    验证方法: 构造一个记录调用次数的 provider,正常调用只触发 1 次 chat().
    """
    from agents.runtime import LLMClient
    from providers.llm.base import LLMResponse, Usage

    call_count = {"n": 0}

    class CountingProvider:
        provider_name = "counter"
        default_model = "c-model"

        @property
        def supported_models(self):
            return ["c-model"]

        @property
        def pricing(self):
            return {}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, **kwargs):
            call_count["n"] += 1
            return LLMResponse(content="x", model="c-model", usage=Usage())

        async def stream_chat(self, messages, *, model=None, **kwargs):
            yield "x"

    llm = LLMClient(provider=CountingProvider())
    # call() 内部只调 1 次 self.provider.chat()
    await llm.call([{"role": "user", "content": "x"}])
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# 工具 / cost warning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cost_exceeds_budget_logs_warning(monkeypatch, caplog):
    """cost 超过 max_cost_cents 时,只 warning 不 raise."""
    from agents.runtime import LLMClient
    from providers.llm.base import LLMResponse, Usage

    class BigUsageProvider:
        provider_name = "big"
        default_model = "big-model"

        @property
        def supported_models(self):
            return ["big-model"]

        @property
        def pricing(self):
            return {}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, **kwargs):
            # 100 万 input + 100 万 output tokens
            return LLMResponse(
                content="x", model="big-model",
                usage=Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000),
            )

        async def stream_chat(self, messages, *, model=None, **kwargs):
            yield "x"

    llm = LLMClient(provider=BigUsageProvider(), price_per_1k_cents=0.5)
    msgs = [{"role": "user", "content": "x"}]
    with caplog.at_level("WARNING"):
        text, in_tok, out_tok = await llm.call(msgs, max_cost_cents=10)
    assert text == "x"
    # self.estimate_cost_cents(1_000_000, 1_000_000) = int(2000 * 0.5) = 1000, 远超 max_cost_cents=10
    assert any("exceeds budget" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# 兜底: provider 抛错,mock 走 _mock_response
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_error_falls_back_to_mock(monkeypatch):
    """mock provider 内部出错时,call() 兜底走 self._mock_response."""
    from agents.runtime import LLMClient

    class BrokenProvider:
        provider_name = "broken"
        default_model = "x"

        @property
        def supported_models(self):
            return ["x"]

        @property
        def pricing(self):
            return {}

        def calculate_cost(self, model, usage):
            return 0.0

        async def chat(self, messages, *, model=None, **kwargs):
            raise RuntimeError("provider down")

        async def stream_chat(self, messages, *, model=None, **kwargs):
            if False:
                yield ""

    # 走 mock 路径(只有 mock 才有 _mock_response 兜底)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    llm = LLMClient()
    # 强制 provider 抛错
    async def broken_chat(*args, **kwargs):
        raise RuntimeError("simulated")
    llm.provider.chat = broken_chat  # type: ignore[assignment]

    msgs = [{"role": "user", "content": "今天好累"}]
    text, in_tok, out_tok = await llm.call(msgs)
    # 兜底走 _mock_response → 默认返回 _mock_general_response
    assert "好累" in text or "我理解" in text
    assert in_tok == 100 and out_tok == 50  # mock 兜底固定 token 数