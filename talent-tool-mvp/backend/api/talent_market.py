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
from fastapi import Response
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_client, require_role
from api.deps import PaginatedResponse
from contracts.shared import UserRole
from services.marketplace.talent_market import (
    CommunicationChannel,
    JobCard,
    JobDetail,
    MatchRecommendation,
    TalentCard,
    TalentDetail,
    TalentMarketService,
    ViewerContext,
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
# v11.2 T6304 — viewer-context plumbing (employer roles / talent profile)
# ---------------------------------------------------------------------------

def _fetch_employer_roles(user: CurrentUser) -> list[dict]:
    """Best-effort lookup of the employer's open roles for threshold scoring.

    Returns ``[]`` when Supabase is unreachable or the org has no roles (the
    service then surfaces a helpful empty-state message instead of erroring).
    """
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        # org membership: candidates table joins users → but roles carry
        # org_id directly. We scope by the user id mapped to an org, falling
        # back to all active roles owned by this user.
        res = (
            sb.table("roles")
            .select("*")
            .or_(f"owner_id.eq.{user.id},hr_id.eq.{user.id}")
            .limit(50)
            .execute()
        )
        return list(res.data or [])
    except Exception:  # noqa: BLE001 — anonymous browse / dev fallback
        logger.info("employer roles lookup failed for %s, treating as no roles", user.id)
        return []


def _fetch_talent_profile(user: CurrentUser) -> Optional[dict]:
    """Best-effort lookup of the talent's candidate profile for job scoring."""
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        res = (
            sb.table("candidates")
            .select("*")
            .eq("user_id", str(user.id))
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001 — dev fallback
        logger.info("talent profile lookup failed for %s", user.id)
        return None


def _viewer_from_user(
    user: Optional[CurrentUser],
) -> ViewerContext:
    """Build a :class:`ViewerContext` from the authenticated user (or None)."""
    if user is None:
        return ViewerContext(kind="anonymous")
    # v11.3: 甲方合同 4 角色 — 老板管理层 (boss) / 部门负责人 (department_head)
    # 属于企业方 (client 侧), 享有同等雇主可见性 (受阀值门约束), 不是平台 admin.
    # 此前只匹配 client → 这两个角色落到 else 被当成 admin, 绕过阀值门. 修复.
    if user.role in (UserRole.client, UserRole.boss, UserRole.department_head):
        return ViewerContext(
            kind="employer",
            employer_roles=_fetch_employer_roles(user),
            user_id=str(user.id),
        )
    if user.role == UserRole.talent_partner:
        return ViewerContext(
            kind="talent",
            talent_profile=_fetch_talent_profile(user),
            user_id=str(user.id),
        )
    # admin (平台管理员): 甲方合同 "资料查看/下载/导出权限: 仅平台管理员".
    # Admin sees the full market without the threshold gate — it is NOT an
    # employer and has no hiring roles, so a kind=employer with empty roles
    # would wrongly hide everyone. Use a dedicated admin viewer kind instead.
    return ViewerContext(kind="admin", user_id=str(user.id))


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
    # v11.2 T6304 — threshold-visibility flags
    can_contact: bool = False
    best_role_id: Optional[str] = None
    comm_channel_open: bool = False


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
    # v11.2 T6304 — threshold-visibility flags
    can_contact: bool = False
    best_role_id: Optional[str] = None
    comm_channel_open: bool = False


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


class CommunicationChannelOut(BaseModel):
    """A two-way contact channel between a candidate and a role's org."""

    id: str
    candidate_id: str
    role_id: str
    org_id: str
    initiated_by: str
    match_score: int = 0
    status: str = "open"
    created_at: str = ""
    updated_at: str = ""


class InitiateContactRequest(BaseModel):
    """Body for POST /talent-market/initiate-contact (employer only)."""

    talent_id: str
    role_id: str


def _talent_card_out(t: TalentCard) -> TalentCardOut:
    return TalentCardOut(
        id=t.id, name=t.name, title=t.title, city=t.city, skills=t.skills,
        seniority=t.seniority, education=t.education,
        salary_min_k=t.salary_min_k, salary_max_k=t.salary_max_k,
        experience_years=t.experience_years, availability=t.availability,
        match_score=t.match_score, online=t.online, avatar_color=t.avatar_color,
        can_contact=bool(getattr(t, "can_contact", False)),
        best_role_id=getattr(t, "best_role_id", None),
        comm_channel_open=bool(getattr(t, "comm_channel_open", False)),
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
        can_contact=bool(getattr(j, "can_contact", False)),
        best_role_id=getattr(j, "best_role_id", None),
        comm_channel_open=bool(getattr(j, "comm_channel_open", False)),
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
    user: Optional[CurrentUser] = Depends(_optional_user),
    response: Response = None,
    svc: TalentMarketService = Depends(get_service),
) -> PaginatedResponse:
    """Talent pool — paginated + filtered, viewer-aware.

    Employers only see talents scoring at/above the match threshold against
    their open roles; anonymous/talent viewers get masked cards
    (no contact, no real score). When an employer has no open roles an
    ``X-Empty-Hint`` header carries a helpful message (no error).
    """
    viewer = _viewer_from_user(user)
    cards, total, meta = svc.list_talents(
        page=page, page_size=page_size, keyword=keyword, position=position,
        skill=skill, city=city, salary_min=salary_min, salary_max=salary_max,
        education=education, viewer=viewer,
    )
    if meta.get("empty_hint") and response is not None:
        response.headers["X-Empty-Hint"] = meta["empty_hint"]
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
    """Talent detail — viewer-aware threshold visibility.

    Anonymous/seeker callers receive a masked summary; authenticated
    employer callers receive the full resume **only if** the match score
    against their roles reaches the threshold (otherwise 404 — the parties
    cannot know each other exists).
    """
    viewer = _viewer_from_user(user)
    full = _can_see_full_resume(user)
    talent = svc.get_talent(talent_id, full=full, viewer=viewer)
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
    user: Optional[CurrentUser] = Depends(_optional_user),
    response: Response = None,
    svc: TalentMarketService = Depends(get_service),
) -> PaginatedResponse:
    """Job pool — paginated + filtered, viewer-aware.

    Talent viewers only see jobs scoring at/above the threshold against
    their profile; anonymous/employer viewers get masked cards.
    """
    viewer = _viewer_from_user(user)
    cards, total, meta = svc.list_jobs(
        page=page, page_size=page_size, keyword=keyword, position=position,
        city=city, salary_min=salary_min, salary_max=salary_max, viewer=viewer,
    )
    if meta.get("empty_hint") and response is not None:
        response.headers["X-Empty-Hint"] = meta["empty_hint"]
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
    user: Optional[CurrentUser] = Depends(_optional_user),
    svc: TalentMarketService = Depends(get_service),
) -> JobDetailOut:
    """Job card detail — viewer-aware threshold visibility."""
    viewer = _viewer_from_user(user)
    job = svc.get_job(job_id, viewer=viewer)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail_out(job)


