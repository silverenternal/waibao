"""双向匹配 - 求职者 ↔ 用人单位 双向打分.

需求 3: 求职者与用人单位相互适配.

算法:
- candidate_to_role: 求职者对岗位的契合度(从求职者画像评估岗位吸引力)
- role_to_candidate: 岗位对求职者的契合度(从岗位画像评估求职者匹配度)
- harmonic_score: 调和均值 (2*a*b / (a+b))
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from agents.toolkit import llm_call
from agents.runtime import LLMClient

logger = logging.getLogger("recruittech.matching.two_way")


@dataclass
class TwoWayScore:
    candidate_to_role: float   # 0~1
    role_to_candidate: float   # 0~1
    harmonic_score: float      # 调和值
    candidate_perspective: dict
    employer_perspective: dict


def harmonic(a: float, b: float, eps: float = 1e-6) -> float:
    """调和均值."""
    return 2 * a * b / (a + b + eps)


async def compute_two_way(
    candidate_profile: dict,
    role_profile: dict,
    candidate_needs: dict,
    role_needs: dict,
    llm: Optional[LLMClient] = None,
) -> TwoWayScore:
    """计算双向契合度."""
    # 1. 候选人对岗位的契合度:
    #    - 求职者画像的偏好 vs 岗位画像
    #    - 真实需求满足度
    candidate_to_role = _score_candidate_view(candidate_profile, candidate_needs, role_profile)

    # 2. 岗位对候选人的契合度:
    #    - 岗位画像要求 vs 求职者画像
    role_to_candidate = _score_employer_view(role_profile, role_needs, candidate_profile)

    # 3. 用 LLM 优化 + 生成双方视角解释
    llm_client = llm or LLMClient()
    try:
        from agents.toolkit import llm_call as _llm_call
        raw = await _llm_call(
            llm_client,
            f"求职者视角评分: {candidate_to_role:.2f}\n用人方视角评分: {role_to_candidate:.2f}",
            system="基于已有评分,生成双方视角的优劣分析(JSON)。",
            json_mode=True,
        )
        perspectives = json.loads(raw)
    except Exception:
        perspectives = {
            "candidate_view": "请结合岗位详情评估",
            "employer_view": "请结合候选人详情评估",
        }

    return TwoWayScore(
        candidate_to_role=candidate_to_role,
        role_to_candidate=role_to_candidate,
        harmonic_score=harmonic(candidate_to_role, role_to_candidate),
        candidate_perspective=perspectives,
        employer_perspective=perspectives,
    )


def _score_candidate_view(profile: dict, needs: dict, role: dict) -> float:
    """求职者视角: 岗位满足求职者需求的程度."""
    score = 0.5
    role_skills = {s.get("name") for s in role.get("required_skills", []) if isinstance(s, dict)}
    cand_skills = {s.get("name") for s in profile.get("skills", []) if isinstance(s, dict)}
    if role_skills:
        # 技能匹配只是其中一面,主要看求职者需求
        overlap = len(role_skills & cand_skills) / max(1, len(role_skills))
        score += overlap * 0.1

    # 真实需求
    must_haves = set(needs.get("must_haves", []))
    role_str = json.dumps(role, ensure_ascii=False)
    matched_must = sum(1 for mh in must_haves if mh in role_str)
    if must_haves:
        score += (matched_must / len(must_haves)) * 0.3

    # 价值观/兴趣匹配
    interests = set(profile.get("interests", []))
    role_culture = role.get("culture", "")
    if interests and any(i in role_culture for i in interests):
        score += 0.1

    return min(1.0, max(0.0, score))


def _score_employer_view(role: dict, role_needs: dict, profile: dict) -> float:
    """用人方视角: 候选人满足岗位需求的程度."""
    score = 0.4

    # 硬技能匹配
    role_skills = {s.get("name") for s in role.get("required_skills", []) if isinstance(s, dict)}
    cand_skills = {s.get("name") for s in profile.get("skills", []) if isinstance(s, dict)}
    if role_skills:
        overlap = len(role_skills & cand_skills) / max(1, len(role_skills))
        score += overlap * 0.35

    # 经验
    min_years = role.get("min_experience_years", 0)
    cand_years = profile.get("experience_years", 0)
    if min_years:
        score += min(1.0, cand_years / min_years) * 0.15

    # 隐性需求(文化/价值观/潜力)
    role_implicit = role_needs.get("implicit_requirements", [])
    if role_implicit:
        # 简单文本匹配
        profile_text = json.dumps(profile, ensure_ascii=False)
        matches = sum(1 for r in role_implicit if any(kw in profile_text for kw in r.split()))
        score += min(1.0, matches / max(1, len(role_implicit))) * 0.1

    return min(1.0, max(0.0, score))


async def persist_two_way_match(
    candidate_id: UUID,
    role_id: UUID,
    score: TwoWayScore,
    supabase,
) -> dict:
    """写入 two_way_matches 表."""
    record = {
        "id": str(uuid4()),
        "candidate_id": str(candidate_id),
        "role_id": str(role_id),
        "candidate_to_role": score.candidate_to_role,
        "role_to_candidate": score.role_to_candidate,
        "harmonic_score": score.harmonic_score,
        "candidate_perspective": score.candidate_perspective,
        "employer_perspective": score.employer_perspective,
        "status": "proposed",
    }
    result = supabase.table("two_way_matches").upsert(
        record, on_conflict="candidate_id,role_id"
    ).execute()
    return result.data[0] if result.data else record


async def get_top_matches_for_candidate(
    candidate_id: UUID,
    limit: int = 10,
    supabase=None,
) -> list[dict]:
    """给求职者推荐 Top N 岗位 (按 harmonic_score 排序)."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    result = (
        supabase.table("two_way_matches")
        .select("*, role:roles(title, organisation_id)")
        .eq("candidate_id", str(candidate_id))
        .order("harmonic_score", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def get_top_candidates_for_role(
    role_id: UUID,
    limit: int = 20,
    supabase=None,
) -> list[dict]:
    """给 HR 推荐 Top N 候选人."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    result = (
        supabase.table("two_way_matches")
        .select("*, candidate:candidates(first_name, last_name, skills)")
        .eq("role_id", str(role_id))
        .order("harmonic_score", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []