"""Candidate Recommender — T1304 主动给雇主推荐候选人.

实现要点:
- 复用 v3.0 matching v2 ``MatchingEngine`` (skill_overlap + semantic + experience).
- 默认 limit=20;返回按 overall_score 排序的候选人列表,含 match 元数据.
- 不依赖 embedding(对没 embedding 的 role, 退化为纯 skill overlap 评分).
- 同时支持 ``recommend_for_role`` 和批量 ``recommend_for_active_roles``.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from contracts.shared import ExtractedSkill, RequiredSkill, SeniorityLevel

logger = logging.getLogger("recruittech.services.candidate_recommender")


@dataclass(slots=True)
class RecommendedCandidate:
    """推荐候选人."""

    candidate_id: str
    full_name: str
    headline: str
    city: str
    seniority: str
    skills: list[str]
    years_experience: float
    overall_score: float
    structured_score: float
    semantic_score: float
    experience_score: float
    confidence: str
    reasons: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 级别序: 用于经验近似匹配
_SENIORITY_RANK = {
    SeniorityLevel.junior: 1,
    SeniorityLevel.mid: 2,
    SeniorityLevel.senior: 3,
    SeniorityLevel.lead: 4,
    SeniorityLevel.principal: 5,
}


class CandidateRecommender:
    """基于 v3.0 matching 算法的候选人推荐器.

    输入: role (dict) + supabase client.
    输出: 排序后的 ``RecommendedCandidate`` 列表.
    """

    def __init__(self, supabase: Any | None = None) -> None:
        self.supabase = supabase

    async def recommend_to_employer(
        self, role_id: str, *, limit: int = 20
    ) -> list[RecommendedCandidate]:
        """对单个 role 推荐候选人."""
        role = await self._fetch_role(role_id)
        if role is None:
            return []
        candidates = await self._fetch_candidates(role=role, limit=max(limit * 3, 60))
        scored = [self._score_candidate(role, c) for c in candidates]
        scored = [s for s in scored if s is not None]
        scored.sort(key=lambda r: r.overall_score, reverse=True)
        return scored[:limit]

    async def recommend_for_active_roles(
        self, *, role_limit: int = 50, candidates_per_role: int = 20
    ) -> dict[str, list[RecommendedCandidate]]:
        """批量: 对所有 active role 各返回 top N 推荐."""
        if self.supabase is None:
            return {}
        try:
            res = (
                self.supabase.table("roles")
                .select("id")
                .eq("status", "active")
                .limit(role_limit)
                .execute()
            )
            roles = [r["id"] for r in (res.data or [])]
        except Exception as exc:  # noqa: BLE001
            logger.debug("[recommender] role fetch failed: %s", exc)
            return {}

        out: dict[str, list[RecommendedCandidate]] = {}
        for rid in roles:
            out[rid] = await self.recommend_to_employer(
                rid, limit=candidates_per_role
            )
        return out

    # ------------------------------------------------------------------
    # 内部 — 拉取
    # ------------------------------------------------------------------
    async def _fetch_role(self, role_id: str) -> dict[str, Any] | None:
        if self.supabase is None:
            return None
        try:
            r = (
                self.supabase.table("roles")
                .select(
                    "id,title,required_skills,preferred_skills,seniority,"
                    "remote_policy,city,salary_min,salary_max,currency"
                )
                .eq("id", role_id)
                .single()
                .execute()
            )
            return r.data or None
        except Exception as exc:  # noqa: BLE001
            logger.debug("[recommender] role fetch failed: %s", exc)
            return None

    async def _fetch_candidates(
        self, *, role: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        if self.supabase is None:
            return []
        try:
            res = (
                self.supabase.table("candidates")
                .select(
                    "id,full_name,headline,city,seniority,extracted_skills,"
                    "years_experience,availability_status"
                )
                .eq("status", "active")
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as exc:  # noqa: BLE001
            logger.debug("[recommender] candidate fetch failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 内部 — 评分
    # ------------------------------------------------------------------
    def _score_candidate(
        self, role: dict[str, Any], cand: dict[str, Any]
    ) -> RecommendedCandidate | None:
        # ---- skill overlap ----
        req_skills_raw = role.get("required_skills") or []
        pref_skills_raw = role.get("preferred_skills") or []
        req_skills = [
            RequiredSkill(**s) if isinstance(s, dict) else RequiredSkill(name=str(s))
            for s in req_skills_raw
        ]
        pref_skills = [
            RequiredSkill(**s) if isinstance(s, dict) else RequiredSkill(name=str(s))
            for s in pref_skills_raw
        ]
        cand_skills_raw = cand.get("extracted_skills") or []
        cand_skills: list[ExtractedSkill] = []
        for s in cand_skills_raw:
            if isinstance(s, dict):
                cand_skills.append(
                    ExtractedSkill(
                        name=s.get("name", ""),
                        years=float(s.get("years") or 0) or None,
                        confidence=float(s.get("confidence") or 1.0),
                    )
                )
            elif isinstance(s, str):
                cand_skills.append(ExtractedSkill(name=s))

        skill_score, overlap, missing = _compute_skill_overlap(
            cand_skills, req_skills, pref_skills
        )

        # ---- experience fit ----
        years = float(cand.get("years_experience") or 0)
        cand_sen = _parse_seniority(cand.get("seniority"))
        role_sen = _parse_seniority(role.get("seniority"))
        experience_score = _experience_fit(cand_sen, role_sen, int(years))

        # ---- semantic (无 embedding 时退化为 skill 派生) ----
        semantic_score = min(1.0, skill_score * 0.85 + 0.05 * len(overlap))

        # ---- composite (40/35/25 — 与 v3.0 matching 一致) ----
        overall = round(
            0.40 * skill_score + 0.35 * semantic_score + 0.25 * experience_score,
            4,
        )

        # ---- confidence bucket ----
        if overall >= 0.75:
            confidence = "strong"
        elif overall >= 0.5:
            confidence = "good"
        else:
            confidence = "possible"

        return RecommendedCandidate(
            candidate_id=str(cand.get("id") or uuid.uuid4()),
            full_name=cand.get("full_name", "") or "",
            headline=cand.get("headline", "") or "",
            city=cand.get("city", "") or "",
            seniority=str(cand.get("seniority") or ""),
            skills=[s.name for s in cand_skills],
            years_experience=round(years, 1),
            overall_score=overall,
            structured_score=round(skill_score, 4),
            semantic_score=round(semantic_score, 4),
            experience_score=round(experience_score, 4),
            confidence=confidence,
            reasons=_build_reasons(overlap, role, cand_sen, role_sen, years),
            missing_skills=missing,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_seniority(value: Any) -> SeniorityLevel | None:
    if value is None or value == "":
        return None
    if isinstance(value, SeniorityLevel):
        return value
    try:
        return SeniorityLevel(str(value).strip().lower())
    except ValueError:
        return None


def _compute_skill_overlap(
    candidate_skills: list[ExtractedSkill],
    required: list[RequiredSkill],
    preferred: list[RequiredSkill],
) -> tuple[float, list[str], list[str]]:
    """返回 (score, matched_skill_names, missing_skill_names)."""
    c_map = {s.name.lower().strip(): s for s in candidate_skills if s.name}
    matched: list[str] = []
    missing: list[str] = []

    earned = 0.0
    total = 0.0
    for skill in required:
        weight = 2.0
        total += weight
        key = skill.name.lower().strip()
        m = c_map.get(key)
        if m is None:
            missing.append(skill.name)
            continue
        if skill.min_years and m.years:
            if m.years >= skill.min_years:
                earned += weight
                matched.append(skill.name)
            else:
                ratio = m.years / skill.min_years
                earned += weight * min(ratio, 1.0) * 0.7
                matched.append(skill.name)
        else:
            earned += weight
            matched.append(skill.name)

    for skill in preferred:
        weight = 1.0
        total += weight
        key = skill.name.lower().strip()
        if key in c_map:
            earned += weight
            matched.append(skill.name)

    score = (earned / total) if total > 0 else 0.0
    return min(1.0, score), matched, missing


def _experience_fit(
    cand_sen: SeniorityLevel | None,
    role_sen: SeniorityLevel | None,
    years: int,
) -> float:
    """0~1 经验匹配分."""
    if role_sen is None:
        return 0.5  # role 没要求就给中间分

    role_rank = _SENIORITY_RANK.get(role_sen, 3)
    cand_rank = _SENIORITY_RANK.get(cand_sen, 3) if cand_sen else max(1, min(5, years // 3 + 1))

    diff = cand_rank - role_rank
    if diff == 0:
        base = 0.95
    elif diff == 1:
        base = 0.8  # over-qualified
    elif diff == -1:
        base = 0.7  # slightly under
    elif diff > 1:
        base = 0.55
    else:
        base = 0.45
    # 经验年数微调
    if years >= role_rank * 3:
        base = min(1.0, base + 0.05)
    return max(0.0, min(1.0, base))


def _build_reasons(
    matched: list[str],
    role: dict[str, Any],
    cand_sen: SeniorityLevel | None,
    role_sen: SeniorityLevel | None,
    years: float,
) -> list[str]:
    reasons: list[str] = []
    if matched:
        reasons.append(f"matched {len(matched)} skills: {', '.join(matched[:5])}")
    if cand_sen and role_sen and cand_sen == role_sen:
        reasons.append(f"seniority matches ({cand_sen.value})")
    if years >= 3:
        reasons.append(f"{int(years)}y experience")
    return reasons


__all__ = [
    "CandidateRecommender",
    "RecommendedCandidate",
]