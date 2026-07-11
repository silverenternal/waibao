"""学习资源 API (T607).

路径:
    GET /api/learning/search?skill=xxx&limit=20
    GET /api/learning/recommend?user_id=xxx&gap_skills=python,fastapi
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, get_current_user
from services.learning_resources import get_learning_resources_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_dict(r: Any) -> dict[str, Any]:
    return {
        "title": r.title,
        "provider": r.provider,
        "url": r.url,
        "duration_hours": r.duration_hours,
        "level": r.level,
        "rating": r.rating,
        "skill_tags": r.skill_tags,
        "description": r.description,
        "price": r.price,
        "language": r.language,
        "source": r.source,
    }


@router.get("/search")
async def search_resources(
    skill: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=100),
    _: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """按技能搜索学习资源."""
    svc = get_learning_resources_service()
    rows = await svc.search(skill, limit=limit)
    return {
        "skill": skill,
        "total": len(rows),
        "items": [_to_dict(r) for r in rows],
    }


@router.get("/recommend")
async def recommend_resources(
    user_id: str | None = Query(None),
    gap_skills: str = Query(..., description="逗号分隔的 gap 技能"),
    limit: int = Query(20, ge=1, le=100),
    _: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """基于 gap skills 推荐学习资源."""
    skills = [s.strip() for s in gap_skills.split(",") if s.strip()]
    if not skills:
        return {"user_id": user_id, "gap_skills": [], "items": [], "total": 0}
    svc = get_learning_resources_service()
    rows = await svc.recommend(skills, overall_limit=limit)
    return {
        "user_id": user_id,
        "gap_skills": skills,
        "total": len(rows),
        "items": [_to_dict(r) for r in rows],
    }


__all__ = ["router"]