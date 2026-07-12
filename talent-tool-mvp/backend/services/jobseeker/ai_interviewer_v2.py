"""AI Interviewer v2 — T2202.

Refactored to drive a 5-stage, persona-aware, Realtime-capable interview.

Stages
------
1. intro         — 破冰 + 自我介绍 (1-2 questions)
2. behavioral    — STAR 行为面试 (2-3 questions)
3. technical     — 技术深度 / 系统设计 (3-4 questions)
4. reverse_q     — 反问候选人 (1-2 questions)
5. closing       — 总结反馈 + 后续 (1 question)

Personas
--------
See :mod:`services.jobseeker.interview_personas`.

Realtime integration
--------------------
When a ``realtime_session`` is provided, the same question / answer flow
streams through the OpenAI Realtime API. The voice and temperature come
from the persona config.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from providers.llm.base import LLMProvider, Message
from providers.registry import get_llm_provider

from .interview_personas import PERSONAS, PERSONA_IDS, PersonaConfig, get_persona
from .interview_prober import (
    ALL_STAGES,
    STAGE_BEHAVIORAL,
    STAGE_CLOSING,
    STAGE_INTRO,
    STAGE_REVERSE_Q,
    STAGE_TECHNICAL,
    ProbingDecision,
    analyze_answer_depth,
    decide_follow_up,
    generate_follow_up,
)
from .interview_report import (
    DIMENSION_LABELS,
    InterviewReport,
    _band,
    _project_to_target_dims,
    _recommendation,
    aggregate_dimensions,
    generate_report,
)
from .question_bank import Question, question_bank

logger = logging.getLogger("recruittech.services.ai_interviewer_v2")


# ---------------------------------------------------------------------------
# Stage question bank (5 stages, per role)
# ---------------------------------------------------------------------------
STAGE_QUESTION_COUNTS: dict[str, int] = {
    STAGE_INTRO: 2,
    STAGE_BEHAVIORAL: 3,
    STAGE_TECHNICAL: 4,
    STAGE_REVERSE_Q: 1,
    STAGE_CLOSING: 1,
}

STAGE_LABELS = {
    STAGE_INTRO: "破冰 / 自我介绍",
    STAGE_BEHAVIORAL: "行为面试",
    STAGE_TECHNICAL: "技术深度",
    STAGE_REVERSE_Q: "反问环节",
    STAGE_CLOSING: "总结",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class InterviewQuestion:
    """An item in the 5-stage flow."""

    id: str
    stage: str
    seq: int                             # 1..N overall
    stage_seq: int                       # 1..M within stage
    title: str
    prompt: str
    expected_points: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    is_follow_up: bool = False
    parent_question_id: str | None = None


@dataclass
class InterviewAnswer:
    """An answer to a single question (with potential follow-ups)."""

    question_id: str
    stage: str
    transcript: str
    duration_sec: float = 0.0
    follow_ups: int = 0
    depth_score: float = 0.0
    coverage_signals: list[str] = field(default_factory=list)
    evaluation: dict[str, Any] = field(default_factory=dict)
    feedback: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Stage planner
# ---------------------------------------------------------------------------
def _build_stage_questions(
    role: str,
    difficulty: str,
    persona: PersonaConfig,
    role_label: str | None = None,
) -> list[InterviewQuestion]:
    """Pick questions for each stage using the static question bank + small
    persona-specific tweaks.
    """
    qs: list[InterviewQuestion] = []
    overall_seq = 0
    used_ids: set[str] = set()
    for stage in ALL_STAGES:
        count = STAGE_QUESTION_COUNTS[stage]
        # For reverse_q & closing, we use synthetic questions.
        if stage == STAGE_REVERSE_Q:
            overall_seq += 1
            new_id = f"q_{uuid.uuid4().hex[:10]}"
            used_ids.add(new_id)
            qs.append(
                InterviewQuestion(
                    id=new_id,
                    stage=stage,
                    seq=overall_seq,
                    stage_seq=1,
                    title="你有什么想问我的?",
                    prompt=(
                        "现在反问你。请告诉我关于这个团队、产品或岗位,你想了解什么?"
                    ),
                    expected_points=[
                        "提 1-2 个有深度的问题",
                        "关注团队/产品/成长空间",
                    ],
                    skills=["communication", "culture"],
                )
            )
            continue
        if stage == STAGE_CLOSING:
            overall_seq += 1
            new_id = f"q_{uuid.uuid4().hex[:10]}"
            used_ids.add(new_id)
            qs.append(
                InterviewQuestion(
                    id=new_id,
                    stage=stage,
                    seq=overall_seq,
                    stage_seq=1,
                    title="总结 + 反馈",
                    prompt=(
                        "最后一个问题: 如果用一个词形容自己,你会选什么?为什么?"
                    ),
                    expected_points=["自我认知", "举例支撑", "真诚"],
                    skills=["communication", "potential"],
                )
            )
            continue
        # Pull from bank
        type_map = {
            STAGE_INTRO: "behavioral",
            STAGE_BEHAVIORAL: "behavioral",
            STAGE_TECHNICAL: "technical",
        }
        wanted_type = type_map[stage]
        # Greedy select questions matching stage type
        candidates = question_bank.select_questions(
            role=role, count=count * 3, difficulty=difficulty  # over-fetch for variety
        )
        # Filter by type
        filtered = [q for q in candidates if q.type == wanted_type]
        if len(filtered) < count:
            # Pad with whatever we have
            extras = [q for q in candidates if q not in filtered]
            filtered = (filtered + extras)
        # De-dup by id and exclude already-used
        seen: set[str] = set()
        picked: list = []
        for q in filtered:
            base_id = q.id or f"q_{uuid.uuid4().hex[:10]}"
            if base_id in used_ids or base_id in seen:
                base_id = f"q_{uuid.uuid4().hex[:10]}"
            seen.add(base_id)
            used_ids.add(base_id)
            picked.append((q, base_id))
            if len(picked) >= count:
                break
        for i, (q, qid) in enumerate(picked):
            overall_seq += 1
            qs.append(
                InterviewQuestion(
                    id=qid,
                    stage=stage,
                    seq=overall_seq,
                    stage_seq=i + 1,
                    title=q.title,
                    prompt=q.prompt,
                    expected_points=q.expected_points,
                    skills=q.skills,
                )
            )
    return qs


# ---------------------------------------------------------------------------
# AI Interviewer v2
# ---------------------------------------------------------------------------
class AIInterviewerV2:
    """5-stage, persona-driven AI interviewer."""

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        realtime_session: Any | None = None,
        persona_id: str = "friendly_warm",
    ) -> None:
        self._llm = llm
        self._realtime = realtime_session
        self.persona = get_persona(persona_id)
        # question_id -> follow_up_count
        self._follow_up_count: dict[str, int] = {}

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------
    def plan(
        self,
        *,
        role: str,
        difficulty: str = "mid",
        role_label: str | None = None,
    ) -> list[InterviewQuestion]:
        return _build_stage_questions(
            role=role,
            difficulty=difficulty,
            persona=self.persona,
            role_label=role_label,
        )

    # ------------------------------------------------------------------
    # Per-question follow-up decision
    # ------------------------------------------------------------------
    def probe(
        self,
        *,
        question: InterviewQuestion,
        answer: InterviewAnswer,
    ) -> ProbingDecision:
        asked = self._follow_up_count.get(question.id, 0)
        decision = decide_follow_up(
            stage=question.stage,
            persona=self.persona,
            answer=answer.transcript,
            question_title=question.title,
            asked_follow_ups=asked,
        )
        if decision.should_follow_up:
            self._follow_up_count[question.id] = asked + 1
        return decision

    def build_follow_up(
        self,
        *,
        question: InterviewQuestion,
        answer: InterviewAnswer,
    ) -> InterviewQuestion:
        decision = self.probe(question=question, answer=answer)
        text = decision.follow_up_question or "能再多聊聊吗?"
        return InterviewQuestion(
            id=f"q_{uuid.uuid4().hex[:10]}",
            stage=question.stage,
            seq=question.seq,
            stage_seq=question.stage_seq,
            title=f"追问:{question.title}",
            prompt=text,
            expected_points=[],
            skills=question.skills,
            is_follow_up=True,
            parent_question_id=question.id,
        )

    # ------------------------------------------------------------------
    # Answer evaluation
    # ------------------------------------------------------------------
    async def evaluate(
        self,
        *,
        question: InterviewQuestion,
        answer: InterviewAnswer,
    ) -> dict[str, Any]:
        """Score a single answer (heuristic + optional LLM)."""
        depth, signals = analyze_answer_depth(answer.transcript)
        words = len(answer.transcript.split())
        # 5 canonical dimensions, all defaulted to 60
        base = 60.0
        length_bonus = min(20.0, words * 0.15)
        depth_bonus = depth * 20.0
        signal_bonus = min(15.0, len(signals) * 4.0)
        score = base + length_bonus + depth_bonus + signal_bonus
        score = max(0.0, min(100.0, score))
        # Apply persona-specific adjustment
        score = self._persona_adjust(score, signals, answer)
        dims = {
            "technical": round(60 + depth * 30 + signal_bonus, 1),
            "communication": round(60 + min(30, words * 0.2), 1),
            "thinking": round(60 + depth * 25 + (5 if "tradeoff" in signals else 0), 1),
            "potential": round(60 + (5 if "failure_reflection" in signals else 0)
                                + (5 if "teamwork" in signals else 0), 1),
            "culture": round(60 + min(20, words * 0.1), 1),
        }
        band = _band(score)
        result = {
            "overall": round(score, 1),
            "dimensions": dims,
            "band": band,
            "depth_score": depth,
            "coverage_signals": signals,
            "strengths": self._strengths(question, signals, depth, words),
            "improvements": self._improvements(question, signals, depth, words),
            "feedback": self._feedback(question, depth, signals, band),
        }
        # Try LLM-augmented feedback (optional)
        if not self._is_mock_provider() and answer.transcript:
            try:
                llm_result = await self._llm_evaluate(question, answer.transcript)
                if llm_result:
                    result["feedback"] = llm_result.get("feedback", result["feedback"])
                    for s in (llm_result.get("strengths") or [])[:2]:
                        if s and s not in result["strengths"]:
                            result["strengths"].insert(0, s)
                    for s in (llm_result.get("improvements") or [])[:2]:
                        if s and s not in result["improvements"]:
                            result["improvements"].insert(0, s)
            except Exception as e:  # noqa: BLE001
                logger.debug("LLM evaluation failed: %s", e)
        return result

    def _persona_adjust(self, score: float, signals: list[str], answer: InterviewAnswer) -> float:
        # Pressure persona rewards composure — short answers get a slight penalty
        if self.persona.id == "challenging_pressure":
            if not signals:
                return score - 5
        if self.persona.id == "rigorous_strict":
            if "numeric" not in signals and "metric" not in signals:
                return score - 5
        if self.persona.id == "tech_expert":
            if "cause" not in signals and len(answer.transcript.split()) > 30:
                return score - 3
        return score

    def _is_mock_provider(self) -> bool:
        name = getattr(self.llm, "provider_name", "")
        return name in {"", "mock", "mock_llm"}

    def _strengths(
        self, q: InterviewQuestion, signals: list[str], depth: float, words: int
    ) -> list[str]:
        out: list[str] = []
        if "numeric" in signals:
            out.append("用具体数字量化结果")
        if "tradeoff" in signals:
            out.append("明确讨论了方案权衡")
        if "failure_reflection" in signals:
            out.append("对失败经历有真诚复盘")
        if "teamwork" in signals:
            out.append("展现了团队协作意识")
        if words >= 80:
            out.append("回答内容详实")
        if depth >= 0.7:
            out.append("思路有深度,层次清晰")
        if not out:
            out.append(f"围绕「{q.title}」给出了基础回答")
        return out[:3]

    def _improvements(
        self, q: InterviewQuestion, signals: list[str], depth: float, words: int
    ) -> list[str]:
        out: list[str] = []
        if "numeric" not in signals and q.stage in {STAGE_BEHAVIORAL, STAGE_TECHNICAL}:
            out.append("补充具体数字(规模/比例/速度)")
        if "tradeoff" not in signals and q.stage == STAGE_TECHNICAL:
            out.append("主动说明方案 trade-off")
        if "failure_reflection" not in signals and q.stage == STAGE_BEHAVIORAL:
            out.append("可以分享一次失败经历与反思")
        if words < 30:
            out.append("回答略显简短,可用 STAR 法展开")
        if depth < 0.4:
            out.append("深度不足,建议结合数据/原理论证")
        if not out:
            out.append("继续保持,可在结构化表达上更下功夫")
        return out[:3]

    def _feedback(self, q: InterviewQuestion, depth: float, signals: list[str], band: str) -> str:
        if band == "excellent":
            return f"对「{q.title}」的回答很到位,继续保持。"
        if band == "good":
            return f"对「{q.title}」整体不错,可结合数据/原理再深入一层。"
        if band == "fair":
            return f"对「{q.title}」达到了基础水平,建议多准备量化案例。"
        return f"对「{q.title}」需要加强,建议针对性梳理相关知识点。"

    async def _llm_evaluate(self, q: InterviewQuestion, transcript: str) -> dict[str, Any] | None:
        try:
            prompt = (
                f"你是一位{self.persona.label}面试官。\n"
                f"题目: {q.title}\n题干: {q.prompt}\n"
                f"候选人回答: {transcript[:2000]}\n\n"
                f"请输出严格 JSON:\n"
                '{"feedback": "1-2 句中文反馈", '
                '"strengths": [str, str], "improvements": [str, str]}\n'
            )
            resp = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content) if isinstance(resp.content, str) else (resp.content or {})
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Stage scoring
    # ------------------------------------------------------------------
    def stage_breakdown(
        self, answers: list[InterviewAnswer]
    ) -> dict[str, dict[str, Any]]:
        """Per-stage aggregation."""
        out: dict[str, dict[str, Any]] = {}
        for stage in ALL_STAGES:
            stage_answers = [a for a in answers if a.stage == stage]
            if not stage_answers:
                out[stage] = {
                    "label": STAGE_LABELS[stage],
                    "count": 0,
                    "avg_score": 0.0,
                    "depth": 0.0,
                }
                continue
            evals = [a.evaluation.get("overall", 0) for a in stage_answers if a.evaluation]
            depth = [a.depth_score for a in stage_answers]
            out[stage] = {
                "label": STAGE_LABELS[stage],
                "count": len(stage_answers),
                "avg_score": round(sum(evals) / max(1, len(evals)), 1) if evals else 0.0,
                "depth": round(sum(depth) / max(1, len(depth)), 2) if depth else 0.0,
            }
        return out

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    async def build_report(
        self,
        *,
        interview_id: str,
        role: str,
        answers: list[InterviewAnswer],
    ) -> InterviewReport:
        rows = []
        for a in answers:
            ev = a.evaluation or {}
            rows.append(
                {
                    "question_id": a.question_id,
                    "overall": ev.get("overall", 0.0),
                    "dimensions": ev.get("dimensions", {}),
                    "band": ev.get("band", "fair"),
                    "feedback": ev.get("feedback", ""),
                    "strengths": ev.get("strengths", []),
                    "improvements": ev.get("improvements", []),
                }
            )
        sb = self.stage_breakdown(answers)
        return await generate_report(
            interview_id=interview_id,
            persona_id=self.persona.id,
            role=role,
            answers=rows,
            weights=self.persona.weights,
            stage_breakdown=sb,
            llm=self.llm if not self._is_mock_provider() else None,
        )

    # ------------------------------------------------------------------
    # Realtime helpers
    # ------------------------------------------------------------------
    def realtime_instructions(self, role: str) -> str:
        """Build the system prompt for the Realtime API session."""
        return (
            f"{self.persona.system_prompt}\n\n"
            f"当前岗位:{role}\n"
            f"按 5 阶段流程进行:破冰 → 行为 → 技术 → 反问 → 总结。\n"
            f"每提一个问题后,等候选人答完再判断是否追问。\n"
            f"如果候选人回答模糊,先用温和的语气请其具体化,再决定是否给出追问。\n"
            f"始终保持{self.persona.label}的语气。\n"
        )

    def realtime_tools(self) -> list[dict[str, Any]]:
        """Tool definitions for the Realtime session."""
        return [
            {
                "type": "function",
                "name": "move_to_next_question",
                "description": "完成当前题目的追问后,移动到下一题。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string", "enum": ALL_STAGES},
                    },
                },
            },
            {
                "type": "function",
                "name": "score_answer",
                "description": "对当前候选人的回答打分,0-100。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "overall": {"type": "number"},
                        "communication": {"type": "number"},
                        "thinking": {"type": "number"},
                        "technical": {"type": "number"},
                    },
                    "required": ["overall"],
                },
            },
        ]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
def make_interviewer(persona_id: str = "friendly_warm", **kwargs: Any) -> AIInterviewerV2:
    return AIInterviewerV2(persona_id=persona_id, **kwargs)
