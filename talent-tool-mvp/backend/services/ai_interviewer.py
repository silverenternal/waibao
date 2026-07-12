"""AI Interviewer — T1301.

核心服务:编排 GPT-4V(视频理解) + Whisper(语音) + LLM 评估。

    AIInterviewer
        ├── generate_questions(role, count=10)
        ├── evaluate_answer(question, video_url, transcript) -> Score (0-100)
        └── generate_feedback(answers) -> FeedbackReport

依赖:
    - providers.vision (GPT-4V mock / 真实)
    - providers.stt (Whisper / Aliyun / mock)
    - providers.llm (用于评估 + 总结)
    - services.question_bank (静态题库)

注意:
    - mock 模式不调用外部 API,直接返回模板化的合理评估与反馈
    - 真实模式走 with_resilience / 熔断 / 重试
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from providers.llm.base import LLMProvider, Message
from providers.registry import get_llm_provider, get_stt_provider, get_vision_provider
from services.question_bank import Question, question_bank

logger = logging.getLogger("recruittech.services.ai_interviewer")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class AnswerScore:
    """单题评分结果."""

    question_id: str
    overall: float                       # 0-100
    dimensions: dict[str, float]         # {"communication": 78, ...}
    band: str                            # weak / fair / good / excellent
    transcript: str
    transcript_provider: str = ""        # whisper / aliyun_stt / mock_stt
    video_url: str | None = None
    vision_notes: str | None = None      # GPT-4V 看到的场景/表情/姿态备注
    feedback: str = ""                   # LLM 产出的具体建议
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FeedbackReport:
    """整体面试报告."""

    interview_id: str
    role: str
    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    radar: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    recommendation: str = "consider"   # strong_yes / yes / consider / no
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    per_question: list[AnswerScore] = field(default_factory=list)
    provider: str = "mock"


# ---------------------------------------------------------------------------
# 评分维度(默认)
# ---------------------------------------------------------------------------
DEFAULT_DIMENSIONS = [
    "communication",
    "depth",
    "tradeoff",
    "creativity",
    "ownership",
]


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------
class AIInterviewer:
    """生成问题 → 评估回答 → 汇总报告."""

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        stt: Any | None = None,
        vision: Any | None = None,
        question_bank_obj: Any = None,
        use_mock_fallback: bool = True,
    ) -> None:
        self._llm = llm
        self._stt = stt
        self._vision = vision
        self._bank = question_bank_obj or question_bank
        self._use_mock_fallback = use_mock_fallback

    # ------------------------------------------------------------------
    # Provider 懒加载(供 evaluate 内部用)
    # ------------------------------------------------------------------
    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    @property
    def stt(self) -> Any:
        if self._stt is None:
            self._stt = get_stt_provider()
        return self._stt

    @property
    def vision(self) -> Any:
        if self._vision is None:
            self._vision = get_vision_provider()
        return self._vision

    # ------------------------------------------------------------------
    # generate_questions
    # ------------------------------------------------------------------
    async def generate_questions(
        self,
        role: str,
        *,
        count: int = 10,
        difficulty: str | None = None,
        extra_with_llm: int = 0,
    ) -> list[Question]:
        """生成面试题。

        1. 从静态题库 select count 道
        2. 调用 LLM 补充 extra_with_llm 道 (失败 → 忽略)
        """
        base = self._bank.select_questions(role=role, count=count, difficulty=difficulty)
        if extra_with_llm > 0:
            extras = await self._bank.generate_extra_questions(
                role=role, count=extra_with_llm, llm_provider=self.llm
            )
            base.extend(extras)
        # 截断
        return base[: max(count, len(base))]

    # ------------------------------------------------------------------
    # evaluate_answer
    # ------------------------------------------------------------------
    async def evaluate_answer(
        self,
        question: Question,
        *,
        video_url: str | None = None,
        audio_bytes: bytes | None = None,
        audio_mime: str = "audio/webm",
        transcript: str | None = None,
        language: str = "auto",
    ) -> AnswerScore:
        """评估一道题的回答。

        流程:
            1. 如果已有 transcript,跳过 STT;否则调用 STT 转写 audio_bytes
            2. 调 GPT-4V 读 video_url (mock 或真实)
            3. LLM 综合输出 {overall, dimensions, band, strengths, improvements}
            4. mock 模式 → 模板化结果
        """
        # 1) STT
        provider_used = ""
        if not transcript:
            if audio_bytes:
                tr = await self._safe_transcribe(audio_bytes, mime=audio_mime, language=language)
                transcript = tr.text or ""
                # stt provider 名 用作 transcript_provider
                provider_used = getattr(self._stt, "provider_name", None) or "mock_stt"
            else:
                transcript = ""
        else:
            provider_used = "user_provided"

        # 2) vision
        vision_notes = await self._safe_vision(video_url=video_url, question=question)

        # 3) LLM 评估
        if self._is_mock_provider(self.llm):
            return self._mock_score(
                question=question,
                transcript=transcript or "",
                provider_used=provider_used,
                video_url=video_url,
                vision_notes=vision_notes,
            )
        return await self._llm_score(
            question=question,
            transcript=transcript or "",
            provider_used=provider_used,
            video_url=video_url,
            vision_notes=vision_notes,
        )

    # ------------------------------------------------------------------
    # generate_feedback
    # ------------------------------------------------------------------
    async def generate_feedback(
        self,
        answers: Iterable[AnswerScore],
        *,
        interview_id: str = "",
        role: str = "",
    ) -> FeedbackReport:
        """汇总报告。"""
        answers = list(answers)
        if not answers:
            return FeedbackReport(interview_id=interview_id, role=role, summary="无答题数据")

        # 维度聚合
        agg: dict[str, list[float]] = {}
        overalls: list[float] = []
        for a in answers:
            overalls.append(a.overall)
            for k, v in a.dimensions.items():
                agg.setdefault(k, []).append(v)
        dim_avg = {k: round(sum(vs) / len(vs), 1) for k, vs in agg.items() if vs}
        overall_avg = round(sum(overalls) / len(overalls), 1)

        # mock 模式 → 模板
        if self._is_mock_provider(self.llm):
            rec = _recommendation(overall_avg)
            strengths, improvements = _synth_strengths_weaknesses(answers)
            summary = _mock_summary(role, overall_avg, rec)
            return FeedbackReport(
                interview_id=interview_id,
                role=role,
                overall_score=overall_avg,
                dimension_scores=dim_avg,
                radar={**dim_avg, "overall": overall_avg},
                summary=summary,
                recommendation=rec,
                strengths=strengths,
                improvements=improvements,
                per_question=answers,
                provider="mock",
            )

        # 真实 LLM 汇总
        try:
            prompt = self._build_summary_prompt(answers, role)
            resp = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                model="gpt-4o-mini",
                temperature=0.4,
                max_tokens=900,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content) if isinstance(resp.content, str) else (resp.content or {})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"generate_feedback LLM failed: {e}")
            data = {}

        rec = data.get("recommendation") or _recommendation(overall_avg)
        return FeedbackReport(
            interview_id=interview_id,
            role=role,
            overall_score=overall_avg,
            dimension_scores=dim_avg,
            radar={**dim_avg, "overall": overall_avg},
            summary=data.get("summary") or _mock_summary(role, overall_avg, rec),
            recommendation=rec if rec in {"strong_yes", "yes", "consider", "no"} else _recommendation(overall_avg),
            strengths=data.get("strengths") or _synth_strengths_weaknesses(answers)[0],
            improvements=data.get("improvements") or _synth_strengths_weaknesses(answers)[1],
            per_question=answers,
            provider=getattr(self.llm, "provider_name", "unknown"),
        )

    # ------------------------------------------------------------------
    # 内部:prompt 构建
    # ------------------------------------------------------------------
    @staticmethod
    def _build_eval_prompt(question: Question, transcript: str, vision_notes: str) -> str:
        return (
            "你是一位资深的结构化面试评估官。请基于候选人回答 + 视频视觉信息 给出 JSON 评估。\n\n"
            f"题目:{question.title}\n"
            f"题干:{question.prompt}\n"
            f"期望要点:{'; '.join(question.expected_points)}\n"
            f"考察权重:{json.dumps(question.weights, ensure_ascii=False)}\n\n"
            f"候选人回答文本:\n\"\"\"\n{transcript[:3000]}\n\"\"\"\n"
            f"\n视频观察:{vision_notes or '(无)'}\n\n"
            "请输出严格 JSON:\n"
            "{\n"
            ' "overall": 0-100 整数,\n'
            ' "dimensions": {communication:0-100, depth:0-100, tradeoff:0-100, ...}, \n'
            ' "band": "weak|fair|good|excellent",\n'
            ' "strengths": [str, str], "improvements": [str, str],\n'
            ' "feedback": "一段给候选人的建设性反馈 (2-3 句)"\n'
            "}"
        )

    @staticmethod
    def _build_summary_prompt(answers: list[AnswerScore], role: str) -> str:
        bullets = []
        for a in answers:
            bullets.append(
                f"- [{a.question_id}] band={a.band} overall={a.overall} dims={a.dimensions} "
                f"feedback={a.feedback}"
            )
        return (
            f"请总结 {role} 候选人的整体表现,返回严格 JSON:\n"
            "{\n"
            ' "recommendation": "strong_yes|yes|consider|no",\n'
            ' "summary": "3-4 句中文摘要",\n'
            ' "strengths": [str, str, str],\n'
            ' "improvements": [str, str, str]\n'
            "}\n\n"
            "答题明细:\n" + "\n".join(bullets)
        )

    # ------------------------------------------------------------------
    # 内部:真实 LLM 评分
    # ------------------------------------------------------------------
    async def _llm_score(
        self,
        question: Question,
        transcript: str,
        provider_used: str,
        video_url: str | None,
        vision_notes: str | None,
    ) -> AnswerScore:
        prompt = self._build_eval_prompt(question, transcript, vision_notes or "")
        try:
            resp = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=700,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content) if isinstance(resp.content, str) else (resp.content or {})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"_llm_score failed: {e}; fallback to mock_score")
            return self._mock_score(
                question=question,
                transcript=transcript,
                provider_used=provider_used,
                video_url=video_url,
                vision_notes=vision_notes,
            )

        overall = float(data.get("overall") or 0)
        overall = max(0.0, min(100.0, overall))
        dims = {k: float(v) for k, v in (data.get("dimensions") or {}).items() if isinstance(v, (int, float))}
        band = data.get("band") or _band(overall)
        return AnswerScore(
            question_id=question.id,
            overall=overall,
            dimensions=dims,
            band=band if band in {"weak", "fair", "good", "excellent"} else _band(overall),
            transcript=transcript,
            transcript_provider=provider_used,
            video_url=video_url,
            vision_notes=vision_notes,
            feedback=data.get("feedback", ""),
            strengths=list(data.get("strengths", []))[:5],
            improvements=list(data.get("improvements", []))[:5],
        )

    # ------------------------------------------------------------------
    # 内部:mock 评分
    # ------------------------------------------------------------------
    @staticmethod
    def _mock_score(
        question: Question,
        transcript: str,
        provider_used: str,
        video_url: str | None,
        vision_notes: str | None,
    ) -> AnswerScore:
        text = transcript or ""
        words = len(re.findall(r"\w+", text))
        # 长度启发式分 (40-90)
        if words == 0:
            length_score = 35.0
        elif words < 30:
            length_score = 55.0
        elif words < 80:
            length_score = 75.0
        elif words < 200:
            length_score = 88.0
        else:
            length_score = 82.0  # 太长略减

        # 期望要点命中比例
        ep = question.expected_points or []
        if ep:
            hits = sum(1 for p in ep if p and (p.lower() in text.lower() or any(s for s in text.split() if p[:4].lower() in s.lower())))
            hit_ratio = hits / max(1, len(ep))
        else:
            hit_ratio = 0.5

        # 权重分数
        weights = question.weights or {"depth": 0.5, "communication": 0.5}
        base_dims = {
            "communication": length_score,
            "depth": min(100, length_score * 0.5 + 40 + hit_ratio * 30),
            "tradeoff": min(100, 50 + hit_ratio * 40),
            "creativity": min(100, 50 + hit_ratio * 30),
            "ownership": min(100, 55 + hit_ratio * 25),
        }
        # 额外: vision 信号 → 修饰 confidence / communication
        if vision_notes and "紧张" in vision_notes:
            base_dims["communication"] = max(40, base_dims["communication"] - 5)

        # 加权 overall — 只用 question.weights 指定的维度
        w_total = sum(weights.values()) or 1.0
        weighted = 0.0
        for k, w in weights.items():
            weighted += base_dims.get(k, 70.0) * w
        overall = weighted / max(w_total, 1e-6)
        overall = round(max(0.0, min(100.0, overall)), 1)
        band = _band(overall)

        strengths, improvements = _synth_strengths_weaknesses_for_one(question, base_dims, band)

        return AnswerScore(
            question_id=question.id,
            overall=overall,
            dimensions={k: round(v, 1) for k, v in base_dims.items()},
            band=band,
            transcript=text,
            transcript_provider=provider_used or "mock_stt",
            video_url=video_url,
            vision_notes=vision_notes or "mock:候选人正对镜头,语调平稳",
            feedback=_mock_one_feedback(question, band, hit_ratio),
            strengths=strengths,
            improvements=improvements,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def _safe_transcribe(self, audio: bytes, *, mime: str, language: str) -> Any:
        try:
            return await self.stt.transcribe(audio, mime=mime, language=language)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"STT failed: {e}")
            # 兜底 mock(并把 stt 替换)
            from providers.stt.mock_provider import MockSTTProvider

            self._stt = MockSTTProvider()
            return await self._stt.transcribe(audio, mime=mime, language=language)

    async def _safe_vision(self, *, video_url: str | None, question: Question) -> str | None:
        if not video_url:
            return None
        try:
            # 真实 GPT-4V 接口:vision.analyze_video / describe / classify_frame
            describe = getattr(self.vision, "describe_frame", None) or getattr(self.vision, "analyze", None)
            if describe is None:
                return None
            out = await describe(video_url, prompt=f"候选人在回答问题:{question.title}")
            if isinstance(out, dict):
                return out.get("text") or out.get("description") or json.dumps(out, ensure_ascii=False)[:400]
            return str(out)[:400]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"vision failed: {e}")
            return None

    def _is_mock_provider(self, provider: Any) -> bool:
        if provider is None:
            return True
        name = getattr(provider, "provider_name", "") or ""
        return name in {"", "mock", "mock_llm", "mock_stt"}


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------
def _band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "weak"


def _recommendation(overall: float) -> str:
    if overall >= 85:
        return "strong_yes"
    if overall >= 70:
        return "yes"
    if overall >= 55:
        return "consider"
    return "no"


def _synth_strengths_weaknesses(
    answers: list[AnswerScore],
) -> tuple[list[str], list[str]]:
    """从逐题 strengths / improvements 聚合成整体。"""
    s_pool: list[str] = []
    i_pool: list[str] = []
    for a in answers:
        s_pool.extend(a.strengths)
        i_pool.extend(a.improvements)
    # 保留前 5,去重保持顺序
    return _dedup(s_pool, 5), _dedup(i_pool, 5)


def _synth_strengths_weaknesses_for_one(
    q: Question, dims: dict[str, float], band: str
) -> tuple[list[str], list[str]]:
    """模板化的单题优点 + 改进。"""
    strong_dim = max(dims.items(), key=lambda kv: kv[1])[0]
    weak_dim = min(dims.items(), key=lambda kv: kv[1])[0]
    return (
        [f"{strong_dim} 维表现突出", f"抓住了「{q.expected_points[0] if q.expected_points else q.title}」要点"],
        [f"{weak_dim} 维可再深入,可结合量化数据", "答案结构化程度可加强,推荐 STAR 法则"],
    )


def _mock_one_feedback(q: Question, band: str, hit_ratio: float) -> str:
    if band == "excellent":
        return f"对「{q.title}」的回答很有结构,要点命中率高。继续保持这种思路清晰、论据扎实的风格。"
    if band == "good":
        return f"对「{q.title}」整体不错。若能把 {q.expected_points[0] if q.expected_points else '核心要点'} 再展开一层,会更有说服力。"
    if band == "fair":
        return f"对「{q.title}」回答到了基础,建议多准备一些量化案例,并按 STAR 结构组织答案。"
    return f"对「{q.title}」回答较为薄弱,建议针对性梳理 {q.skills or ['核心技能']} 相关案例。"


def _mock_summary(role: str, overall: float, rec: str) -> str:
    bucket = {
        "strong_yes": "候选人表现非常突出,建议优先安排下一轮。",
        "yes": "候选人整体水平契合岗位,可推进复试。",
        "consider": "候选人有一定潜力,建议结合团队匹配度综合判断。",
        "no": "候选人当前匹配度偏低,建议暂缓推进。",
    }.get(rec, "表现一般")
    return f"针对 {role} 岗位的整体表现评 {round(overall, 1)} 分。{bucket}"


def _dedup(seq: list[str], n: int) -> list[str]:
    out: list[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
        if len(out) >= n:
            break
    return out


# 单例 (供 API 层使用)
ai_interviewer = AIInterviewer()
