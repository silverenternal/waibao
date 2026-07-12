"""Interview Report — T2202.

Aggregates per-question scores into a 5-dimension radar:
  - technical       技术深度
  - communication   沟通表达
  - thinking        思维能力
  - potential       成长潜力
  - culture         文化匹配

Also generates natural-language commentary per dimension and an
overall recommendation.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from providers.llm.base import LLMProvider, Message

logger = logging.getLogger("recruittech.services.interview_report")

DIMENSION_LABELS = {
    "technical": "技术",
    "communication": "沟通",
    "thinking": "思维",
    "potential": "潜力",
    "culture": "文化",
}


@dataclass
class DimensionScore:
    name: str
    score: float          # 0-100
    band: str             # weak / fair / good / excellent
    comment: str = ""


@dataclass
class InterviewReport:
    interview_id: str
    persona_id: str
    role: str
    overall_score: float = 0.0
    recommendation: str = "consider"   # strong_yes / yes / consider / no
    dimensions: list[DimensionScore] = field(default_factory=list)
    radar: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    stage_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_question: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "interview_id": self.interview_id,
            "persona_id": self.persona_id,
            "role": self.role,
            "overall_score": self.overall_score,
            "recommendation": self.recommendation,
            "dimensions": [
                {"name": d.name, "score": d.score, "band": d.band, "comment": d.comment}
                for d in self.dimensions
            ],
            "radar": self.radar,
            "summary": self.summary,
            "strengths": self.strengths,
            "improvements": self.improvements,
            "stage_breakdown": self.stage_breakdown,
            "per_question": self.per_question,
            "provider": self.provider,
        }


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


def aggregate_dimensions(
    answers: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, float]:
    """Aggregate per-question dimension scores into a single 0-100 per dimension.

    Each answer has ``dimensions`` like {communication: 80, thinking: 70, ...}.
    If a dimension is missing for an answer, we ignore it (do not zero-fill).
    """
    dim_totals: dict[str, list[float]] = {}
    for a in answers:
        for k, v in (a.get("dimensions") or {}).items():
            try:
                dim_totals.setdefault(k, []).append(float(v))
            except (TypeError, ValueError):
                continue
    return {k: round(sum(vs) / len(vs), 1) for k, vs in dim_totals.items() if vs}


def _project_to_target_dims(
    raw: dict[str, float],
    target: list[str] = ["technical", "communication", "thinking", "potential", "culture"],
) -> dict[str, float]:
    """Map the interviewer's 5 (or 7) dimensions into the canonical 5 radar dims.

    Source dimension keys (legacy / question-bank):
        communication, depth, tradeoff, creativity, ownership
    New AI interview (5 dims):
        technical, communication, thinking, potential, culture
    """
    mapping = {
        "communication": "communication",
        "depth": "technical",
        "tradeoff": "thinking",
        "creativity": "thinking",
        "ownership": "potential",
        "technical": "technical",
        "thinking": "thinking",
        "potential": "potential",
        "culture": "culture",
    }
    out: dict[str, list[float]] = {d: [] for d in target}
    for k, v in raw.items():
        target_key = mapping.get(k)
        if target_key:
            out[target_key].append(float(v))
    return {d: round(sum(vs) / len(vs), 1) if vs else 60.0 for d, vs in out.items()}


def _overall_from_radar(radar: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted average using the persona's weights (default 5/5/5/5/5)."""
    if not weights:
        weights = {d: 0.2 for d in radar.keys()}
    # Normalize weights
    total = sum(weights.values()) or 1.0
    score = 0.0
    for d, v in radar.items():
        w = weights.get(d, 0.2)
        score += v * (w / total)
    return round(max(0, min(100, score)), 1)


def _summarize_dimension(d: str, score: float) -> str:
    band = _band(score)
    templates = {
        "technical": {
            "excellent": "技术功底扎实,关键原理和取舍讲得到位。",
            "good": "技术能力良好,能解决主要问题,部分细节可再深入。",
            "fair": "技术基础尚可,复杂场景下需要更多支撑材料。",
            "weak": "技术深度不足,建议补充核心原理与项目实战。",
        },
        "communication": {
            "excellent": "表达清晰有结构,STAR 法则运用自如。",
            "good": "表达较为清楚,偶有跳跃,听众容易跟上。",
            "fair": "基本能说清问题,但结构感和重点不够突出。",
            "weak": "表达缺乏结构,建议多加练习结构化表达。",
        },
        "thinking": {
            "excellent": "思维灵活,能看到多种方案与权衡。",
            "good": "思路清晰,能给出合理方案与替代选项。",
            "fair": "思考有方向但不够全面,建议多角度推演。",
            "weak": "思维单一,需要加强系统性思考训练。",
        },
        "potential": {
            "excellent": "展现出强烈的ownership 与成长速度。",
            "good": "有自驱力,过往经历体现潜力。",
            "fair": "有一定潜力,但需要更多场景验证。",
            "weak": "潜力信号偏弱,建议补充更具挑战性的项目。",
        },
        "culture": {
            "excellent": "与团队文化高度契合,合作风格令人放心。",
            "good": "整体风格与团队一致,合作顺畅。",
            "fair": "在部分场景下与团队协作需要磨合。",
            "weak": "文化匹配度不高,需进一步评估。",
        },
    }
    return templates.get(d, {}).get(band, "")


async def generate_report(
    *,
    interview_id: str,
    persona_id: str,
    role: str,
    answers: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
    stage_breakdown: dict[str, dict[str, Any]] | None = None,
    llm: LLMProvider | None = None,
) -> InterviewReport:
    """Build the full report.

    Inputs:
        answers: list of dicts with at least
                 { overall, dimensions: {…}, band, feedback, strengths, improvements, stage, question_id }
        weights: persona weight dict (technical / communication / …)
        stage_breakdown: per-stage { score, count, signals }
    """
    weights = weights or {
        "technical": 0.25,
        "communication": 0.20,
        "thinking": 0.20,
        "potential": 0.20,
        "culture": 0.15,
    }
    # Aggregate per-question dims
    raw_dim_avg = aggregate_dimensions(answers, weights)
    radar = _project_to_target_dims(raw_dim_avg)
    overall = _overall_from_radar(radar, weights)
    rec = _recommendation(overall)

    # Build per-dimension commentary
    dimensions: list[DimensionScore] = []
    for d in ["technical", "communication", "thinking", "potential", "culture"]:
        score = radar.get(d, 60.0)
        dimensions.append(
            DimensionScore(
                name=DIMENSION_LABELS[d],
                score=score,
                band=_band(score),
                comment=_summarize_dimension(d, score),
            )
        )

    # Strengths / improvements
    strengths_pool: list[str] = []
    improvements_pool: list[str] = []
    for a in answers:
        strengths_pool.extend(a.get("strengths") or [])
        improvements_pool.extend(a.get("improvements") or [])
    strengths = _dedup(strengths_pool, 5)
    improvements = _dedup(improvements_pool, 5)

    # Try LLM-generated summary; fall back to template
    summary = ""
    provider = "heuristic"
    if llm is not None:
        try:
            summary = await _llm_summary(llm, role, persona_id, overall, rec, radar, strengths, improvements)
            provider = getattr(llm, "provider_name", "llm")
        except Exception as e:  # noqa: BLE001
            logger.debug("LLM summary failed: %s", e)

    if not summary:
        summary = _template_summary(role, persona_id, overall, rec)

    return InterviewReport(
        interview_id=interview_id,
        persona_id=persona_id,
        role=role,
        overall_score=overall,
        recommendation=rec,
        dimensions=dimensions,
        radar=radar,
        summary=summary,
        strengths=strengths or ["候选人能围绕问题进行阐述"],
        improvements=improvements or ["建议在结构化表达上多下功夫"],
        stage_breakdown=stage_breakdown or {},
        per_question=answers,
        provider=provider,
    )


async def _llm_summary(
    llm: LLMProvider,
    role: str,
    persona_id: str,
    overall: float,
    recommendation: str,
    radar: dict[str, float],
    strengths: list[str],
    improvements: list[str],
) -> str:
    prompt = (
        f"你是一位专业面试评估官。\n"
        f"请基于以下面试数据,生成 3-4 句中文综合评语:\n\n"
        f"岗位: {role}\n面试官人格: {persona_id}\n"
        f"总分: {overall}\n推荐: {recommendation}\n"
        f"五维评分: {json.dumps(radar, ensure_ascii=False)}\n"
        f"亮点: {'; '.join(strengths[:5])}\n"
        f"待提升: {'; '.join(improvements[:5])}\n"
    )
    resp = await llm.chat(
        messages=[Message(role="user", content=prompt)],
        model=os.environ.get("AI_INTERVIEW_SUMMARY_MODEL", "gpt-4o-mini"),
        temperature=0.4,
        max_tokens=300,
    )
    return (resp.content or "").strip()


def _template_summary(role: str, persona_id: str, overall: float, rec: str) -> str:
    bucket = {
        "strong_yes": "表现非常突出,建议优先进入下一轮。",
        "yes": "整体水平契合岗位,可推进复试。",
        "consider": "有一定潜力,建议结合团队匹配度综合判断。",
        "no": "当前匹配度偏低,建议暂缓推进。",
    }.get(rec, "表现一般")
    return (
        f"针对 {role} 岗位({persona_id} 面试官),候选人综合评分 {round(overall, 1)}。"
        f"{bucket}"
    )


def _dedup(seq: list[str], n: int) -> list[str]:
    out: list[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
        if len(out) >= n:
            break
    return out
