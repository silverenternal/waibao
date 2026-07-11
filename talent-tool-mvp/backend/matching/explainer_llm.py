"""Matching 2.0 — LLM 可解释匹配 + 反事实.

T901: generate_explain(match_score, candidate, role) -> {
    reasons, weak_points, counterfactual
}

设计原则:
- 一次 LLM 调用生成 reasons + weak_points + counterfactual (避免多次调用)
- mock provider 也能跑通 (返回模板化解释)
- 反事实:基于 weak_points 给出 "如果……会更匹配" 提示与分数提升估计
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

logger = logging.getLogger("recruittech.matching.explainer_llm")


# ---------------------------------------------------------------------------
# Provider 协议
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """轻量 LLM 协议,避免对真实 provider 的硬依赖."""

    name: str

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        ...


class MockLLMProvider:
    """Mock provider — 不调用真实 LLM,返回基于规则的模板化解释.

    用于:
    - 离线/CI 环境跑通
    - 演示场景
    - 单测覆盖
    """

    name = "mock"

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        # 从 user prompt 抽出关键事实
        return _mock_generate_explain(user)


def _mock_generate_explain(user_prompt: str) -> dict[str, Any]:
    """从 user prompt 解析字段并生成模板化解释."""
    role_title = _extract(user_prompt, "Role Title") or "该岗位"
    candidate_title = _extract(user_prompt, "Candidate Title") or "候选人"
    years = _extract(user_prompt, "Experience Years") or "?"
    matched = _extract(user_prompt, "Skills Matched") or ""
    partial = _extract(user_prompt, "Skills Partial") or ""
    missing = _extract(user_prompt, "Skills Missing") or ""

    reasons: list[str] = []
    if matched:
        reasons.append(
            f"候选人具备岗位所需核心技能:{matched}"
        )
    if years and years != "?":
        reasons.append(f"{candidate_title}有 {years} 年相关经验,与岗位要求高度契合")
    if not reasons:
        reasons.append(f"{candidate_title}的画像与 {role_title} 整体方向一致")

    weak_points: list[str] = []
    if partial:
        weak_points.append(f"部分技能({partial})经验尚浅,需要进一步评估")
    if missing:
        weak_points.append(f"缺少 {missing} 等关键技能")

    # 反事实:用第一条 weak_point 给出 "如果……" 提示
    counterfactual: dict[str, Any] = {"if_have": "", "score_lift": 0.0}
    if missing:
        first_missing = missing.split(",")[0].strip()
        counterfactual = {
            "if_have": f"具备 {first_missing} 的实际项目经验",
            "score_lift": 0.15,
        }
    elif partial:
        first_partial = partial.split(",")[0].strip()
        counterfactual = {
            "if_have": f"深化 {first_partial} 的独立项目经历",
            "score_lift": 0.08,
        }
    else:
        counterfactual = {
            "if_have": "在近 6 个月内主导过类似规模项目",
            "score_lift": 0.05,
        }

    return {
        "reasons": reasons[:5],
        "weak_points": weak_points[:5],
        "counterfactual": counterfactual,
    }


def _extract(text: str, key: str) -> Optional[str]:
    """从 user_prompt 中抽取形如 'Key: value' 的字段."""
    m = re.search(rf"{re.escape(key)}\s*:\s*(.+)", text)
    return m.group(1).strip() if m else None


class OpenAIProvider:
    """OpenAI provider — 走真实 LLM,失败时回退到 mock."""

    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI  # type: ignore

            api_key = os.getenv("OPENAI_API_KEY", "")
            self._client = AsyncOpenAI(api_key=api_key)
        except Exception as exc:
            logger.warning(f"OpenAI client init failed: {exc}")
            self._client = None
        return self._client

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        client = self._ensure_client()
        if client is None:
            return _mock_generate_explain(user)
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            logger.warning(f"OpenAI call failed, falling back to mock: {exc}")
            return _mock_generate_explain(user)


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass
class MatchScore:
    """匹配分摘要."""

    overall: float = 0.0
    skill: float = 0.0
    semantic: float = 0.0
    experience: float = 0.0
    structured: float = 0.0
    confidence: str = "possible"
    skills_matched: list[str] = field(default_factory=list)
    skills_partial: list[str] = field(default_factory=list)
    skills_missing: list[str] = field(default_factory=list)


@dataclass
class CandidateBrief:
    id: str = ""
    title: str = ""
    seniority: str = ""
    years: float = 0.0
    skills: list[str] = field(default_factory=list)


@dataclass
class RoleBrief:
    id: str = ""
    title: str = ""
    seniority: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    team_size: int = 0


@dataclass
class Explanation:
    reasons: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)
    counterfactual: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasons": self.reasons,
            "weak_points": self.weak_points,
            "counterfactual": self.counterfactual,
        }


# ---------------------------------------------------------------------------
# System / User prompt 模板
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert recruitment consultant writing concise match explanations
for a UK recruitment platform. Your audience is non-technical recruiters and hiring managers.

Return ONLY valid JSON with this exact schema:
{
  "reasons": ["specific reason 1", "specific reason 2", ...],   // 2-5 items
  "weak_points": ["gap 1", "gap 2", ...],                     // 0-5 items, may be []
  "counterfactual": {
    "if_have": "one concrete thing that, if true, would lift the match",
    "score_lift": 0.10                                        // estimated absolute score gain, 0~0.3
  }
}

Rules:
- Plain UK English. No jargon. No raw scores.
- reasons must reference specific skills/years from the candidate.
- weak_points must be honest and constructive.
- counterfactual.if_have should be a single, actionable sentence.
- counterfactual.score_lift is your best estimate (rounded to 2 decimals).
- Never fabricate experience. Only use data provided.
"""

