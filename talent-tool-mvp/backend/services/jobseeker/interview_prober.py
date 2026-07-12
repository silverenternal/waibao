"""Interview Prober — T2202.

Decides whether to ask a follow-up / clarifying question based on the
candidate's last answer. Considers:
- Answer length (too short / too long)
- Depth signals (numbers, trade-offs, examples)
- Persona (e.g. rigorous_strict is more likely to follow up)
- Question stage (intro / behavioral / technical / reverse / closing)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .interview_personas import PersonaConfig


STAGE_INTRO = "intro"
STAGE_BEHAVIORAL = "behavioral"
STAGE_TECHNICAL = "technical"
STAGE_REVERSE_Q = "reverse_q"
STAGE_CLOSING = "closing"

ALL_STAGES = [STAGE_INTRO, STAGE_BEHAVIORAL, STAGE_TECHNICAL, STAGE_REVERSE_Q, STAGE_CLOSING]


@dataclass
class ProbingDecision:
    """Result of probe analysis."""

    should_follow_up: bool
    follow_up_question: str | None
    reason: str
    depth_score: float            # 0..1
    coverage_signals: list[str]   # 命中的深度信号

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_follow_up": self.should_follow_up,
            "follow_up_question": self.follow_up_question,
            "reason": self.reason,
            "depth_score": self.depth_score,
            "coverage_signals": self.coverage_signals,
        }


# Signal patterns
_NUMERIC = re.compile(r"\d+(\.\d+)?(%|x|ms|s|分钟|小时|天|个|人|万|亿|K|M|G|TB|QPS|TPS|RPS)?")
_TRADEOFF = re.compile(r"(权衡|trade.?off|取舍|利弊|优点|缺点|优势|劣势|instead of|rather than)")
_EXAMPLE = re.compile(r"(比如|例如|举个例子|for example|let's say|假设|假如)")
_CAUSE = re.compile(r"(因为|由于|so that|therefore|从而|所以|原因|根因|底层)")
_FAILURE = re.compile(r"(失败|教训|踩坑|bug|事故|复盘|root cause|postmortem)")
_TEAM = re.compile(r"(团队|协作|沟通|owner|lead|我负责|我推动|跨部门)")
_METRIC = re.compile(r"(延迟|latency|成功率|可用性|错误率|性能|throughput|吞吐|监控|报警|告警)")


def analyze_answer_depth(answer: str) -> tuple[float, list[str]]:
    """Return (depth_score 0..1, list of signals hit)."""
    if not answer or not answer.strip():
        return 0.0, []
    text = answer.strip()
    words = len(re.findall(r"\w+", text))
    chars = len(text)
    signals: list[str] = []
    if _NUMERIC.search(text):
        signals.append("numeric")
    if _TRADEOFF.search(text):
        signals.append("tradeoff")
    if _EXAMPLE.search(text):
        signals.append("example")
    if _CAUSE.search(text):
        signals.append("cause")
    if _FAILURE.search(text):
        signals.append("failure_reflection")
    if _TEAM.search(text):
        signals.append("teamwork")
    if _METRIC.search(text):
        signals.append("metric")
    # Length-based component
    length_score = 0.0
    if words >= 120:
        length_score = 0.5
    elif words >= 60:
        length_score = 0.35
    elif words >= 30:
        length_score = 0.2
    else:
        length_score = 0.05
    signal_score = min(0.5, len(signals) * 0.1)
    depth = round(min(1.0, length_score + signal_score), 2)
    return depth, signals


def decide_follow_up(
    *,
    stage: str,
    persona: PersonaConfig,
    answer: str,
    question_title: str,
    asked_follow_ups: int,
) -> ProbingDecision:
    """Decide whether to ask a follow-up and what to ask.

    Heuristic — for the real LLM-driven version, see :func:`generate_follow_up`
    which constructs a richer question.
    """
    depth, signals = analyze_answer_depth(answer)
    short_answer = len(answer.strip()) < 20 if answer else True

    # Hard cap on follow-ups
    if asked_follow_ups >= persona.max_follow_ups_per_question:
        return ProbingDecision(
            should_follow_up=False,
            follow_up_question=None,
            reason=f"max_follow_ups={persona.max_follow_ups_per_question} reached",
            depth_score=depth,
            coverage_signals=signals,
        )
    # Closing stage: never follow up
    if stage == STAGE_CLOSING:
        return ProbingDecision(
            should_follow_up=False,
            follow_up_question=None,
            reason="closing stage",
            depth_score=depth,
            coverage_signals=signals,
        )

    # Persona probability — short answers always follow up
    if short_answer:
        return ProbingDecision(
            should_follow_up=True,
            follow_up_question=(
                f"能再多说一些吗? 比如 {question_title} 里你提到的具体场景或数据。"
            ),
            reason="answer too short",
            depth_score=depth,
            coverage_signals=signals,
        )

    # Depth-based gating
    threshold = 0.5 - 0.2 * (persona.follow_up_probability - 0.5)
    if depth < threshold:
        follow_up = _build_follow_up(stage, persona, question_title, signals)
        return ProbingDecision(
            should_follow_up=True,
            follow_up_question=follow_up,
            reason=f"depth {depth} below persona threshold {threshold:.2f}",
            depth_score=depth,
            coverage_signals=signals,
        )
    return ProbingDecision(
        should_follow_up=False,
        follow_up_question=None,
        reason=f"depth {depth} sufficient",
        depth_score=depth,
        coverage_signals=signals,
    )


def _build_follow_up(stage: str, persona: PersonaConfig, title: str, signals: list[str]) -> str:
    """Generate a follow-up question from a template."""
    if stage == STAGE_BEHAVIORAL:
        if "failure_reflection" not in signals:
            return f"听起来不错,能讲讲在这个项目 {title} 里你犯过的一个错误或踩过的坑吗?"
        if "metric" not in signals:
            return f"很好,那怎么衡量这个项目 {title} 的最终效果?有哪些关键指标?"
    if stage == STAGE_TECHNICAL:
        if "tradeoff" not in signals:
            return f"你提到的方案,主要的权衡是什么?有没有考虑过替代方案?"
        if "numeric" not in signals:
            return f"能给一些具体数字吗?比如 {title} 涉及的 QPS / 延迟 / 数据量级。"
    if stage == STAGE_REVERSE_Q:
        return "你还有什么问题想问我吗?这对你判断这个团队也很重要。"
    if stage == STAGE_INTRO:
        return "能再多聊聊你最有成就感的一段经历吗?"
    return f"能再具体一点吗?关于 {title},我想了解得更深一些。"


def generate_follow_up(
    *,
    stage: str,
    persona: PersonaConfig,
    question_title: str,
    question_prompt: str,
    answer: str,
    signals: list[str],
    llm: Any | None = None,
) -> str:
    """Generate a follow-up question. If LLM is provided, use it for richer text;
    otherwise fall back to the template-based builder.
    """
    if llm is None:
        return _build_follow_up(stage, persona, question_title, signals)
    try:
        from providers.llm.base import Message
        prompt = (
            f"你是一位{persona.label}面试官。\n"
            f"题目: {question_title}\n题干: {question_prompt}\n"
            f"候选人回答: {answer[:1500]}\n"
            f"已识别的深度信号: {', '.join(signals) or '无'}\n"
            f"当前阶段: {stage}\n\n"
            f"请基于你的人格,生成一句简短的后续追问(中文,30字以内)。"
        )
        import asyncio
        loop = asyncio.get_event_loop()
        resp = asyncio.get_event_loop().run_until_complete(
            llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=persona.temperature,
                max_tokens=120,
            )
        )
        if resp and resp.content:
            return resp.content.strip().strip('"')[:200]
    except Exception:  # noqa: BLE001
        pass
    return _build_follow_up(stage, persona, question_title, signals)
