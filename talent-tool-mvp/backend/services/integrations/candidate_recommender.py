"""Candidate Recommender — T1304 + T1804 合作方 HR 推荐.

实现要点:
- 复用 v3.0 matching v2 ``MatchingEngine`` (skill_overlap + semantic + experience).
- 默认 limit=20;返回按 overall_score 排序的候选人列表,含 match 元数据.
- 不依赖 embedding(对没 embedding 的 role, 退化为纯 skill overlap 评分).
- 同时支持 ``recommend_for_role`` 和批量 ``recommend_for_active_roles``.
- T1804 新增:
    - ``bulk_seed_recommendations()`` — 从 seed JSONL 灌入合作方推荐记录
    - ``recommend_for_partner()`` — 给合作方 HR 推荐 top 5 候选人
    - ``partner_recommendation_stats()`` — 合作方推荐统计
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


@dataclass(slots=True)
class PartnerRecommendation:
    """T1804 — 合作方 HR 推荐给候选人的记录."""
    id: str
    partner_id: str
    hr_id: str
    hr_name: str
    candidate_id: str
    candidate_name: str
    role_id: str
    role_title: str
    overall_score: float
    confidence: str
    reasons: list[str]
    created_at: str

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
    # T1804 — 合作方 HR 推荐
    # ------------------------------------------------------------------
    async def recommend_for_partner(
        self,
        *,
        hr_id: str,
        hr_name: str,
        partner_id: str,
        role_id: str,
        limit: int = 5,
    ) -> list[PartnerRecommendation]:
        """给单个合作方 HR 推荐 top N 候选人(写入 partner_recommendations).

        返回 ``PartnerRecommendation`` 列表(含 ID,可写回 Supabase)。
        """
        cands = await self.recommend_to_employer(role_id, limit=limit)
        # 拉 role title
        role = await self._fetch_role(role_id) or {}
        role_title = role.get("title") or "(未知角色)"

        out: list[PartnerRecommendation] = []
        for c in cands:
            rec = PartnerRecommendation(
                id=str(uuid.uuid4()),
                partner_id=partner_id,
                hr_id=hr_id,
                hr_name=hr_name,
                candidate_id=c.candidate_id,
                candidate_name=c.full_name or "(匿名)",
                role_id=role_id,
                role_title=role_title,
                overall_score=c.overall_score,
                confidence=c.confidence,
                reasons=list(c.reasons),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            out.append(rec)
        return out

    async def bulk_seed_recommendations(
        self, jsonl_path: str | Path
    ) -> list[PartnerRecommendation]:
        """从 seed JSONL 灌入合作方推荐记录(返回内存对象列表)。"""
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning("[recommender] bulk_seed: file not found %s", path)
            return []

        out: list[PartnerRecommendation] = []
        with path.open("r", encoding="utf-8") as f:
            for ln, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[recommender] JSONL parse fail line %d: %s", ln, exc)
                    continue
                out.append(
                    PartnerRecommendation(
                        id=str(row.get("id") or uuid.uuid4()),
                        partner_id=str(row["partner_id"]),
                        hr_id=str(row["hr_id"]),
                        hr_name=str(row.get("hr_name", "")),
                        candidate_id=str(row["candidate_id"]),
                        candidate_name=str(row.get("candidate_name", "")),
                        role_id=str(row["role_id"]),
                        role_title=str(row.get("role_title", "")),
                        overall_score=float(row.get("overall_score", 0.0)),
                        confidence=str(row.get("confidence", "moderate")),
                        reasons=list(row.get("reasons") or []),
                        created_at=str(
                            row.get("created_at")
                            or datetime.now(timezone.utc).isoformat()
                        ),
                    )
                )
        logger.info("[recommender] bulk_seed: %d records from %s", len(out), path.name)
        return out

    def partner_recommendation_stats(
        self, recs: list[PartnerRecommendation]
    ) -> dict[str, Any]:
        """统计合作方推荐分布 (for /api/recommendations/partner/stats)."""
        if not recs:
            return {"total": 0}

        by_hr: dict[str, int] = {}
        by_conf: dict[str, int] = {}
        score_sum = 0.0
        for r in recs:
            by_hr[r.hr_id] = by_hr.get(r.hr_id, 0) + 1
            by_conf[r.confidence] = by_conf.get(r.confidence, 0) + 1
            score_sum += r.overall_score
        return {
            "total": len(recs),
            "unique_hrs": len(by_hr),
            "by_confidence": by_conf,
            "avg_score": round(score_sum / len(recs), 4),
            "by_hr": dict(sorted(by_hr.items(), key=lambda x: -x[1])),
        }

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
    "PartnerRecommendation",
    "RecommendedCandidate",
]