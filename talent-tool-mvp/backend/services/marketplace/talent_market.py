"""T6103 — Recruitment Marketplace service.

A two-sided talent/job marketplace: jobseekers store their profiles here,
employers store open roles, and both sides can browse + get match
recommendations.

The service reads from the existing ``candidates`` (talent pool) and
``roles`` (job pool) Supabase tables. When those tables are empty or
unreachable (e.g. dev without seed data) it falls back to a stable
synthetic catalog so the UI is always populated. All PII on the talent
side is gated: anonymous summary is returned to the public/seeker audience,
full resume + contact info only to authenticated employer/admin users.
"""
from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from matching.threshold import (
    MATCH_THRESHOLD,
    VisibilityGate,
    best_score_against_roles,
    best_score_against_talents,
    compute_pair_score,
    is_above_threshold,
)

logger = logging.getLogger("recruittech.services.talent_market")

# Deterministic RNG so the fallback catalog is stable across calls
# (same seed → same ids → consistent deep links during a session).
_RNG = random.Random(20240610)

CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都", "南京", "武汉", "远程"]
SKILL_POOL = [
    "Python", "Java", "Go", "TypeScript", "React", "Vue", "Node.js",
    "FastAPI", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes",
    "AWS", "Machine Learning", "PyTorch", "TensorFlow", "LLM", "RAG",
    "Spark", "Flink", "Elasticsearch", "GraphQL", "gRPC", "C++",
]
POSITIONS = [
    "后端工程师", "前端工程师", "全栈工程师", "算法工程师", "数据工程师",
    "机器学习工程师", "DevOps 工程师", "测试工程师", "产品经理", "数据分析师",
    "架构师", "安全工程师", "移动端工程师", "技术经理", "SRE",
]
EDUCATIONS = ["大专", "本科", "硕士", "博士"]

# v11.2 T6302 — identity verification display map (shared with the migration)
#     pending   -> 待上传 (not verified yet)
#     submitted -> 待审核 (documents uploaded, awaiting review)
#     verified  -> 已认证 (all documents verified)
_IDENTITY_DISPLAY = {
    "pending": "待上传",
    "submitted": "待审核",
    "verified": "已认证",
}

# v11.2 T6302 — travel tolerance / requirement human-readable labels
_TRAVEL_REQUIRED_LABEL = {
    "none": "无需出差",
    "occasional": "偶有出差 (季度 1-2 次, 国内为主)",
    "frequent": "频繁出差 (每月多次, 含国内/海外)",
}
COMPANIES = [
    ("字节跳动", "互联网"), ("阿里巴巴", "互联网"), ("腾讯", "互联网"),
    ("美团", "互联网"), ("百度", "互联网"), ("华为", "通信"),
    ("小米", "智能硬件"), ("京东", "电商"), ("网易", "互联网"),
    ("拼多多", "电商"), ("小红书", "社区"), ("大疆", "智能硬件"),
]


@dataclass
class TalentCard:
    """Anonymous talent card shown in the public talent pool."""

    id: str
    name: str  # masked, e.g. "张*"
    title: str
    city: str
    skills: list[str]
    seniority: Optional[str]
    education: Optional[str]
    salary_min_k: Optional[int]
    salary_max_k: Optional[int]
    experience_years: Optional[int]
    availability: Optional[str]
    match_score: int  # 0-100, synthetic relevance signal
    online: bool
    avatar_color: str
    # v11.2 T6302 — identity + 五险一金/出差 soft dimensions
    identity_status: str = "pending"  # pending=待上传, submitted=待审核, verified=已认证
    social_insurance_expectation: Optional[bool] = None  # expects 五险一金
    travel_tolerance: Optional[str] = None  # willing | occasional | unwilling


@dataclass
class TalentDetail(TalentCard):
    """Full resume — employer/admin only. Adds contact + narrative."""

    full_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    summary: str = ""
    industries: list[str] = field(default_factory=list)


@dataclass
class JobCard:
    """Job card shown in the public job pool."""

    id: str
    company: str
    company_industry: str
    title: str
    city: str
    salary_min_k: Optional[int]
    salary_max_k: Optional[int]
    skills_required: list[str]
    skills_preferred: list[str]
    seniority: Optional[str]
    education: Optional[str]
    experience_years: Optional[str]
    remote_policy: str
    match_score: int  # 0-100, synthetic relevance for seekers
    posted_at: str
    # v11.2 T6302 — benefits/travel soft dimensions (never eliminate)
    offers_social_insurance: bool = True  # 五险一金
    offers_housing_fund: bool = False  # 住房公积金
    travel_required: str = "occasional"  # none | occasional | frequent


@dataclass
class JobDetail(JobCard):
    """Full job posting — seeker/employer/admin. Adds narrative + boundaries."""

    description: str = ""
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    headcount: int = 1
    # T6107: 岗位卡 4 部分 — 加分项 + 边界 (硬条件见 skills/education + certificates)
    certificates_required: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    work_schedule: str = ""
    travel_required: str = ""


@dataclass
class MatchRecommendation:
    """A talent↔job match recommendation shown on the market homepage."""

    id: str
    talent_id: str
    talent_name: str
    talent_title: str
    job_id: str
    job_title: str
    company: str
    score: int
    reasons: list[str]


# v11.2 T6304 — viewer context for threshold-visibility.

