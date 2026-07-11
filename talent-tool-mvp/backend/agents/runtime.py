"""Agent Runtime — 统一智能体运行底座.

所有智能体必须继承 BaseAgent,以保证:
- 统一的输入/输出协议 (AgentInput/AgentOutput)
- Tool 注册与调用
- Memory 读写 (短期/工作/长期)
- Cost 控制 / Retry / Backoff
- Tracing (OpenTelemetry)

LLMClient 通过 backend.providers 抽象层调用 LLM:
    - chat()       内部委托给 self.provider.chat()
    - stream_chat() 内部委托给 self.provider.stream_chat()
    - cost/retry/cost 控制由 provider.base.with_resilience 中间件保证
    - 默认从 env LLM_PROVIDER (mock/openai/anthropic/deepseek/zhipu/tongyi/moonshot) 选 provider
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Union

logger = logging.getLogger("recruittech.agents")


# ---------------------------------------------------------------------------
# Agent 内部统一的 LLMResponse dataclass (从 provider.LLMResponse 转)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LLMResponse:
    """Agent 层 LLM 响应 — 与 providers.llm.base.LLMResponse 解耦的轻量 dataclass.

    由 LLMClient 在 provider 返回后转换而成,Agent 业务代码应使用本 dataclass
    而不是直接依赖 providers.LLMResponse。
    """

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    raw: Any = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _dict_messages_to_provider(messages: list[dict]) -> list[Any]:
    """把 runtime 历史约定的 dict messages 转成 provider 层的 Message dataclass."""
    from providers.llm.base import Message, ToolCall

    out: list[Message] = []
    for m in messages:
        tool_calls = None
        if m.get("tool_calls"):
            tool_calls = []
            for tc in m["tool_calls"]:
                func = tc.get("function") if isinstance(tc.get("function"), dict) else None
                if func is not None:
                    name = func.get("name", "")
                    args_raw = func.get("arguments", {})
                    if isinstance(args_raw, str):
                        try:
                            import json as _json

                            args = _json.loads(args_raw)
                        except Exception:
                            args = {"_raw": args_raw}
                    else:
                        args = args_raw or {}
                else:
                    name = tc.get("name", "")
                    args = tc.get("arguments", {}) or {}
                tool_calls.append(
                    ToolCall(id=tc.get("id", ""), name=name, arguments=args)
                )
        out.append(
            Message(
                role=m["role"],
                content=m.get("content", "") or "",
                name=m.get("name"),
                tool_call_id=m.get("tool_call_id"),
                tool_calls=tool_calls,
            )
        )
    return out


def _provider_response_to_agent(resp: Any) -> LLMResponse:
    """providers.llm.base.LLMResponse -> agents.runtime.LLMResponse."""
    return LLMResponse(
        text=resp.content,
        model=resp.model,
        input_tokens=resp.usage.prompt_tokens,
        output_tokens=resp.usage.completion_tokens,
        finish_reason=resp.finish_reason,
        raw=resp,
    )


class MemoryScope(str, Enum):
    short_term = "short_term"   # 单次对话上下文
    working = "working"         # 当前任务工作记忆(可跨调用保留)
    long_term = "long_term"     # 用户画像/历史偏好(永久)


@dataclass
class AgentInput:
    """智能体统一输入协议."""

    user_id: str
    persona: str                       # jobseeker / employer / hr / dept_head / admin
    text: str                          # 用户的原始输入
    context: dict[str, Any] = field(default_factory=dict)  # 业务上下文
    memory_scope: MemoryScope = MemoryScope.working
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    trace_id: Optional[str] = None
    max_cost_cents: int = 50           # 单次调用最大成本(分)


@dataclass
class AgentOutput:
    """智能体统一输出协议."""

    agent_name: str
    text: str                          # 给用户的回复
    artifacts: dict[str, Any] = field(default_factory=dict)  # 结构化产物
    memory_writes: list[dict] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    cost_cents: int = 0
    tokens_used: int = 0
    request_id: str = ""
    duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    reasoning_chain: list[dict] = field(default_factory=list)  # 推理步骤(对用户可见)


@dataclass
class ToolCall:
    """Tool 调用记录."""

    name: str
    args: dict[str, Any]
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


class BaseAgent(ABC):
    """所有智能体的基类."""

    name: str = "base_agent"
    description: str = ""
    version: str = "1.0.0"
    required_personas: tuple[str, ...] = ()

    def __init__(self, llm_client: Any = None, memory: Any = None, tracer: Any = None, **kwargs):
        # 同时接受 llm= / llm_client= 两种写法
        self.llm = kwargs.pop("llm", None) or llm_client
        self.memory = memory
        self.tracer = tracer
        self._tools: dict[str, Callable[..., Awaitable[Any]]] = {}
        # 静默吞掉其他未来扩展 kwargs (兼容不同 agent 的自定义参数)
        for k, v in kwargs.items():
            setattr(self, k, v)

    # ---- Tool 注册 ----

    def register_tool(self, name: str, fn: Callable[..., Awaitable[Any]]):
        """注册一个工具方法,Agent 可在 prompt 中调用."""
        self._tools[name] = fn

    async def call_tool(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not registered in {self.name}")
        start = time.time()
        try:
            result = await self._tools[name](**kwargs)
            logger.debug(f"[{self.name}] tool {name} OK in {(time.time()-start)*1000:.0f}ms")
            return result
        except Exception as e:
            logger.exception(f"[{self.name}] tool {name} failed: {e}")
            raise

    # ---- Memory 读写 ----

    async def remember(self, scope: MemoryScope, key: str, value: Any, user_id: str):
        if self.memory is None:
            return
        await self.memory.write(scope=scope, user_id=user_id, key=key, value=value)

    async def recall(self, scope: MemoryScope, key: str, user_id: str, default: Any = None) -> Any:
        if self.memory is None:
            return default
        return await self.memory.read(scope=scope, user_id=user_id, key=key, default=default)

    # ---- 核心执行入口 ----

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        start = time.time()
        try:
            # 1. persona 检查
            if self.required_personas and agent_input.persona not in self.required_personas:
                return AgentOutput(
                    agent_name=self.name,
                    text="",
                    success=False,
                    error=f"persona '{agent_input.persona}' not allowed for {self.name}",
                    request_id=agent_input.request_id,
                )

            # 2. tracing
            if self.tracer:
                self.tracer.start_span(self.name, trace_id=agent_input.trace_id)

            # 3. 实际处理(子类实现)
            output = await self._handle(agent_input)

            # 4. 写 memory
            if self.memory and output.memory_writes:
                for w in output.memory_writes:
                    await self.memory.write(
                        scope=w.get("scope", MemoryScope.working),
                        user_id=agent_input.user_id,
                        key=w["key"],
                        value=w["value"],
                    )

            output.agent_name = self.name
            output.request_id = agent_input.request_id
            output.duration_ms = int((time.time() - start) * 1000)
            output.success = True
            # 收集推理链(如果有)
            if hasattr(self, '_last_reasoning'):
                output.reasoning_chain = getattr(self, '_last_reasoning', [])
            return output

        except Exception as e:
            logger.exception(f"[{self.name}] run failed: {e}")
            return AgentOutput(
                agent_name=self.name,
                text="",
                success=False,
                error=str(e),
                request_id=agent_input.request_id,
                duration_ms=int((time.time() - start) * 1000),
            )
        finally:
            if self.tracer:
                self.tracer.end_span()

    @abstractmethod
    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        """子类实现的核心逻辑."""
        ...


# ---- LLM 调用辅助(走 providers 抽象层) ----

# Provider 来源类型:LLMProvider 实例 / 字符串名(openai/anthropic/.../mock) / None
ProviderArg = Union[Any, str, None]


def _is_mock_provider(provider: Any) -> bool:
    return getattr(provider, "provider_name", "") == "mock"


def _resolve_provider_by_name(name: str) -> Any:
    """把字符串名解析成 LLMProvider 实例.优先用 registry,失败则 fallback 到 mock."""
    name = (name or "mock").lower()
    if name == "mock":
        from providers.llm.mock_provider import MockLLMProvider

        return MockLLMProvider()
    try:
        from providers.registry import get_llm_provider

        return get_llm_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[LLM] registry resolve failed for {name!r}: {e}; falling back to mock")
        from providers.llm.mock_provider import MockLLMProvider

        return MockLLMProvider()


def _wrap_legacy_openai_client(openai_client: Any, model: str) -> Any:
    """向后兼容:把老 LLMClient(openai_client=openai_async) 包成 OpenAIProvider.

    业务代码可能直接传了一个 AsyncOpenAI 实例,我们把它注入 OpenAIProvider,
    这样 provider.chat() 仍走标准 OpenAI SDK 路径,行为与旧代码一致。
    """
    from providers.llm.openai_provider import OpenAIProvider

    p = OpenAIProvider.__new__(OpenAIProvider)
    # 手工跳过 OpenAIProvider.__init__ 的 api_key 检查,直接挂 SDK client
    p.provider_name = "openai"
    p.api_key = getattr(openai_client, "api_key", "") or "legacy"
    p.base_url = None
    p.client = openai_client
    p.default_model = model
    p._rate_per_sec = 10.0
    p._burst = 20
    p._extra = {}

    # 把 chat / stream_chat 重新绑成装饰过的版本 — 这里用未装饰版本即可,
    # 因为客户端已经在外层 LLMClient 处被调用,我们不再额外加熔断/retry.
    async def _chat(messages, *, model=None, temperature=0.7, max_tokens=1024, **kwargs):
        from providers.llm.base import LLMResponse, Usage

        params = {
            "model": model or p.default_model,
            "messages": OpenAIProvider._serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        params.update(kwargs)
        if "response_format" in kwargs:
            params["response_format"] = kwargs["response_format"]
        resp = await p.client.chat.completions.create(**params)
        return OpenAIProvider._parse_completion(p, resp)

    async def _stream(messages, *, model=None, temperature=0.7, max_tokens=1024, **kwargs):
        params = {
            "model": model or p.default_model,
            "messages": OpenAIProvider._serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        params.update(kwargs)
        stream = await p.client.chat.completions.create(**params)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def _tool_call(messages, tools, *, model=None, temperature=0.0, max_tokens=1024, **kwargs):
        resp = await _chat(messages, model=model, temperature=temperature,
                           max_tokens=max_tokens, tools=tools, **kwargs)
        from providers.llm.base import ToolCallResult

        return ToolCallResult(content=resp.content, tool_calls=resp.tool_calls, finish_reason=resp.finish_reason)

    p.chat = _chat  # type: ignore[assignment]
    p.stream_chat = _stream  # type: ignore[assignment]
    p.tool_call = _tool_call  # type: ignore[assignment]
    return p


class _DummyProvider:
    """仅供 MockLLMProvider 内部 LLMClient helper 使用 — 不会触发网络.

    MockLLMProvider.__init__ 需要创建一个 LLMClient(openai_client=None) 来复用
    _mock_response 路由逻辑。如果让 LLMClient 再走 provider 解析,会无限递归
    创建 MockLLMProvider -> LLMClient -> MockLLMProvider -> ...
    所以这里用一个 stub 对象占位 self.provider。
    """

    provider_name = "dummy"
    default_model = "mock-model"
    supported_models = ["mock-model"]
    pricing: dict = {}
    client = None

    def calculate_cost(self, model: str, usage: Any) -> float:  # noqa: ARG002
        return 0.0


class LLMClient:
    """统一 LLM 调用封装 — 内部委托给 backend.providers 抽象层.

    设计要点:
    - 默认从 env LLM_PROVIDER 选 provider;默认 "mock"
    - self.provider.chat() / self.provider.stream_chat() 是真正的 LLM 调用入口
    - cost/retry/circuit breaker 全部由 providers.base.with_resilience 中间件承担
    - 调用接口向后兼容:llm.call(messages, ...) 仍返回 (text, in_tok, out_tok)
    - 老的 LLMClient(openai_client=...) 写法被适配为 OpenAIProvider 包装
    """

    def __init__(
        self,
        provider: ProviderArg = None,
        *,
        # 向后兼容: 老 LLMClient(openai_client=..., model=..., price=...) 写法
        openai_client: Any = None,
        model: Optional[str] = None,
        price_per_1k_cents: float = 0.5,
        max_retries: int = 3,
        # 内部标志:MockLLMProvider 用 True 来避免递归(provider 自己持有 LLMClient 当 helper)
        _skip_provider_resolve: bool = False,
    ):
        # ---- 1. 决定 provider ----
        # 优先级: provider kw > openai_client 兼容路径 > env LLM_PROVIDER > mock
        if _skip_provider_resolve:
            # 内部 helper,无需真 provider — 设个哑对象即可(仅用于 _mock_response)
            self.provider = _DummyProvider()
        elif provider is None:
            if openai_client is not None:
                # 旧调用方式: LLMClient(openai_client=openai_instance) — 走 OpenAIProvider
                provider = _wrap_legacy_openai_client(openai_client, model or "gpt-4o")
            else:
                env_name = (os.getenv("LLM_PROVIDER") or "mock").lower()
                provider = env_name

        # provider 是字符串名 → 解析
        if isinstance(provider, str):
            self.provider = _resolve_provider_by_name(provider)
        elif not _skip_provider_resolve:
            # provider 已经是 LLMProvider 实例
            self.provider = provider

        # ---- 2. 兼容字段 (旧代码可能还会读 self.client / self.model / self.price) ----
        self.client = getattr(self.provider, "client", None) or openai_client
        self.model = model or getattr(self.provider, "default_model", None) or "gpt-4o"
        self.price = price_per_1k_cents
        self.max_retries = max_retries

    # ---- 工厂 ----

    @classmethod
    def from_env(cls) -> "LLMClient":
        """自动从 env (LLM_PROVIDER 等) 构造."""
        return cls()

    # ---- 主入口 ----

    async def call(
        self,
        messages: list[dict],
        max_cost_cents: int = 50,
        temperature: float = 0.7,
        max_retries: int = 3,
        response_format: Optional[dict] = None,
    ) -> tuple[str, int, int]:
        """调用 LLM, 返回 (text, input_tokens, output_tokens).

        向后兼容: 旧业务代码 (toolkit.llm_call, react agent 等) 直接解构三元素。
        新代码优先用 chat() / stream_chat() 拿到完整的 LLMResponse。
        """
        provider_messages = _dict_messages_to_provider(messages)

        # 调 provider;retry/cost/circuit breaker 都在 provider 的 @with_resilience 中
        try:
            resp = await self.provider.chat(
                provider_messages,
                model=self.model,
                temperature=temperature,
                max_tokens=1024,
                response_format=response_format,
            )
        except Exception as e:
            # provider 失败 — 仅 mock 兜底
            if _is_mock_provider(self.provider):
                text = self._mock_response(messages)
                logger.warning(f"[LLM] mock fallback after provider error: {e}")
                return text, 100, 50
            raise

        # cost 估算 (仅 warning,不阻断 — cost 控制交由中间件)
        in_tok = resp.usage.prompt_tokens
        out_tok = resp.usage.completion_tokens
        cost = self.estimate_cost_cents(in_tok, out_tok)
        if cost > max_cost_cents:
            logger.warning(
                f"[LLM] cost {cost:.1f}¢ exceeds budget {max_cost_cents}¢ "
                f"(provider={self.provider.provider_name}, model={resp.model})"
            )

        return resp.content, in_tok, out_tok

    async def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format: Optional[dict] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """新风格 API: 内部调 self.provider.chat() 并返回 Agent LLMResponse dataclass."""
        provider_messages = _dict_messages_to_provider(messages)
        resp = await self.provider.chat(
            provider_messages,
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **kwargs,
        )
        return _provider_response_to_agent(resp)

    async def stream_chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式对话: 内部调 self.provider.stream_chat()."""
        provider_messages = _dict_messages_to_provider(messages)
        async for chunk in self.provider.stream_chat(
            provider_messages,
            model=model or self.model,
            temperature=temperature,            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk

    # ---- 工具 ----

    def estimate_cost_cents(self, in_tok: int, out_tok: int) -> int:
        """按 self.price (cents/1k tokens) 估算成本."""
        return int((in_tok + out_tok) / 1000 * self.price)

    def cost_usd(self, model: str, in_tok: int, out_tok: int) -> float:
        """按 provider.pricing 表算 USD — 用于委托给 cost 中间件."""
        if hasattr(self.provider, "calculate_cost"):
            from providers.llm.base import Usage

            try:
                return self.provider.calculate_cost(
                    model,
                    Usage(prompt_tokens=in_tok, completion_tokens=out_tok),
                )
            except Exception:
                return 0.0
        return 0.0

    # ---- 兼容: 老的 mock 路由逻辑 (供 MockLLMProvider 复用) ----

    def _mock_response(self, messages: list[dict]) -> str:
        """智能 mock — 模拟"真 LLM"按 system prompt 的指令生成对应格式输出.

        保留在这里是为了向后兼容 + 让 MockLLMProvider 直接复用,无需重复实现.
        业务代码不应该再直接调这个方法 — 改用 chat() / call().
        """
        system = ""
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
        last = messages[-1].get("content", "") if messages else ""

        user_text = self._extract_user_text(last)
        full = system + "\n" + last

        if "情感分析专家" in full or "情感智能助手" in full or "emotion" in full.lower() and "分析" in full:
            return self._mock_emotion_response(user_text)
        if "职业规划顾问" in full or "career_planner" in full.lower():
            return self._mock_career_response(user_text)
        if "画像综合专家" in full or "信息整合专家" in full or "整合专家" in full:
            return self._mock_clarifier_response(user_text)
        if "战略解码专家" in full or "战略" in full and "愿景" in full:
            return self._mock_vision_response(user_text)
        if "需求细化" in full or "JD" in full or "jd" in full.lower() and "部门" in full:
            return self._mock_jobspec_response(user_text)
        if "人才需求顾问" in full or ("人才" in full and "画像" in full):
            return self._mock_talent_brief_response(user_text)
        if "资质审核专家" in full or ("资质" in full and "审核" in full):
            return self._mock_compliance_response(user_text)
        if "多方对话协调员" in full or "协调员" in full:
            return self._mock_multiparty_response(user_text)
        if "制度管家" in full or "企业制度" in full:
            return self._mock_policy_response(user_text)
        if "全生命周期" in full or "HR 全生命周期" in full:
            return '{"stage": "general", "answer": "我是 HR 助手,可以帮你查询制度、流程等。", "action_items": [], "create_ticket": false}'
        if "互评整合专家" in full:
            return '{"mutual_score": 0.75, "strengths": ["技术扎实"], "concerns": [], "recommendation": "proceed", "next_steps": ["安排面试"]}'
        if "工作教练" in full or "知心朋友" in full:
            return '{"rating": "good", "advice": "继续保持,明天继续努力", "warnings": [], "action_items": ["复盘今天的工作"], "mood_score": 0.5, "topics": []}'
        if "真诚HR" in full:
            return "我是真诚 HR 助手,有具体问题请告诉我。"
        if "profile_agent" in full.lower() or "画像采集" in full or "建档引导" in full:
            return self._mock_profile_response(user_text)

        if "Thought:" in last or "Action:" in last or "Final Answer" in system:
            return "Thought: 我已收集足够信息,可以给出回答。\nFinal Answer: " + self._mock_general_response(user_text)

        return self._mock_general_response(user_text)

    @staticmethod
    def _mock_emotion_response(text: str) -> str:
        positive_signals = ["开心", "高兴", "happy", "太好了", "拿到", "成功", "通过", "😊"]
        negative_signals = ["崩溃", "绝望", "难过", "焦虑", "压力", "失败", "挂", "延期"]
        risk_signals = ["不想活", "没意思", "自杀", "崩溃", "废"]

        is_positive = any(s in text for s in positive_signals)
        is_negative = any(s in text for s in negative_signals)
        is_risk = any(s in text for s in risk_signals)

        if is_risk:
            return json.dumps({
                "emotions": [{"name": "hopelessness", "intensity": 0.9, "evidence": "检测到高风险词"}],
                "primary_emotion": "hopelessness",
                "complexity": "contradictory",
                "underlying_need": "需要被看见、被理解",
                "risk_level": "severe",
                "recommended_response_tone": "warm",
                "response": "我注意到你可能正在经历非常艰难的时期。我在这里,愿意陪你。",
            }, ensure_ascii=False)
        if is_negative:
            return json.dumps({
                "emotions": [{"name": "sadness", "intensity": 0.7, "evidence": "检测到负面表达"}],
                "primary_emotion": "sadness",
                "complexity": "simple",
                "underlying_need": "需要被倾听",
                "risk_level": "mild",
                "recommended_response_tone": "listening",
                "response": "听起来你今天不太好受。想不想说说发生了什么?",
            }, ensure_ascii=False)
        if is_positive:
            return json.dumps({
                "emotions": [{"name": "joy", "intensity": 0.8, "evidence": "检测到积极表达"}],
                "primary_emotion": "joy",
                "complexity": "simple",
                "underlying_need": "需要分享喜悦",
                "risk_level": "none",
                "recommended_response_tone": "warm",
                "response": "为你高兴! 发生了什么好事?",
            }, ensure_ascii=False)
        return json.dumps({
            "emotions": [{"name": "neutral", "intensity": 0.3, "evidence": "中性表达"}],
            "primary_emotion": "neutral",
            "complexity": "simple",
            "underlying_need": "日常交流",
            "risk_level": "none",
            "recommended_response_tone": "listening",
            "response": "我在听,有什么想聊的?",
        }, ensure_ascii=False)

    @staticmethod
    def _mock_profile_response(text: str) -> str:
        return json.dumps({
            "updated_profile": {"raw_text_sample": text[:50]},
            "next_questions": ["能否更详细描述你的工作经历?", "你的核心技能是什么?"],
            "completion": 0.4,
            "warm_response": "好的,我记下了一部分信息。还有什么想补充的吗?",
        }, ensure_ascii=False)

    @staticmethod
    def _mock_career_response(text: str) -> str:
        return json.dumps({
            "short_term": [{"title": "更新简历并投递目标公司", "duration": "2 周", "priority": "high"}],
            "mid_term": [{"title": "完成目标领域认证", "duration": "3 个月"}],
            "long_term": [{"title": "成为领域专家", "duration": "3 年"}],
            "learning_paths": [],
            "recommended_roles": [],
            "skill_gaps": [{"skill": "云原生", "importance": "medium", "acquisition_difficulty": "medium"}],
            "market_insights": {"salary_trends": {"python": "20-50k/月"}, "hot_skills": ["AI/LLM", "云原生"]},
        }, ensure_ascii=False)

    @staticmethod
    def _mock_clarifier_response(text: str) -> str:
        return json.dumps({
            "profile_synthesis": {
                "summary": {"value": "综合画像测试", "reasoning": "基于用户输入综合"},
                "explicit_skills": [{"value": "Python", "reasoning": "用户在文本中提到"}],
                "implicit_traits": [{"value": "学习能力强", "reasoning": "从用户表述推断"}],
                "value_orientation": [{"value": "成长", "reasoning": "..."}],
                "career_interests": [{"value": "AI", "reasoning": "..."}],
            },
            "real_needs": {
                "explicit": [{"value": "稳定工作", "reasoning": "..."}],
                "implicit": [{"value": "成长空间", "reasoning": "..."}],
                "must_haves": [{"value": "团队氛围", "reasoning": "..."}],
                "nice_to_haves": [],
                "deal_breakers": [],
            },
            "contradictions": [],
            "follow_up_questions": [
                {"question": "能说说你的工作经历吗?", "priority": "high", "purpose": "补全 experience"}
            ],
            "info_completeness": {"value": 0.5, "reasoning": "..."},
            "overall_confidence": 0.6,
        }, ensure_ascii=False)

    @staticmethod
    def _mock_vision_response(text: str) -> str:
        return json.dumps({
            "vision": {"statement": "成为行业领先", "horizon": "3-5年"},
            "planning": {"statement": "扩展团队", "horizon": "1年"},
            "strategy": {"statement": "聚焦 AI", "horizon": "1年"},
            "tactic": [],
            "gaps": [],
            "follow_up_questions": ["年度战略可以更具体吗?"],
        }, ensure_ascii=False)

    @staticmethod
    def _mock_jobspec_response(text: str) -> str:
        return json.dumps({
            "responsibilities": ["做开发", "参与设计"],
            "hard_requirements": [{"category": "技能", "value": "Python", "min_years": 3}],
            "nice_to_haves": [],
            "draft_jd": text[:200],
            "over_spec_flags": [],
        }, ensure_ascii=False)

    @staticmethod
    def _mock_talent_brief_response(text: str) -> str:
        return json.dumps({
            "hard_constraints": [],
            "soft_preferences": [],
            "talent_image_draft": {"summary": "测试画像"},
            "follow_up_questions": ["能否具体描述理想候选人的 3 个特质?"],
        }, ensure_ascii=False)

    @staticmethod
    def _mock_compliance_response(text: str) -> str:
        return json.dumps({
            "trust_score": 0.75,
            "verified_fields": {"company_name": "测试"},
            "missing_items": ["建议补充法人身份证"],
            "warnings": [],
            "expiry_risk": False,
            "summary": "基础验证通过",
        }, ensure_ascii=False)

    @staticmethod
    def _mock_multiparty_response(text: str) -> str:
        return json.dumps({
            "stakeholders": [],
            "conflicts": [],
            "proposed_resolution": "建议三方会议沟通。",
            "decision_summary": "尚未达成共识",
        }, ensure_ascii=False)

    @staticmethod
    def _mock_policy_response(text: str) -> str:
        return json.dumps({
            "items": [{"category": "other", "title": "制度", "content": "已入库"}],
            "legal_risks": [],
            "faq_version": [],
        }, ensure_ascii=False)

    @staticmethod
    def _mock_general_response(text: str) -> str:
        return f"我理解了 — 关于「{text[:30]}」,让我想想..."

    @staticmethod
    def _extract_user_text(prompt: str) -> str:
        """从 prompt 中提取用户真实输入(剥离模板指令)."""
        import re
        m = re.search(r"用户(?:新)?输入[::]\s*\n?(.+?)(?:\n\n|\Z)", prompt, re.DOTALL)
        if m:
            return m.group(1).strip()
        m = re.search(r'"([^"]+)"', prompt)
        if m:
            return m.group(1).strip()
        lines = [l.strip() for l in prompt.split("\n") if l.strip() and len(l.strip()) < 200]
        if lines:
            return min(lines, key=len)
        return prompt[:200]
