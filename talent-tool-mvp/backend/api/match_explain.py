"""T901 — 匹配可解释性 API.

GET  /api/match/{id}/explain         — reasons + weak_points
GET  /api/match/{id}/counterfactual  — 反事实匹配 (如果……会更匹配)
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from matching.explainer_llm import (
    LLMExplainer,
    MockLLMProvider,
    OpenAIProvider,
)

logger = logging.getLogger("recruittech.api.match_explain")
router = APIRouter()


# ---------------------------------------------------------------------------
# Provider 单例
# ---------------------------------------------------------------------------

_default_explainer: Optional[LLMExplainer] = None


def _get_explainer() -> LLMExplainer:
    """选择 provider 优先级:OpenAI -> Mock."""
    global _default_explainer
    if _default_explainer is not None:
        return _default_explainer
    import os

    if os.getenv("OPENAI_API_KEY"):
        try:
            _default_explainer = LLMExplainer(provider=OpenAIProvider())
            logger.info("LLMExplainer using OpenAIProvider")
        except Exception as exc:
            logger.warning(f"OpenAIProvider init failed, fallback to mock: {exc}")
            _default_explainer = LLMExplainer(provider=MockLLMProvider())
    else:
        logger.info("LLMExplainer using MockLLMProvider (no OPENAI_API_KEY)")
        _default_explainer = LLMExplainer(provider=MockLLMProvider())
    return _default_explainer


def reset_explainer_for_tests(provider=None) -> LLMExplainer:
    """重置 provider(测试用)."""
    global _default_explainer
    _default_explainer = LLMExplainer(provider=provider or MockLLMProvider())
    return _default_explainer


# ---------------------------------------------------------------------------
# 辅助函数: 从 supabase 抽取 match/candidate/role 摘要
# ---------------------------------------------------------------------------


def _load_match_bundle(supabase, match_id: str) -> dict[str, Any]:
    """一次性加载 match + candidate + role,组装成 LLMExplainer 输入."""
    match_resp = (
        supabase.table("matches")
        .select("*")
        .eq("id", match_id)
        .maybe_single()
        .execute()
    )
    if not match_resp.data:
        raise HTTPException(status_code=404, detail="Match not found")
    match = match_resp.data

    cand_resp = (
        supabase.table("candidates")
        .select("*")
        .eq("id", match["candidate_id"])
        .maybe_single()
        .execute()
    )
    candidate = cand_resp.data or {}

    role_resp = (
        supabase.table("roles")
        .select("*")
        .eq("id", match["role_id"])
        .maybe_single()
        .execute()
    )
    role = role_resp.data or {}

    skill_overlap = match.get("skill_overlap") or []
    matched = [s.get("skill_name") for s in skill_overlap if s.get("status") == "matched"]
    partial = [s.get("skill_name") for s in skill_overlap if s.get("status") == "partial"]
    missing = [s.get("skill_name") for s in skill_overlap if s.get("status") == "missing"]

    candidate_skills = [
        s.get("name") for s in (candidate.get("skills") or []) if isinstance(s, dict)
    ]
    experience = candidate.get("experience") or []
    cand_title = ""
    cand_seniority = candidate.get("seniority", "")
    years = 0.0
    if experience and isinstance(experience[0], dict):
        cand_title = experience[0].get("title", "") or ""
        total_months = sum(
            (e.get("duration_months") or 0) for e in experience if isinstance(e, dict)
        )
        years = round(total_months / 12, 1)

    team_size = role.get("team_size") or 0
    if not team_size and isinstance(role.get("metadata"), dict):
        team_size = role["metadata"].get("team_size", 0)

    return {
        "match_score": {
            "overall": float(match.get("overall_score", 0.0)),
            "skill": float(
                (match.get("scoring_breakdown") or {}).get("components", {}).get(
                    "structured_score", 0.0
                )
            ),
            "semantic": float(match.get("semantic_score", 0.0)),
            "experience": float(
                (match.get("scoring_breakdown") or {}).get("components", {}).get(
                    "experience_fit_raw", 0.0
                )
            ),
            "confidence": match.get("confidence", "possible"),
            "skills_matched": matched,
            "skills_partial": partial,
            "skills_missing": missing,
        },
        "candidate": {
            "id": str(candidate.get("id", "")),
            "title": cand_title,
            "seniority": cand_seniority,
            "years": years,
            "skills": candidate_skills,
        },
        "role": {
            "id": str(role.get("id", "")),
            "title": role.get("title", ""),
            "seniority": role.get("seniority", ""),
            "required_skills": role.get("required_skills", []) or [],
            "preferred_skills": role.get("preferred_skills", []) or [],
            "team_size": team_size,
        },
    }


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/{match_id}/explain")
async def get_match_explain(
    match_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """获取匹配自然语言解释."""
    supabase = get_supabase_admin()
    bundle = _load_match_bundle(supabase, str(match_id))
    explainer = _get_explainer()
    explanation = await explainer.generate_explain(
        bundle["match_score"], bundle["candidate"], bundle["role"]
    )
    return {
        "match_id": str(match_id),
        "reasons": explanation.reasons,
        "weak_points": explanation.weak_points,
        "model_version": explainer.model_version,
    }


@router.get("/{match_id}/counterfactual")
async def get_match_counterfactual(
    match_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """获取反事实匹配 (如果……会更匹配)."""
    supabase = get_supabase_admin()
    bundle = _load_match_bundle(supabase, str(match_id))
    explainer = _get_explainer()
    explanation = await explainer.generate_explain(
        bundle["match_score"], bundle["candidate"], bundle["role"]
    )
    cf = explanation.counterfactual or {}
    return {
        "match_id": str(match_id),
        "if_have": cf.get("if_have", ""),
        "score_lift": cf.get("score_lift", 0.0),
        "model_version": explainer.model_version,
    }