USER_PROMPT_TEMPLATE = """Generate a match explanation.

## Role
- Role Title: {role_title}
- Role Seniority: {role_seniority}
- Required Skills: {required_skills}
- Preferred Skills: {preferred_skills}
- Team Size: {team_size}

## Candidate
- Candidate Title: {candidate_title}
- Candidate Seniority: {candidate_seniority}
- Experience Years: {experience_years}

## Match Score
- Overall: {overall:.2f}
- Confidence: {confidence}
- Skill Score: {skill:.2f}
- Semantic Score: {semantic:.2f}
- Experience Score: {experience:.2f}

## Skills Matched
{matched}

## Skills Partial
{partial}

## Skills Missing
{missing}

Return JSON only.
"""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


class LLMExplainer:
    """LLM 可解释匹配服务."""

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        # provider 未指定时,默认走 mock (无环境依赖)
        self.provider: LLMProvider = provider or MockLLMProvider()
        self.model_version = f"explainer-llm-v1+{self.provider.name}"

    async def generate_explain(
        self,
        match_score: MatchScore | dict[str, Any],
        candidate: CandidateBrief | dict[str, Any],
        role: RoleBrief | dict[str, Any],
    ) -> Explanation:
        """一次性生成 reasons / weak_points / counterfactual."""
        ms = _as_match_score(match_score)
        cand = _as_candidate(candidate)
        rl = _as_role(role)

        prompt = USER_PROMPT_TEMPLATE.format(
            role_title=rl.title,
            role_seniority=rl.seniority or "Not specified",
            required_skills=", ".join(rl.required_skills) or "None",
            preferred_skills=", ".join(rl.preferred_skills) or "None",
            team_size=rl.team_size,
            candidate_title=cand.title,
            candidate_seniority=cand.seniority or "Not specified",
            experience_years=cand.years or 0.0,
            overall=ms.overall,
            confidence=ms.confidence,
            skill=ms.skill,
            semantic=ms.semantic,
            experience=ms.experience,
            matched=", ".join(ms.skills_matched) or "None",
            partial=", ".join(ms.skills_partial) or "None",
            missing=", ".join(ms.skills_missing) or "None",
        )

        result = await self.provider.chat_json(
            system=SYSTEM_PROMPT,
            user=prompt,
            temperature=0.3,
            max_tokens=700,
        )

        return _coerce(result, ms=ms, cand=cand, role=rl)