#: the kind of viewer asking the market for cards.
VIEWER_EMPLOYER = "employer"
VIEWER_TALENT = "talent"
VIEWER_ANONYMOUS = "anonymous"
VIEWER_ADMIN = "admin"


@dataclass
class ViewerContext:
    """Who is browsing the market.

    ``kind`` is one of employer / talent / anonymous / admin. ``employer_roles``
    is the list of role-dicts the employer's org has open (used to score
    talents). ``talent_profile`` is the browsing talent's candidate dict (used
    to score jobs). ``org_id`` / ``candidate_id`` / ``user_id`` identify the
    viewer for channel ownership checks.

    甲方合同: 平台管理员可查看全部资料/下载/导出 (资料查看权限: 仅平台管理员).
    因此 admin 视图不走阀值门 — 直接看到全部人才/岗位 + 完整简历.
    """

    kind: str = VIEWER_ANONYMOUS
    employer_roles: list[dict[str, Any]] = field(default_factory=list)
    talent_profile: Optional[dict[str, Any]] = None
    org_id: Optional[str] = None
    candidate_id: Optional[str] = None
    user_id: Optional[str] = None

    @property
    def is_employer(self) -> bool:
        return self.kind == VIEWER_EMPLOYER

    @property
    def is_talent(self) -> bool:
        return self.kind == VIEWER_TALENT

    @property
    def is_anonymous(self) -> bool:
        return self.kind == VIEWER_ANONYMOUS

    @property
    def is_admin(self) -> bool:
        return self.kind == VIEWER_ADMIN


@dataclass
class CommunicationChannel:
    """A two-way contact opened between a candidate and a role's org.

    Created only after the match score reaches the threshold. Once open both
    parties are mutually visible.
    """

    id: str
    candidate_id: str
    role_id: str
    org_id: str
    initiated_by: str  # candidate | employer
    match_score: int = 0
    status: str = "open"  # open | closed
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "role_id": self.role_id,
            "org_id": self.org_id,
            "initiated_by": self.initiated_by,
            "match_score": self.match_score,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# Helpful empty-state copy (甲方口径) when an employer has no open roles yet.
EMPTY_ROLES_HINT = (
    "您的企业暂未发布在招岗位。发布岗位后, 平台将自动按匹配阀值"
    f"({MATCH_THRESHOLD}%)为双方匹配, 并只展示达标的求职者。"
)


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def _role_key(role: Any) -> Optional[str]:
    """Best-effort id extraction for a role dict/object (id/role_id/uuid)."""
    if role is None:
        return None
    for k in ("id", "role_id", "uuid"):
        if isinstance(role, dict):
            v = role.get(k)
        else:
            v = getattr(role, k, None)
        if v is not None and v != "":
            return str(v)
    return None


def _salary_range(rng: random.Random) -> tuple[Optional[int], Optional[int]]:
    base = rng.choice([15, 18, 20, 25, 30, 35, 40, 50, 60, 80])
    return base, base + rng.choice([5, 8, 10, 15, 20])


def _build_fallback_talents(n: int = 24) -> list[TalentCard]:
    rng = random.Random(_RNG.randint(0, 10**9))
    talents: list[TalentCard] = []
    surnames = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
    for i in range(n):
        pos = rng.choice(POSITIONS)
        city = rng.choice(CITIES)
        skills = rng.sample(SKILL_POOL, rng.randint(3, 6))
        seniority = rng.choice(["初级", "中级", "高级", "资深", "专家", None])
        edu = rng.choice(EDUCATIONS + [None])
        smin, smax = _salary_range(rng)
        yrs = rng.randint(1, 15)
        online = rng.random() < 0.4
        tid = _stable_id("talent", "tal", i, pos, city)
        surname = rng.choice(surnames)
        talents.append(
            TalentCard(
                id=tid,
                name=f"{surname}*",
                title=pos,
                city=city,
                skills=skills,
                seniority=seniority,
                education=edu,
                salary_min_k=smin,
                salary_max_k=smax,
                experience_years=yrs,
                availability=rng.choice(["在职看机会", "离职可立即上岗", "应届", None]),
                match_score=rng.randint(62, 99),
                online=online,
                avatar_color=f"hsl({(i * 37) % 360} 65% 55%)",
                # v11.2 T6302 — identity + 五险一金/出差 soft dimensions
                identity_status=rng.choice(["pending", "submitted", "verified"]),
                social_insurance_expectation=rng.random() < 0.8,  # mostly True
                travel_tolerance=rng.choice(
                    ["willing", "occasional", "unwilling", None]
                ),
            )
        )
    talents.sort(key=lambda t: t.match_score, reverse=True)
    return talents