# ---------------------------------------------------------------------------
# v11.2 T6304 — 发起沟通 / 沟通渠道 (employer side)
# ---------------------------------------------------------------------------

_BELOW_THRESHOLD_MSG = "匹配度未达阀值(70%)，暂无法发起沟通"


def _channel_out(ch: CommunicationChannel) -> CommunicationChannelOut:
    return CommunicationChannelOut(
        id=ch.id, candidate_id=ch.candidate_id, role_id=ch.role_id,
        org_id=ch.org_id, initiated_by=ch.initiated_by,
        match_score=ch.match_score, status=ch.status,
        created_at=ch.created_at, updated_at=ch.updated_at,
    )


@router.post(
    "/initiate-contact",
    response_model=CommunicationChannelOut,
    tags=["talent-market"],
)
async def initiate_contact(
    body: InitiateContactRequest,
    user: CurrentUser = Depends(require_client),
    svc: TalentMarketService = Depends(get_service),
) -> CommunicationChannelOut:
    """发起沟通 (employer only).

    Creates a communication channel between ``talent_id`` and ``role_id``.
    Requires the real match score to be at/above the threshold, otherwise
    403 (the parties cannot know each other exists).
    """
    roles = _fetch_employer_roles(user)
    role = next((r for r in roles if str(r.get("id")) == str(body.role_id)), None)
    org_id = str((role or {}).get("org_id") or (role or {}).get("organisation_id") or "")
    try:
        channel = svc.initiate_contact(
            candidate_id=body.talent_id,
            role_id=body.role_id,
            org_id=org_id,
            initiated_by="employer",
            employer_roles=roles,
        )
    except ValueError:
        raise HTTPException(status_code=403, detail=_BELOW_THRESHOLD_MSG)
    return _channel_out(channel)


@router.get(
    "/channels",
    response_model=list[CommunicationChannelOut],
    tags=["talent-market"],
)
async def list_channels(
    user: CurrentUser = Depends(
        require_role(
            UserRole.client, UserRole.boss, UserRole.department_head,
            UserRole.talent_partner, UserRole.admin,
        )
    ),
    svc: TalentMarketService = Depends(get_service),
) -> list[CommunicationChannelOut]:
    """沟通渠道列表 — employer sees their org's channels; talent sees own."""
    if user.role == UserRole.talent_partner:
        profile = _fetch_talent_profile(user) or {}
        channels = svc.list_channels(candidate_id=str(profile.get("id") or user.id))
    else:
        # employer / admin: scope to their org's roles.
        roles = _fetch_employer_roles(user)
        org_ids = {
            str(r.get("org_id") or r.get("organisation_id") or "")
            for r in roles
        }
        if len(org_ids) == 1:
            (org_id,) = org_ids
            channels = svc.list_channels(org_id=org_id)
        else:
            # multiple/no orgs — return channels for any owned org.
            out = []
            for oid in org_ids:
                out.extend(svc.list_channels(org_id=oid))
            channels = out
    return [_channel_out(c) for c in channels]
