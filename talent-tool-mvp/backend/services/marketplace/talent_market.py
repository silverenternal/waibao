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
from typing import Any, Optional
from uuid import UUID

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


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


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
        certificates_required=_skill_names(row.get("certificates_required")),
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

    def __init__(self) -> None:
        self._talents: Optional[list[TalentCard]] = None
        self._jobs: Optional[list[JobCard]] = None

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
    ) -> tuple[list[TalentCard], int]:
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

        total = len(talents)
        start = (page - 1) * page_size
        return talents[start : start + page_size], total

    def get_talent(self, talent_id: str, *, full: bool = False) -> Optional[TalentCard]:
        for t in self._all_talents():
            if t.id == talent_id:
                if full:
                    return self._enrich_talent(t)
                return t
        return None

    def _enrich_talent(self, card: TalentCard) -> TalentDetail:
        rng = random.Random(hash(card.id) & 0xFFFFFFFF)
        surnames = ["张", "李", "王", "刘", "陈", "杨"]
        detail = TalentDetail(**card.__dict__)
        detail.full_name = f"{rng.choice(surnames)}{card.name[-1] if card.name else '某'}"
        detail.email = f"talent{abs(hash(card.id)) % 10000:04d}@example.com"
        detail.phone = f"1{rng.choice([3,5,7,8,9])}{rng.randint(100000000,999999999)}"
        detail.linkedin_url = "https://linkedin.com/in/" + card.id
        detail.summary = (
            f"{detail.full_name}，{card.experience_years or 3} 年"
            f"{card.title}经验，专注 {', '.join(card.skills[:3])}。"
        )
        detail.industries = [card.city, "互联网"]
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
    ) -> tuple[list[JobCard], int]:
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

        total = len(jobs)
        start = (page - 1) * page_size
        return jobs[start : start + page_size], total

    def get_job(self, job_id: str) -> Optional[JobCard]:
        for j in self._all_jobs():
            if j.id == job_id:
                return self._enrich_job(j)
        return None

    def _enrich_job(self, card: JobCard) -> JobDetail:
        detail = JobDetail(**card.__dict__)
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
        # T6107: 边界 — 不做什么 / 工作时间 / 地点 / 出差
        detail.work_schedule = (
            "弹性工作制, 标准工时 9:30-18:30, 双休"
        )
        detail.travel_required = "偶有出差 (季度 1-2 次, 国内为主)"
        detail.boundaries = [
            f"工作时间: {detail.work_schedule}",
            f"工作地点: {card.city} ({'远程可' if card.remote_policy == 'remote' else '需到岗'})",
            f"出差要求: {detail.travel_required}",
            "不参与: 与本岗位职责无关的外包接单 / 私活",
        ]
        detail.benefits = ["六险一金", "弹性工作", "年度体检", "股权激励"]
        detail.headcount = 2
        return detail

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