def _build_fallback_jobs(n: int = 24) -> list[JobCard]:
    rng = random.Random(_RNG.randint(0, 10**9))
    jobs: list[JobCard] = []
    for i in range(n):
        company, industry = rng.choice(COMPANIES)
        pos = rng.choice(POSITIONS)
        city = rng.choice(CITIES)
        req = rng.sample(SKILL_POOL, rng.randint(2, 4))
        pref = rng.sample([s for s in SKILL_POOL if s not in req], rng.randint(1, 3))
        seniority = rng.choice(["初级", "中级", "高级", "资深", "专家", None])
        edu = rng.choice(EDUCATIONS + [None])
        smin, smax = _salary_range(rng)
        jobs.append(
            JobCard(
                id=_stable_id("job", "job", i, company, pos, city),
                company=company,
                company_industry=industry,
                title=pos,
                city=city,
                salary_min_k=smin,
                salary_max_k=smax,
                skills_required=req,
                skills_preferred=pref,
                seniority=seniority,
                education=edu,
                experience_years=rng.choice(["1-3年", "3-5年", "5-10年", "不限"]),
                remote_policy=rng.choice(["onsite", "hybrid", "remote"]),
                match_score=rng.randint(60, 98),
                posted_at=f"2026-07-{(i % 15) + 1:02d}",
                # v11.2 T6302 — benefits/travel soft dimensions
                offers_social_insurance=rng.random() < 0.85,  # mostly True
                offers_housing_fund=rng.random() < 0.4,  # ~40% True
                travel_required=rng.choice(["none", "occasional", "frequent"]),
            )
        )
    jobs.sort(key=lambda j: j.match_score, reverse=True)
    return jobs


# ---------------------------------------------------------------------------
# Supabase row → card mappers
# ---------------------------------------------------------------------------

def _skill_names(skills: Any) -> list[str]:
    if not skills:
        return []
    out: list[str] = []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str):
                out.append(s)
            elif isinstance(s, dict):
                name = s.get("name") or s.get("skill")
                if name:
                    out.append(str(name))
    return out


def _candidate_to_card(row: dict[str, Any], idx: int) -> TalentCard:
    first = (row.get("first_name") or "").strip() or "求"
    last = (row.get("last_name") or "").strip()
    masked = f"{first[0]}*" if first else "匿*"
    salary = row.get("salary_expectation") or {}
    smin = salary.get("min_amount") if isinstance(salary, dict) else None
    smax = salary.get("max_amount") if isinstance(salary, dict) else None
    return TalentCard(
        id=str(row.get("id")),
        name=masked,
        title=row.get("current_title") or row.get("seniority") or "人才",
        city=row.get("location") or "未知",
        skills=_skill_names(row.get("skills")),
        seniority=row.get("seniority"),
        education=row.get("education"),
        salary_min_k=int(smin) if smin else None,
        salary_max_k=int(smax) if smax else None,
        experience_years=row.get("experience_years"),
        availability=row.get("availability"),
        match_score=min(99, 60 + (idx % 10) * 4),
        online=(idx % 5 == 0),
        avatar_color=f"hsl({(idx * 37) % 360} 65% 55%)",
        # v11.2 T6302 — identity + 五险一金/出差 soft dimensions
        identity_status=row.get("identity_status") or "pending",
        social_insurance_expectation=row.get("social_insurance_expectation"),
        travel_tolerance=row.get("travel_tolerance"),
    )


def _role_to_card(row: dict[str, Any], idx: int) -> JobCard:
    salary = row.get("salary_band") or {}
    smin = salary.get("min_amount") if isinstance(salary, dict) else None
    smax = salary.get("max_amount") if isinstance(salary, dict) else None
    company = row.get("company_name") or row.get("organisation_name") or "企业"
    industry = row.get("industry") or "未知"
    created = (row.get("created_at") or "")[:10]
    return JobCard(
        id=str(row.get("id")),
        company=company,
        company_industry=industry,
        title=row.get("title") or "职位",
        city=row.get("location") or "未知",
        salary_min_k=int(smin) if smin else None,
        salary_max_k=int(smax) if smax else None,
        skills_required=_skill_names(row.get("required_skills")),
        skills_preferred=_skill_names(row.get("preferred_skills")),
        seniority=row.get("seniority"),
        education=row.get("education"),
        experience_years=row.get("experience_years"),
        remote_policy=row.get("remote_policy") or "onsite",
        match_score=min(98, 58 + (idx % 10) * 4),
        posted_at=created or "2026-07-01",
        # v11.2 T6302 — benefits/travel soft dimensions
        offers_social_insurance=row.get("offers_social_insurance", True),
        offers_housing_fund=row.get("offers_housing_fund", False),
        travel_required=row.get("travel_required") or "occasional",
    )


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

def _try_query(table: str, columns: str, limit: int, order: str = "created_at"):
    """Best-effort Supabase read. Returns (rows, ok)."""
    try:
        from api.deps import get_supabase_admin  # local import to avoid cycle

        client = get_supabase_admin()
        res = (
            client.table(table)
            .select(columns)
            .order(order, desc=True)
            .limit(limit)
            .execute()
        )
        return (res.data or []), True
    except Exception as exc:  # pragma: no cover - dev fallback
        logger.info("talent_market fallback for %s: %s", table, exc)
        return [], False


