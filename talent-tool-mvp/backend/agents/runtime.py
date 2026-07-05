"""Agent Runtime — 统一智能体运行底座.

所有智能体必须继承 BaseAgent,以保证:
- 统一的输入/输出协议 (AgentInput/AgentOutput)
- Tool 注册与调用
- Memory 读写 (短期/工作/长期)
- Cost 控制 / Retry / Backoff
- Tracing (OpenTelemetry)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("recruittech.agents")


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


# ---- LLM 调用辅助(带 cost/retry) ----

class LLMClient:
    """统一 LLM 调用封装,带 cost 控制和重试."""

    def __init__(self, openai_client=None, model: str = "gpt-4o", price_per_1k_cents: float = 0.5):
        self.client = openai_client
        self.model = model
        self.price = price_per_1k_cents

    async def call(
        self,
        messages: list[dict],
        max_cost_cents: int = 50,
        temperature: float = 0.7,
        max_retries: int = 3,
        response_format: Optional[dict] = None,
    ) -> tuple[str, int, int]:
        """调用 LLM, 返回 (text, input_tokens, output_tokens)."""
        if self.client is None:
            # 离线/未配置时使用 mock 响应(开发模式)
            return self._mock_response(messages), 100, 50

        backoff = 1.0
        last_err = None
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                resp = await self.client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                in_tok = resp.usage.prompt_tokens if resp.usage else 0
                out_tok = resp.usage.completion_tokens if resp.usage else 0
                cost = (in_tok + out_tok) / 1000 * self.price
                if cost > max_cost_cents:
                    logger.warning(f"[LLM] cost {cost:.1f}¢ exceeds budget {max_cost_cents}¢")
                return text, in_tok, out_tok
            except Exception as e:
                last_err = e
                logger.warning(f"[LLM] attempt {attempt+1} failed: {e}")
                await asyncio.sleep(backoff)
                backoff *= 2
        raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_err}")

    def _mock_response(self, messages: list[dict]) -> str:
        """智能 mock — 不再用 if/elif 判断 agent 类型,而是模拟"真 LLM"的行为.

        原理: LLM 在没接 API 时,应该按 system prompt 的指令生成对应格式的输出.
        我们这里用启发式生成合理的响应,让 mock 看起来像 LLM.
        """
        system = ""
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
        last = messages[-1].get("content", "") if messages else ""

        # 抽取用户真实输入
        user_text = self._extract_user_text(last)
        full = system + "\n" + last

        # 按意图关键词路由(优先级最高,不依赖 system 是否含 JSON)
        # 用更具体的关键词,避免子串误匹配
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
        # 兜底:画像/profile(最后,避免与上面的子串冲突)
        if "profile_agent" in full.lower() or "画像采集" in full or "建档引导" in full:
            return self._mock_profile_response(user_text)

        # ReAct 模式
        if "Thought:" in last or "Action:" in last or "Final Answer" in system:
            return "Thought: 我已收集足够信息,可以给出回答。\nFinal Answer: " + self._mock_general_response(user_text)

        # 默认:通用友好回复
        return self._mock_general_response(user_text)

    @staticmethod
    def _mock_emotion_response(text: str) -> str:
        """模拟 LLM 情绪识别 — 用语义的轻量启发式,不用硬编码词典统计."""
        # 注意:这里只用于 mock,真实场景 LLM 会真正理解语义
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
        # 注意:这里只 mock 简单版本,bias 检测调用的是 detect_biases
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

    def estimate_cost_cents(self, in_tok: int, out_tok: int) -> int:
        return int((in_tok + out_tok) / 1000 * self.price)