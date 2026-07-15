"""T6103 — Recruitment Marketplace REST API.

Two-sided talent/job marketplace. Public browse (no auth) for the pool
listings and job cards; the full talent resume (with contact info) is
gated to authenticated employer/admin users only.

Routes (mounted under ``/api/talent-market``):

* ``GET /api/talent-market/stats``                   market headline numbers
* ``GET /api/talent-market/recommendations``         latest match suggestions
* ``GET /api/talent-market/talents``                 talent pool (paginated + filtered)
* ``GET /api/talent-market/talents/{talent_id}``     talent detail (employer sees full)
* ``GET /api/talent-market/jobs``                    job pool (paginated + filtered)
* ``GET /api/talent-market/jobs/{job_id}``           job card detail

PII note: the talent list/detail responses hide contact fields by
default; full resume + contact is only included when the caller is an
authenticated ``client`` (employer) or ``admin``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import PaginatedResponse
from contracts.shared import UserRole
from services.marketplace.talent_market import (
    JobCard,
    JobDetail,
    MatchRecommendation,
    TalentCard,
    TalentDetail,
    TalentMarketService,
    get_service,
)

logger = logging.getLogger("recruittech.api.talent_market")
router = APIRouter()


def _optional_user_factory():
    """Return a dependency that resolves the user OR None (never 401)."""
    from fastapi import Header
    from api.auth import decode_supabase_jwt

    async def _dep(authorization: Optional[str] = Header(default=None)):
        if not authorization:
            return None
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            return None
        try:
            payload = decode_supabase_jwt(token)
            from api.auth import _payload_to_user

            return _payload_to_user(payload)
        except Exception:  # noqa: BLE001 — anonymous browse allowed
            return None

    return _dep


_optional_user = _optional_user_factory()


def _can_see_full_resume(user: Optional[CurrentUser]) -> bool:
    return user is not None and user.role in (UserRole.client, UserRole.admin)


def _is_seeker(user: Optional[CurrentUser]) -> bool:
    return user is not None and user.role in (UserRole.talent_partner, UserRole.admin)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class MarketStats(BaseModel):
    talents_total: int
    talents_online: int
    jobs_total: int
    companies_total: int
    matches_total: int


class TalentCardOut(BaseModel):
    id: str
    name: str
    title: str
    city: str
    skills: list[str]
    seniority: Optional[str] = None
    education: Optional[str] = None
    salary_min_k: Optional[int] = None
    salary_max_k: Optional[int] = None
    experience_years: Optional[int] = None
    availability: Optional[str] = None
    match_score: int
    online: bool
    avatar_color: str


class TalentDetailOut(TalentCardOut):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    summary: Optional[str] = None
    industries: list[str] = Field(default_factory=list)


class JobCardOut(BaseModel):
    id: str
    company: str
    company_industry: str
    title: str
    city: str
    salary_min_k: Optional[int] = None
    salary_max_k: Optional[int] = None
    skills_required: list[str]
    skills_preferred: list[str]
    seniority: Optional[str] = None
    education: Optional[str] = None
    experience_years: Optional[str] = None
    remote_policy: str
    match_score: int
    posted_at: str
    certificates_required: list[str] = Field(default_factory=list)


class JobDetailOut(JobCardOut):
    description: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    headcount: int = 1
    # T6107: 岗位卡 4 部分 — 加分项 + 边界
    nice_to_have: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    work_schedule: str = ""
    travel_required: str = ""


class MatchRecommendationOut(BaseModel):
    id: str
    talent_id: str
    talent_name: str
    talent_title: str
    job_id: str
    job_title: str
    company: str
    score: int
    reasons: list[str]


def _talent_card_out(t: TalentCard) -> TalentCardOut:
    return TalentCardOut(
        id=t.id, name=t.name, title=t.title, city=t.city, skills=t.skills,
        seniority=t.seniority, education=t.education,
        salary_min_k=t.salary_min_k, salary_max_k=t.salary_max_k,
        experience_years=t.experience_years, availability=t.availability,
        match_score=t.match_score, online=t.online, avatar_color=t.avatar_color,
    )


def _talent_detail_out(t: TalentCard) -> TalentDetailOut:
    base = _talent_card_out(t).model_dump()
    if isinstance(t, TalentDetail):
        base.update(
            full_name=t.full_name, email=t.email, phone=t.phone,
            linkedin_url=t.linkedin_url, summary=t.summary,
            industries=t.industries,
        )
    return TalentDetailOut(**base)


def _job_card_out(j: JobCard) -> JobCardOut:
    return JobCardOut(
        id=j.id, company=j.company, company_industry=j.company_industry,
        title=j.title, city=j.city, salary_min_k=j.salary_min_k,
        salary_max_k=j.salary_max_k, skills_required=j.skills_required,
        skills_preferred=j.skills_preferred, seniority=j.seniority,
        education=j.education, experience_years=j.experience_years,
        remote_policy=j.remote_policy, match_score=j.match_score,
        posted_at=j.posted_at,
        certificates_required=getattr(j, "certificates_required", []),
    )


def _job_detail_out(j: JobCard) -> JobDetailOut:
    base = _job_card_out(j).model_dump()
    if isinstance(j, JobDetail):
        base.update(
            description=j.description, responsibilities=j.responsibilities,
            requirements=j.requirements, benefits=j.benefits,
            headcount=j.headcount,
            nice_to_have=j.nice_to_have, boundaries=j.boundaries,
            work_schedule=j.work_schedule, travel_required=j.travel_required,
        )
    return JobDetailOut(**base)


def _match_out(m: MatchRecommendation) -> MatchRecommendationOut:
    return MatchRecommendationOut(
        id=m.id, talent_id=m.talent_id, talent_name=m.talent_name,
        talent_title=m.talent_title, job_id=m.job_id, job_title=m.job_title,
        company=m.company, score=m.score, reasons=m.reasons,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=MarketStats, tags=["talent-market"])
async def get_stats(
    svc: TalentMarketService = Depends(get_service),
) -> MarketStats:
    """Market headline statistics."""
    return MarketStats(**svc.stats())


@router.get(
    "/recommendations",
    response_model=list[MatchRecommendationOut],
    tags=["talent-market"],
)
async def get_recommendations(
    limit: int = Query(default=5, ge=1, le=20),
    svc: TalentMarketService = Depends(get_service),
) -> list[MatchRecommendationOut]:
    """Latest talent↔job match recommendations (homepage feed)."""
    return [_match_out(m) for m in svc.recommendations(limit=limit)]


@router.get("/talents", response_model=PaginatedResponse, tags=["talent-market"])
async def list_talents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    keyword: Optional[str] = Query(default=None),
    position: Optional[str] = Query(default=None),
    skill: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    salary_min: Optional[int] = Query(default=None, ge=0),
    salary_max: Optional[int] = Query(default=None, ge=0),
    education: Optional[str] = Query(default=None),
    svc: TalentMarketService = Depends(get_service),
) -> PaginatedResponse:
    """Talent pool — paginated + filtered. Returns anonymous cards."""
    cards, total = svc.list_talents(
        page=page, page_size=page_size, keyword=keyword, position=position,
        skill=skill, city=city, salary_min=salary_min, salary_max=salary_max,
        education=education,
    )
    return PaginatedResponse(
        data=[_talent_card_out(c).model_dump(mode="json") for c in cards],
        total=total, page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get(
    "/talents/{talent_id}",
    response_model=TalentDetailOut,
    tags=["talent-market"],
)
async def get_talent(
    talent_id: str,
    user: Optional[CurrentUser] = Depends(_optional_user),
    svc: TalentMarketService = Depends(get_service),
) -> TalentDetailOut:
    """Talent detail.

    Anonymous/seeker callers receive a masked summary; authenticated
    employer/admin callers receive the full resume + contact info.
    """
    full = _can_see_full_resume(user)
    talent = svc.get_talent(talent_id, full=full)
    if talent is None:
        raise HTTPException(status_code=404, detail="Talent not found")
    return _talent_detail_out(talent)


@router.get("/jobs", response_model=PaginatedResponse, tags=["talent-market"])
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    keyword: Optional[str] = Query(default=None),
    position: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    salary_min: Optional[int] = Query(default=None, ge=0),
    salary_max: Optional[int] = Query(default=None, ge=0),
    svc: TalentMarketService = Depends(get_service),
) -> PaginatedResponse:
    """Job pool — paginated + filtered."""
    cards, total = svc.list_jobs(
        page=page, page_size=page_size, keyword=keyword, position=position,
        city=city, salary_min=salary_min, salary_max=salary_max,
    )
    return PaginatedResponse(
        data=[_job_card_out(c).model_dump(mode="json") for c in cards],
        total=total, page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailOut,
    tags=["talent-market"],
)
async def get_job(
    job_id: str,
    svc: TalentMarketService = Depends(get_service),
) -> JobDetailOut:
    """Job card detail (responsibilities + requirements + boundaries)."""
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail_out(job)