def _coerce(
    raw: dict[str, Any],
    *,
    ms: MatchScore,
    cand: CandidateBrief,
    role: RoleBrief,
) -> Explanation:
    """强制字段类型 + 容错."""
    reasons = [str(x) for x in (raw.get("reasons") or [])][:5]
    weak_points = [str(x) for x in (raw.get("weak_points") or [])][:5]

    cf = raw.get("counterfactual") or {}
    if not isinstance(cf, dict):
        cf = {}
    if_have = str(cf.get("if_have", "")).strip()
    try:
        score_lift = float(cf.get("score_lift", 0.0))
    except (TypeError, ValueError):
        score_lift = 0.0
    score_lift = max(0.0, min(0.5, round(score_lift, 3)))

    # 保底:若 LLM 没给 reasons,基于 matched/missing 生成
    if not reasons:
        reasons = _fallback_reasons(ms, cand, role)
    if not weak_points:
        weak_points = _fallback_weak_points(ms, role)
    if not if_have:
        if_have, score_lift = _fallback_counterfactual(ms, role)

    return Explanation(
        reasons=reasons,
        weak_points=weak_points,
        counterfactual={"if_have": if_have, "score_lift": score_lift},
    )


def _fallback_reasons(ms: MatchScore, cand: CandidateBrief, role: RoleBrief) -> list[str]:
    out: list[str] = []
    if ms.skills_matched:
        out.append(
            f"候选人具备 {', '.join(ms.skills_matched[:3])} 等核心技能,符合岗位核心要求"
        )
    if cand.years:
        out.append(f"{cand.title or '候选人'}有 {cand.years:.1f} 年相关经验")
    if not out:
        out.append("候选人画像与岗位画像存在显著重叠")
    return out


def _fallback_weak_points(ms: MatchScore, role: RoleBrief) -> list[str]:
    out: list[str] = []
    if ms.skills_missing:
        first = ms.skills_missing[0]
        out.append(f"候选人缺少 {first} 的相关经验")
    if role.team_size and role.team_size >= 5:
        out.append(f"岗位要求管理 {role.team_size} 人团队,候选人简历中未见明确管理履历")
    return out


def _fallback_counterfactual(ms: MatchScore, role: RoleBrief) -> tuple[str, float]:
    if ms.skills_missing:
        first = ms.skills_missing[0]
        return f"具备 {first} 的项目经验", 0.15
    if role.team_size >= 5:
        return "具有 5 人以上团队管理经验", 0.12
    return "在近 6 个月内主导过类似规模项目", 0.05


# ---------------------------------------------------------------------------
# 数据规范化辅助
# ---------------------------------------------------------------------------


def _as_match_score(obj: Any) -> MatchScore:
    if isinstance(obj, MatchScore):
        return obj
    return MatchScore(
        overall=float(obj.get("overall", 0.0)),
        skill=float(obj.get("skill", obj.get("structured_score", 0.0))),
        semantic=float(obj.get("semantic", obj.get("semantic_score", 0.0))),
        experience=float(obj.get("experience", obj.get("experience_score", 0.0))),
        structured=float(obj.get("structured", obj.get("structured_score", 0.0))),
        confidence=str(obj.get("confidence", "possible")),
        skills_matched=list(obj.get("skills_matched", []) or []),
        skills_partial=list(obj.get("skills_partial", []) or []),
        skills_missing=list(obj.get("skills_missing", []) or []),
    )


def _as_candidate(obj: Any) -> CandidateBrief:
    if isinstance(obj, CandidateBrief):
        return obj
    return CandidateBrief(
        id=str(obj.get("id", "")),
        title=str(obj.get("title", obj.get("current_title", ""))),
        seniority=str(obj.get("seniority", "")),
        years=float(obj.get("years", obj.get("experience_years", 0)) or 0),
        skills=list(obj.get("skills", []) or []),
    )


def _as_role(obj: Any) -> RoleBrief:
    if isinstance(obj, RoleBrief):
        return obj
    required = obj.get("required_skills", []) or []
    if required and isinstance(required[0], dict):
        required = [s.get("name", "") for s in required]
    preferred = obj.get("preferred_skills", []) or []
    if preferred and isinstance(preferred[0], dict):
        preferred = [s.get("name", "") for s in preferred]
    return RoleBrief(
        id=str(obj.get("id", "")),
        title=str(obj.get("title", "")),
        seniority=str(obj.get("seniority", "")),
        required_skills=[str(s) for s in required if s],
        preferred_skills=[str(s) for s in preferred if s],
        team_size=int(obj.get("team_size", 0) or 0),
    )