class TalentMarketService:
    """Read-only aggregation over the candidates/roles tables + fallback."""

    CHANNELS_TABLE = "communication_channels"

    def __init__(self) -> None:
        self._talents: Optional[list[TalentCard]] = None
        self._jobs: Optional[list[JobCard]] = None
        # v11.2 T6304 — in-memory communication-channel store (resilience
        # fallback when Supabase is unreachable). Keyed by channel id; also
        # indexed by (candidate_id, role_id) via _channel_index.
        self._channels: dict[str, CommunicationChannel] = {}
        self._channel_index: dict[tuple[str, str], str] = {}
        self._channel_seq = 0
        self._channels_probed = False
        self._sb_channels = None

    # -- talent pool -------------------------------------------------------

    def _all_talents(self) -> list[TalentCard]:
        if self._talents is not None:
            return self._talents
        rows, ok = _try_query("candidates", "*", 200)
        if ok and rows:
            self._talents = [_candidate_to_card(r, i) for i, r in enumerate(rows)]
        else:
            self._talents = _build_fallback_talents(24)
        return self._talents

    def list_talents(
        self,
        *,
        page: int = 1,
        page_size: int = 12,
        keyword: Optional[str] = None,
        position: Optional[str] = None,
        skill: Optional[str] = None,
        city: Optional[str] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        education: Optional[str] = None,
        viewer: Optional[ViewerContext] = None,
    ) -> tuple[list[TalentCard], int, dict[str, Any]]:
        """Talent pool listing with viewer-aware threshold visibility.

        Returns ``(cards, total, meta)``. ``meta`` carries an optional
        ``empty_hint`` (甲方口径文案) for the employer-no-roles empty state.
        """
        meta: dict[str, Any] = {}
        talents = list(self._all_talents())
        if keyword:
            kw = keyword.lower()
            talents = [
                t for t in talents
                if kw in t.title.lower()
                or kw in t.name.lower()
                or any(kw in s.lower() for s in t.skills)
            ]
        if position:
            talents = [t for t in talents if position in t.title]
        if skill:
            talents = [t for t in talents if skill in t.skills]
        if city:
            talents = [t for t in talents if t.city == city]
        if education:
            talents = [t for t in talents if (t.education or "") >= education]
        if salary_min is not None:
            talents = [
                t for t in talents
                if t.salary_max_k is None or t.salary_max_k >= salary_min
            ]
        if salary_max is not None:
            talents = [
                t for t in talents
                if t.salary_min_k is None or t.salary_min_k <= salary_max
            ]

        # --- viewer-aware scoring / masking -------------------------------
        viewer = viewer or ViewerContext()
        if viewer.is_admin:
            # 甲方合同: 管理员可查看全部资料 (无阀值门, 可联系标记关闭——管理员
            # 不是雇佣方, 不在市场上发起沟通; 资料查看/下载走独立 admin 链路).
            talents = [self._mask_card_for_admin(t) for t in talents]
        elif viewer.is_employer:
            roles = viewer.employer_roles or []
            if not roles:
                # 甲方合同: 企业没有在招岗位 → 无法匹配任何人 → 空列表 + 提示.
                return [], 0, {"empty_hint": EMPTY_ROLES_HINT}
            scored: list[tuple[int, TalentCard, Optional[str]]] = []
            for t in talents:
                best_score, best_role_id, _ = best_score_against_roles(t, roles)
                if is_above_threshold(best_score):
                    scored.append((best_score, t, best_role_id))
            # 排序/增量: 不淘汰整体池, 但雇主视图只保留过线人才并按分降序.
            scored.sort(key=lambda x: x[0], reverse=True)
            talents = [
                self._annotate_card(t, score, role_id) for score, t, role_id in scored
            ]
        elif viewer.is_talent:
            # 求职者浏览人才池: 保留浏览体验, 不展示真实匹配分.
            talents = [self._mask_card_for_browse(t) for t in talents]
        else:
            # 匿名: 可浏览 (市场感), 但隐藏真实分 + 不可联系 + 无身份/联系.
            talents = [self._mask_card_for_anonymous(t) for t in talents]

        total = len(talents)
        start = (page - 1) * page_size
        return talents[start : start + page_size], total, meta

    def get_talent(
        self,
        talent_id: str,
        *,
        full: bool = False,
        viewer: Optional[ViewerContext] = None,
    ) -> Optional[TalentCard]:
        viewer = viewer or ViewerContext()
        card: Optional[TalentCard] = None
        for t in self._all_talents():
            if t.id == talent_id:
                card = t
                break
        if card is None:
            return None

        if viewer.is_admin:
            # 甲方合同: 管理员可查看全部资料/下载/导出 — 无阀值门, 返回完整简历.
            return self._enrich_talent(card) if full else self._mask_card_for_admin(card)

        if viewer.is_employer:
            roles = viewer.employer_roles or []
            if not roles:
                # 没有在招岗位 → 对雇主而言此人不存在.
                return None
            # 详情页展示真实最高匹配分 (须与 list_talents 一致, 否则同一候选人
            # 列表/详情分数对不上). 单 talent × R 岗位评分很轻量, 不用 early-stop.
            best_score, best_role_id, _ = best_score_against_roles(card, roles)
            if not is_above_threshold(best_score):
                # 甲方合同: 低于阀值 → 对方根本无法知道彼此存在 (404).
                return None
            annotated = self._annotate_card(card, best_score, best_role_id)
            return self._enrich_talent(annotated) if full else annotated

        if viewer.is_anonymous:
            # 匿名: 只返回脱敏摘要, 不返回 full.
            return self._mask_card_for_anonymous(card)

        # talent viewer or legacy None caller: respect `full` (admin) else masked.
        if full:
            return self._enrich_talent(card)
        return self._mask_card_for_browse(card)

    # -- viewer-aware annotation / masking --------------------------------

    def _annotate_card(
        self,
        card: TalentCard,
        score: int,
        best_role_id: Optional[str],
    ) -> TalentCard:
        """Attach the real best match score + best_role_id to an employer card.

        Overrides the synthetic ``match_score`` with the real threshold score.
        """
        card.match_score = int(score)
        # best_role_id is surfaced via the API layer (TalentCardOut) — store
        # it on the card instance so the API mapper can read it back.
        setattr(card, "best_role_id", best_role_id)
        setattr(card, "can_contact", True)
        setattr(card, "comm_channel_open", self._channel_exists_for(card.id, best_role_id))
        return card

    def _mask_card_for_browse(self, card: TalentCard) -> TalentCard:
        """Talent viewer browsing the pool — keep the marketplace feel.

        Contact disabled; the real match score is hidden because a talent
        browsing other talents has no role to score against.
        """
        setattr(card, "can_contact", False)
        setattr(card, "best_role_id", None)
        setattr(card, "comm_channel_open", False)
        return card

    def _mask_card_for_anonymous(self, card: TalentCard) -> TalentCard:
        """Anonymous browse — marketplace feel but no score / no contact.

        甲方合同: 匿名可浏览 (市场感), 但隐藏真实匹配度 (登录查看), 不可联系,
        无身份/联系信息.
        """
        card.match_score = 0  # hide real score; frontend shows 登录查看匹配度
        setattr(card, "can_contact", False)
        setattr(card, "best_role_id", None)
        setattr(card, "comm_channel_open", False)
        return card

    def _mask_card_for_admin(self, card: TalentCard) -> TalentCard:
        """Admin browse — full visibility, no threshold gate (甲方合同:
        资料查看/下载/导出权限: 仅平台管理员). Admin is not a hiring party,
        so it does not initiate market contact, but sees the real synthetic
        score / identity state for oversight.
        """
        setattr(card, "can_contact", False)
        setattr(card, "best_role_id", None)
        setattr(card, "comm_channel_open", False)
        return card

    def _channel_exists_for(
        self, candidate_id: Optional[str], role_id: Optional[str]
    ) -> bool:
        """True if an open communication channel already links the pair."""
        if not candidate_id or not role_id:
            return False
        return (candidate_id, role_id) in self._channel_index

    def _enrich_talent(self, card: TalentCard) -> TalentDetail:
        rng = random.Random(hash(card.id) & 0xFFFFFFFF)
        surnames = ["张", "李", "王", "刘", "陈", "杨"]
        # Drop viewer-annotation extras (can_contact/best_role_id/
        # comm_channel_open) — they are not TalentDetail fields, but the API
        # mapper reads them back off the returned object via getattr.
        base = {
            k: v for k, v in card.__dict__.items()
            if k in TalentCard.__dataclass_fields__
        }
        detail = TalentDetail(**base)
        detail.full_name = f"{rng.choice(surnames)}{card.name[-1] if card.name else '某'}"
        detail.email = f"talent{abs(hash(card.id)) % 10000:04d}@example.com"
        detail.phone = f"1{rng.choice([3,5,7,8,9])}{rng.randint(100000000,999999999)}"
        detail.linkedin_url = "https://linkedin.com/in/" + card.id
        # v11.3 甲方合同: 联系方式仅在沟通渠道开启后对雇主可见 ("联系前企业可见
        # 信息由阀值控制; 沟通发起后由双方决定"). 雇主达阀值可见完整简历, 但
        # email/phone/linkedin 要等发起沟通 (communication channel) 后才解锁.
        # admin ( oversight, 非标注卡) 与 talent 本人不受限. 判据: 仅 _annotate_card
        # 给雇主卡打上 can_contact=True; 未开渠道时 comm_channel_open=False.
        if getattr(card, "can_contact", False) and not getattr(
            card, "comm_channel_open", False
        ):
            detail.email = None
            detail.phone = None
            detail.linkedin_url = None
        detail.summary = (
            f"{detail.full_name}，{card.experience_years or 3} 年"
            f"{card.title}经验，专注 {', '.join(card.skills[:3])}。"
        )
        detail.industries = [card.city, "互联网"]
        # v11.2 T6302 — surface identity verification state using the display
        # map. Never eliminates; just informs the employer. Only note it when
        # the candidate is NOT fully verified.
        if getattr(card, "identity_status", "verified") != "verified":
            identity_label = _IDENTITY_DISPLAY.get(
                getattr(card, "identity_status", "pending"), "待上传"
            )
            detail.summary += f" (身份: {identity_label})"
        return detail

    # -- job pool ----------------------------------------------------------

    def _all_jobs(self) -> list[JobCard]:
        if self._jobs is not None:
            return self._jobs
        rows, ok = _try_query("roles", "*", 200)
        if ok and rows:
            self._jobs = [_role_to_card(r, i) for i, r in enumerate(rows)]
        else:
            self._jobs = _build_fallback_jobs(24)
        return self._jobs

    def list_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 12,
        keyword: Optional[str] = None,
        position: Optional[str] = None,
        city: Optional[str] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        viewer: Optional[ViewerContext] = None,
    ) -> tuple[list[JobCard], int, dict[str, Any]]:
        """Job pool listing with viewer-aware threshold visibility.

        Returns ``(cards, total, meta)``.
        """
        meta: dict[str, Any] = {}
        jobs = list(self._all_jobs())
        if keyword:
            kw = keyword.lower()
            jobs = [
                j for j in jobs
                if kw in j.title.lower()
                or kw in j.company.lower()
                or any(kw in s.lower() for s in j.skills_required)
            ]
        if position:
            jobs = [j for j in jobs if position in j.title]
        if city:
            jobs = [j for j in jobs if j.city == city]
        if salary_min is not None:
            jobs = [
                j for j in jobs
                if j.salary_max_k is None or j.salary_max_k >= salary_min
            ]
        if salary_max is not None:
            jobs = [
                j for j in jobs
                if j.salary_min_k is None or j.salary_min_k <= salary_max
            ]

        # --- viewer-aware scoring ------------------------------------------
        viewer = viewer or ViewerContext()
        if viewer.is_talent and viewer.talent_profile:
            talent = viewer.talent_profile
            scored: list[tuple[int, JobCard]] = []
            for j in jobs:
                # candidate-first contract: filter(talent, role).
                res = compute_pair_score(talent, j)
                if is_above_threshold(res.match_score):
                    j.match_score = int(res.match_score)
                    setattr(j, "can_contact", True)
                    setattr(
                        j,
                        "comm_channel_open",
                        self._channel_exists_for(
                            viewer.candidate_id, j.id
                        ),
                    )
                    scored.append((res.match_score, j))
            scored.sort(key=lambda x: x[0], reverse=True)
            jobs = [j for _, j in scored]
        elif viewer.is_talent:
            # logged-in talent with no profile yet → browse, no real score.
            jobs = [self._mask_job_for_browse(j) for j in jobs]
        else:
            # anonymous / employer browsing jobs: marketplace feel, masked.
            jobs = [self._mask_job_for_browse(j) for j in jobs]

        total = len(jobs)
        start = (page - 1) * page_size
        return jobs[start : start + page_size], total, meta

    def _mask_job_for_browse(self, card: JobCard) -> JobCard:
        setattr(card, "can_contact", False)
        setattr(card, "comm_channel_open", False)
        return card

    def get_job(
        self,
        job_id: str,
        *,
        viewer: Optional[ViewerContext] = None,
    ) -> Optional[JobCard]:
        viewer = viewer or ViewerContext()
        card: Optional[JobCard] = None
        for j in self._all_jobs():
            if j.id == job_id:
                card = j
                break
        if card is None:
            return None
        # talent viewer: below threshold → job invisible (甲方合同, 对称).
        if viewer.is_talent and viewer.talent_profile:
            res = compute_pair_score(viewer.talent_profile, card)
            if not is_above_threshold(res.match_score):
                return None
            card.match_score = int(res.match_score)
            setattr(card, "can_contact", True)
            setattr(
                card,
                "comm_channel_open",
                self._channel_exists_for(viewer.candidate_id, card.id),
            )
        else:
            setattr(card, "can_contact", False)
            setattr(card, "comm_channel_open", False)
        return self._enrich_job(card)

    def _enrich_job(self, card: JobCard) -> JobDetail:
        base = {
            k: v for k, v in card.__dict__.items()
            if k in JobCard.__dataclass_fields__
        }
        detail = JobDetail(**base)
        detail.description = (
            f"{card.company} 正在招聘 {card.title}，工作地点 {card.city}。"
        )
        detail.responsibilities = [
            f"负责 {card.company_industry} 相关 {card.title} 工作",
            "参与系统架构设计与核心模块开发",
            "与产品、测试协作推动项目高质量交付",
            "保障线上系统稳定性与性能持续优化",
        ]
        detail.requirements = [
            f"{card.experience_years or '不限'}相关经验",
            f"熟练掌握 {', '.join(card.skills_required[:3])}",
            "良好的沟通与团队协作能力",
        ]
        # T6107: 加分项 (preferred 技能 + 软实力)
        detail.nice_to_have = list(card.skills_preferred[:4]) + [
            "有高并发 / 大流量系统经验",
            "有技术团队带教经验",
        ][:4]
        # v11.2 T6302 — derive benefits/travel lines from the card's soft
        # fields (offers_social_insurance / offers_housing_fund /
        # travel_required) instead of hardcoding them.
        benefits_line = "五险一金" if card.offers_social_insurance else "无五险一金"
        if card.offers_housing_fund:
            benefits_line += ", 含公积金"
        detail.travel_required = _TRAVEL_REQUIRED_LABEL.get(
            card.travel_required, _TRAVEL_REQUIRED_LABEL["occasional"]
        )
        # T6107: 边界 — 不做什么 / 工作时间 / 地点 / 出差 / 福利
        detail.work_schedule = (
            "弹性工作制, 标准工时 9:30-18:30, 双休"
        )
        detail.boundaries = [
            f"工作时间: {detail.work_schedule}",
            f"工作地点: {card.city} ({'远程可' if card.remote_policy == 'remote' else '需到岗'})",
            f"出差要求: {detail.travel_required}",
            f"福利保障: {benefits_line}",
            "不参与: 与本岗位职责无关的外包接单 / 私活",
        ]
        # benefits list mirrors the derived compensation offering
        detail.benefits = [
            "六险一金" if card.offers_social_insurance else "商保",
            "公积金" if card.offers_housing_fund else "弹性工作",
            "弹性工作",
            "年度体检",
            "股权激励",
        ]
        detail.headcount = 2
        return detail

    # -- communication channels (T6304) -----------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _channels_client(self):
        """Lazily resolve + probe the Supabase client for the channels table.

        A misconfigured/unreachable client is cached as None so the service
        degrades to the in-memory store (mirrors the recommendation service
        fallback pattern).
        """
        if self._channels_probed:
            return self._sb_channels
        self._channels_probed = True
        try:
            from api.deps import get_supabase_admin

            client = get_supabase_admin()
            client.table(self.CHANNELS_TABLE).select("id").limit(1).execute()
            self._sb_channels = client
        except Exception as exc:  # pragma: no cover - dev fallback
            logger.info(
                "talent_market channels: Supabase unavailable, using memory store: %s",
                exc,
            )
            self._sb_channels = None
        return self._sb_channels

    def initiate_contact(
        self,
        *,
        candidate_id: str,
        role_id: str,
        org_id: str,
        initiated_by: str = "employer",
        employer_roles: Optional[list[dict[str, Any]]] = None,
        talent_profile: Optional[dict[str, Any]] = None,
    ) -> CommunicationChannel:
        """Open a communication channel between a candidate and a role.

        甲方合同: 只有当匹配度 ≥ 阀值才允许发起沟通; 低于阀值 → ValueError.
        Creates a ``communication_channels`` row (or in-memory fallback). Once
        created both parties are mutually visible.

        ``employer_roles`` (employer-initiated) or ``talent_profile``
        (candidate-initiated) feeds the real score check. Falls back to a
        direct ``compute_pair_score`` if neither context is supplied.
        """
        # --- (a) verify match >= threshold -------------------------------
        # 甲方合同 + 安全: 只允许对 *真实存在且调用方拥有/具备* 的 (候选人, 岗位)
        # 对开沟通. 绝不能对一个只有 {"id": ...} 的空岗位/空候选人评分——
        # HardConditionFilter 把空约束视为达标 (ratio=1.0), 会得到 100 分从而
        # 绕过阀值门 (雇主可对任意 talent_id 开渠道). 因此找不到真实上下文 →
        # 拒绝 (ValueError → API 403).
        score = 0
        try:
            if initiated_by == "employer":
                roles = employer_roles or []
                role = next((r for r in roles if str(_role_key(r)) == str(role_id)), None)
                if role is None:
                    # 雇主不拥有该岗位 → 拒绝 (防止越权开渠道).
                    raise ValueError("role not owned by employer")
                score, _, _ = best_score_against_roles(
                    self._talent_dict(candidate_id),
                    roles,
                    early_threshold=MATCH_THRESHOLD,
                )
            else:
                talent = talent_profile or self._talent_dict(candidate_id)
                # 候选人必须提供真实画像 (含技能), 否则空约束 → 100 分绕过阀值.
                if not talent or not (
                    talent.get("skills") or talent.get("skill_list")
                ):
                    raise ValueError("talent profile missing for scoring")
                role_obj = self._role_dict(role_id)
                if role_obj is None or not (
                    role_obj.get("required_skills")
                    or role_obj.get("skills_required")
                ):
                    raise ValueError("role not found / has no requirements")
                score = compute_pair_score(talent, role_obj).match_score
        except ValueError:
            raise
        except Exception:  # noqa: BLE001 — never crash on scoring
            score = 0

        if not is_above_threshold(score):
            raise ValueError("below threshold")

        # --- (b) persist (or in-memory) ----------------------------------
        return self._upsert_channel(
            candidate_id=candidate_id,
            role_id=role_id,
            org_id=org_id,
            initiated_by=initiated_by,
            score=score,
        )

    def _upsert_channel(
        self,
        *,
        candidate_id: str,
        role_id: str,
        org_id: str,
        initiated_by: str,
        score: int,
    ) -> CommunicationChannel:
        sb = self._channels_client()
        payload = {
            "candidate_id": str(candidate_id),
            "role_id": str(role_id),
            "org_id": str(org_id),
            "initiated_by": initiated_by,
            "match_score": int(score),
            "status": "open",
        }
        if sb is not None:
            try:
                res = sb.table(self.CHANNELS_TABLE).upsert(
                    payload, on_conflict="candidate_id,role_id"
                ).execute()
                row = (res.data or [{}])[0]
                return self._row_to_channel(row)
            except Exception as exc:  # pragma: no cover - DB fallback
                logger.warning(
                    "talent_market channel upsert failed, using memory: %s", exc
                )
        return self._upsert_channel_memory(
            candidate_id=candidate_id,
            role_id=role_id,
            org_id=org_id,
            initiated_by=initiated_by,
            score=score,
        )

    def _upsert_channel_memory(
        self,
        *,
        candidate_id: str,
        role_id: str,
        org_id: str,
        initiated_by: str,
        score: int,
    ) -> CommunicationChannel:
        key = (str(candidate_id), str(role_id))
        existing_id = self._channel_index.get(key)
        now = self._now_iso()
        if existing_id and existing_id in self._channels:
            ch = self._channels[existing_id]
            ch.match_score = int(score)
            ch.status = "open"
            ch.updated_at = now
            return ch
        self._channel_seq += 1
        ch_id = f"ch_{self._channel_seq}"
        ch = CommunicationChannel(
            id=ch_id,
            candidate_id=str(candidate_id),
            role_id=str(role_id),
            org_id=str(org_id),
            initiated_by=initiated_by,
            match_score=int(score),
            status="open",
            created_at=now,
            updated_at=now,
        )
        self._channels[ch_id] = ch
        self._channel_index[key] = ch_id
        return ch

    @staticmethod
    def _row_to_channel(row: dict[str, Any]) -> CommunicationChannel:
        return CommunicationChannel(
            id=str(row.get("id")),
            candidate_id=str(row.get("candidate_id", "")),
            role_id=str(row.get("role_id", "")),
            org_id=str(row.get("org_id", "")),
            initiated_by=str(row.get("initiated_by", "employer")),
            match_score=int(row.get("match_score") or 0),
            status=str(row.get("status", "open")),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def _talent_dict(self, candidate_id: str) -> dict[str, Any]:
        """Best-effort dict view of a talent card for scoring."""
        for t in self._all_talents():
            if t.id == candidate_id:
                return {
                    "id": t.id,
                    "skills": t.skills,
                    "education": t.education,
                    "salary_min_k": t.salary_min_k,
                    "salary_max_k": t.salary_max_k,
                    "city": t.city,
                    "availability": t.availability,
                    "social_insurance_expectation": getattr(
                        t, "social_insurance_expectation", None
                    ),
                    "travel_tolerance": getattr(t, "travel_tolerance", None),
                }
        return {"id": candidate_id}

    def _role_dict(self, role_id: str) -> Optional[dict[str, Any]]:
        """Best-effort dict view of a job card for scoring (candidate side).

        Returns None when no job with ``role_id`` exists in the pool. Callers
        must treat None as "role unknown" and refuse to score (an empty role
        dict would satisfy all hard conditions → score 100 → threshold bypass).
        """
        for j in self._all_jobs():
            if j.id == role_id:
                return {
                    "id": j.id,
                    "required_skills": j.skills_required,
                    "preferred_skills": j.skills_preferred,
                    "education": j.education,
                    "seniority": j.seniority,
                    "salary_min_k": j.salary_min_k,
                    "salary_max_k": j.salary_max_k,
                    "city": j.city,
                    "remote_policy": j.remote_policy,
                    "offers_social_insurance": getattr(
                        j, "offers_social_insurance", True
                    ),
                    "offers_housing_fund": getattr(j, "offers_housing_fund", False),
                    "travel_required": getattr(j, "travel_required", "occasional"),
                }
        return None

    def list_channels(
        self, *, org_id: Optional[str] = None, candidate_id: Optional[str] = None
    ) -> list[CommunicationChannel]:
        """Channels for the caller — employer (org) or talent (candidate)."""
        sb = self._channels_client()
        if sb is not None:
            try:
                q = sb.table(self.CHANNELS_TABLE).select("*").eq("status", "open")
                if org_id:
                    q = q.eq("org_id", org_id)
                if candidate_id:
                    q = q.eq("candidate_id", candidate_id)
                res = q.order("created_at", desc=True).execute()
                return [self._row_to_channel(r) for r in (res.data or [])]
            except Exception as exc:  # pragma: no cover - DB fallback
                logger.warning("talent_market channel list failed: %s", exc)
        # in-memory fallback
        out = list(self._channels.values())
        if org_id:
            out = [c for c in out if c.org_id == org_id]
        if candidate_id:
            out = [c for c in out if c.candidate_id == candidate_id]
        out.sort(key=lambda c: c.created_at, reverse=True)
        return out

    # -- stats + recommendations ------------------------------------------

    def stats(self) -> dict[str, int]:
        talents = self._all_talents()
        jobs = self._all_jobs()
        companies = {j.company for j in jobs}
        online = sum(1 for t in talents if t.online)
        return {
            "talents_total": len(talents),
            "talents_online": online,
            "jobs_total": len(jobs),
            "companies_total": len(companies) or max(1, len(jobs) // 2),
            "matches_total": max(len(talents), len(jobs)) * 3,
        }

    def recommendations(self, limit: int = 5) -> list[MatchRecommendation]:
        talents = self._all_talents()
        jobs = self._all_jobs()
        recs: list[MatchRecommendation] = []
        rng = random.Random(7)
        pair_count = min(limit, len(talents), len(jobs)) or 0
        for i in range(pair_count):
            t = talents[i]
            j = jobs[i]
            overlap = set(t.skills) & set(j.skills_required)
            reasons: list[str] = []
            if overlap:
                reasons.append(f"技能匹配: {', '.join(list(overlap)[:3])}")
            if t.city == j.city:
                reasons.append(f"同城 ({t.city})")
            if t.seniority and j.seniority and t.seniority == j.seniority:
                reasons.append(f"职级契合 ({t.seniority})")
            if not reasons:
                reasons.append("综合画像相近")
            recs.append(
                MatchRecommendation(
                    id=_stable_id("match", t.id, j.id),
                    talent_id=t.id,
                    talent_name=t.name,
                    talent_title=t.title,
                    job_id=j.id,
                    job_title=j.title,
                    company=j.company,
                    score=max(60, min(99, 70 + len(overlap) * 8)),
                    reasons=reasons,
                )
            )
        return recs


_service_singleton: Optional[TalentMarketService] = None


def get_service() -> TalentMarketService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = TalentMarketService()
    return _service_singleton
