"""T3002: AI 主动 Sourcing API.

Endpoints:
    POST /api/sourcing/search              — 输入岗位画像, 输出打分候选人 (目标 100)
    GET  /api/sourcing/candidates/{id}     — 候选人详情 (5 维评分 + 理由)
    POST /api/sourcing/candidates/{id}/invite — 一键邀请面试 (记录意向)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from providers.sourcing import JobProfile
from services.platform.sourcing_agent import get_sourcing_agent

logger = logging.getLogger("recruittech.api.sourcing")
router = APIRouter()


class SearchRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    skills: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    seniority: Optional[str] = Field(None, description="junior | mid | senior | staff")
    min_years: int = Field(0, ge=0, le=40)
    keywords: list[str] = Field(default_factory=list)
    target: int = Field(100, ge=1, le=200)


@router.post("/search")
async def search_candidates(
    body: SearchRequest,
    _user: CurrentUser = Depends(get_current_user),
):
    """一键启动主动 sourcing: 输入岗位, 输出候选人 + 匹配分。"""
    profile = JobProfile(
        title=body.title,
        skills=body.skills,
        location=body.location,
        seniority=body.seniority,
        min_years=body.min_years,
        keywords=body.keywords,
    )
    agent = get_sourcing_agent()
    scored = await agent.source(profile, target=body.target)
    return {
        "job": {"title": body.title, "location": body.location, "skills": body.skills},
        "total": len(scored),
        "candidates": [s.to_dict() for s in scored],
    }


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """候选人详情 (需先经 /search 产出)。"""
    agent = get_sourcing_agent()
    scored = agent.get_candidate(candidate_id)
    if scored is None:
        raise HTTPException(status_code=404, detail=f"candidate not found: {candidate_id}")
    return scored.to_dict()


class InviteRequest(BaseModel):
    message: Optional[str] = None
    job_title: Optional[str] = None


@router.post("/candidates/{candidate_id}/invite")
async def invite_candidate(
    candidate_id: str,
    body: InviteRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """一键邀请面试 (记录邀约意向)。"""
    agent = get_sourcing_agent()
    scored = agent.get_candidate(candidate_id)
    if scored is None:
        raise HTTPException(status_code=404, detail=f"candidate not found: {candidate_id}")
    logger.info(
        "sourcing invite by=%s candidate=%s job=%s",
        user.email,
        candidate_id,
        body.job_title,
    )
    return {
        "status": "invited",
        "candidate_id": candidate_id,
        "candidate_name": scored.candidate.name,
        "job_title": body.job_title,
        "message": body.message or "我们对您的背景很感兴趣, 诚邀您参加面试。",
    }
