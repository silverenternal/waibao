"""Job Subscription — T1304 候选人主动订阅.

候选人保存一组订阅条件 (role / city / salary_min / skills),系统根据
matching v2 算法从 active 角色库中匹配出匹配的职位。

设计要点:
- 内存优先 + Supabase 持久化(supabase 不可用时纯内存).
- ``match_subscription(criteria)`` 接受 ``SubscriptionCriteria`` 或 dict,
  返回按 score 降序排列的 JobPosting 列表(最多 ``limit`` 条).
- ``match_all_subscriptions()`` 用于推送引擎触发:遍历所有订阅,
  找出每个订阅的命中职位,返回 ``(subscription, matches)`` 对.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("recruittech.services.job_subscription")

DEFAULT_LIMIT = 20


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SubscriptionCriteria:
    """订阅条件."""

    role: str = ""  # 职位关键字(模糊匹配 title)
    city: str = ""  # 城市 (e.g. "Shanghai" / "Remote")
    salary_min: float = 0.0  # 最低薪资(单位由 currency 决定)
    currency: str = "CNY"
    skills: list[str] = field(default_factory=list)
    seniority: str = ""  # 期望级别 (junior/mid/senior/lead/principal)
    remote_policy: str = ""  # onsite/hybrid/remote

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SubscriptionCriteria":
        data = data or {}
        return cls(
            role=str(data.get("role", "") or ""),
            city=str(data.get("city", "") or ""),
            salary_min=float(data.get("salary_min", 0) or 0),
            currency=str(data.get("currency", "CNY") or "CNY"),
            skills=list(data.get("skills") or []),
            seniority=str(data.get("seniority", "") or ""),
            remote_policy=str(data.get("remote_policy", "") or ""),
        )


@dataclass(slots=True)
class JobPosting:
    """匹配返回的职位(可以是 active role)."""

    id: str
    title: str
    company: str
    city: str
    salary_min: float
    salary_max: float
    currency: str
    skills: list[str]
    seniority: str
    remote_policy: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Subscription:
    """单条候选人订阅记录."""

    id: str
    user_id: str
    name: str  # 订阅别名,例如 "上海 P6 Python"
    criteria: SubscriptionCriteria
    channels: list[str] = field(default_factory=list)  # email/web/dingtalk/...
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["criteria"] = self.criteria.to_dict()
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Subscription":
        crit = row.get("criteria")
        if isinstance(crit, dict):
            criteria = SubscriptionCriteria.from_dict(crit)
        else:
            criteria = SubscriptionCriteria()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            name=row.get("name", ""),
            criteria=criteria,
            channels=list(row.get("channels") or []),
            enabled=bool(row.get("enabled", True)),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


class JobSubscriptionService:
    """订阅服务 — CRUD + 匹配."""

    def __init__(self, supabase: Any | None = None) -> None:
        self.supabase = supabase
        self._store: dict[str, Subscription] = {}

    # ----- CRUD -----
    def create(
        self,
        *,
        user_id: str,
        name: str,
        criteria: SubscriptionCriteria | dict[str, Any],
        channels: list[str] | None = None,
        enabled: bool = True,
    ) -> Subscription:
        if isinstance(criteria, dict):
            criteria = SubscriptionCriteria.from_dict(criteria)
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=str(user_id),
            name=name or criteria.role or "subscription",
            criteria=criteria,
            channels=list(channels or []),
            enabled=bool(enabled),
        )
        self._store[sub.id] = sub
        self._persist(sub)
        return sub

    def update(
        self,
        sub_id: str,
        *,
        user_id: str,
        name: str | None = None,
        criteria: dict[str, Any] | None = None,
        channels: list[str] | None = None,
        enabled: bool | None = None,
    ) -> Subscription | None:
        sub = self._store.get(sub_id)
        if not sub or sub.user_id != str(user_id):
            return None
        if name is not None:
            sub.name = name
        if criteria is not None:
            sub.criteria = SubscriptionCriteria.from_dict(criteria)
        if channels is not None:
            sub.channels = list(channels)
        if enabled is not None:
            sub.enabled = bool(enabled)
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(sub)
        return sub

    def delete(self, sub_id: str, *, user_id: str) -> bool:
        sub = self._store.get(sub_id)
        if not sub or sub.user_id != str(user_id):
            return False
        self._store.pop(sub_id, None)
        try:
            if self.supabase is not None:
                self.supabase.table("job_subscriptions").delete().eq(
                    "id", sub_id
                ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[job-subscription] delete persist failed: %s", exc)
        return True

    def get(self, sub_id: str, *, user_id: str | None = None) -> Subscription | None:
        sub = self._store.get(sub_id)
        if sub is None and self.supabase is not None:
            self._refresh_from_supabase()
            sub = self._store.get(sub_id)
        if sub is None:
            return None
        if user_id is not None and sub.user_id != str(user_id):
            return None
        return sub

    def list_for_user(self, user_id: str) -> list[Subscription]:
        if self.supabase is not None:
            self._refresh_from_supabase(user_id=user_id)
        return [s for s in self._store.values() if s.user_id == str(user_id)]

    def list_all_enabled(self) -> list[Subscription]:
        if self.supabase is not None:
            self._refresh_from_supabase()
        return [s for s in self._store.values() if s.enabled]

    # ----- 匹配 -----
    async def match_subscription(
        self,
        criteria: SubscriptionCriteria | dict[str, Any],
        *,
        limit: int = DEFAULT_LIMIT,
        jobs: list[JobPosting] | None = None,
    ) -> list[JobPosting]:
        """匹配活跃角色 -> JobPosting."""
        if isinstance(criteria, dict):
            criteria = SubscriptionCriteria.from_dict(criteria)
        jobs = jobs if jobs is not None else await self._fetch_jobs()
        scored: list[JobPosting] = []
        for job in jobs:
            score, reasons = _score_job(criteria, job)
            if score <= 0:
                continue
            job.score = round(score, 4)
            job.reasons = reasons
            scored.append(job)
        scored.sort(key=lambda j: j.score, reverse=True)
        return scored[:limit]

    async def match_all_subscriptions(
        self, *, jobs: list[JobPosting] | None = None
    ) -> list[tuple[Subscription, list[JobPosting]]]:
        """遍历所有启用订阅,逐一匹配;返回非空匹配对."""
        jobs = jobs if jobs is not None else await self._fetch_jobs()
        out: list[tuple[Subscription, list[JobPosting]]] = []
        for sub in self.list_all_enabled():
            matches = await self.match_subscription(
                sub.criteria, jobs=jobs, limit=DEFAULT_LIMIT
            )
            if matches:
                out.append((sub, matches))
        return out

    # ----- 持久化 -----
    def _persist(self, sub: Subscription) -> None:
        if self.supabase is None:
            return
        try:
            row = sub.to_dict()
            self.supabase.table("job_subscriptions").upsert(row).execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[job-subscription] persist failed: %s", exc)

    def _refresh_from_supabase(self, user_id: str | None = None) -> None:
        if self.supabase is None:
            return
        try:
            q = self.supabase.table("job_subscriptions").select("*")
            if user_id:
                q = q.eq("user_id", user_id)
            rows = q.execute().data or []
            for r in rows:
                self._store[r["id"]] = Subscription.from_row(r)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[job-subscription] refresh failed: %s", exc)

    async def _fetch_jobs(self) -> list[JobPosting]:
        """拉取活跃 role -> JobPosting;失败则返回空."""
        if self.supabase is None:
            return []
        try:
            res = (
                self.supabase.table("roles")
                .select(
                    "id,title,company,city,salary_min,salary_max,currency,"
                    "required_skills,seniority,remote_policy"
                )
                .eq("status", "active")
                .execute()
            )
            jobs: list[JobPosting] = []
            for r in res.data or []:
                skills = []
                for sk in r.get("required_skills") or []:
                    if isinstance(sk, dict) and sk.get("name"):
                        skills.append(sk["name"])
                jobs.append(
                    JobPosting(
                        id=r["id"],
                        title=r.get("title", ""),
                        company=r.get("company", ""),
                        city=r.get("city", ""),
                        salary_min=float(r.get("salary_min") or 0),
                        salary_max=float(r.get("salary_max") or 0),
                        currency=r.get("currency", "CNY"),
                        skills=skills,
                        seniority=r.get("seniority", ""),
                        remote_policy=r.get("remote_policy", ""),
                    )
                )
            return jobs
        except Exception as exc:  # noqa: BLE001
            logger.debug("[job-subscription] fetch jobs failed: %s", exc)
            return []

    # ----- 辅助 -----
    def clear(self) -> None:
        """测试用: 清空内存."""
        self._store.clear()


# ---------------------------------------------------------------------------
# 匹配评分 (与 matching v2 一致的 skill + 城市 + 薪资 + 级别 + remote 加权)
# ---------------------------------------------------------------------------

_WEIGHT_SKILL = 0.40
_WEIGHT_CITY = 0.20
_WEIGHT_SALARY = 0.20
_WEIGHT_SENIORITY = 0.10
_WEIGHT_REMOTE = 0.10


def _score_job(
    criteria: SubscriptionCriteria, job: JobPosting
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    # 1. role 关键字模糊匹配(只对 title 做包含判断)
    role_kw = (criteria.role or "").strip().lower()
    if role_kw:
        title_l = (job.title or "").lower()
        if role_kw in title_l or title_l in role_kw:
            score += _WEIGHT_SKILL
            reasons.append(f"title matches '{role_kw}'")
        else:
            # role 不匹配直接 0,避免噪音
            return 0.0, []

    # 2. skills overlap (Jaccard)
    if criteria.skills:
        cs = {s.strip().lower() for s in criteria.skills if s}
        js = {s.strip().lower() for s in job.skills if s}
        if cs and js:
            inter = cs & js
            union = cs | js
            jacc = len(inter) / len(union) if union else 0
            score += _WEIGHT_SKILL * jacc
            if inter:
                reasons.append(
                    f"matched skills: {', '.join(sorted(inter)[:5])}"
                )
        elif not cs:
            # 没指定 skills 时给一半 skill 权重
            score += _WEIGHT_SKILL * 0.5
    else:
        # 没指定 skills
        score += _WEIGHT_SKILL * 0.5

    # 3. city — 设置了就不匹配直接 0 (硬过滤)
    if criteria.city:
        if criteria.city.strip().lower() != (job.city or "").strip().lower():
            return 0.0, []
        score += _WEIGHT_CITY
        reasons.append(f"city {job.city}")

    # 4. salary_min — 设置了就不匹配直接 0 (硬过滤)
    if criteria.salary_min > 0:
        if job.salary_max <= 0 or job.salary_max < criteria.salary_min:
            return 0.0, []
        score += _WEIGHT_SALARY
        reasons.append(
            f"salary max {job.salary_max} >= target {criteria.salary_min}"
        )

    # 5. seniority — 设置了就不匹配直接 0 (硬过滤)
    if criteria.seniority:
        if criteria.seniority.strip().lower() != (job.seniority or "").strip().lower():
            return 0.0, []
        score += _WEIGHT_SENIORITY
        reasons.append(f"seniority {job.seniority}")

    # 6. remote_policy — 设置了就不匹配直接 0 (硬过滤)
    if criteria.remote_policy:
        if criteria.remote_policy.strip().lower() != (
            job.remote_policy or ""
        ).strip().lower():
            return 0.0, []
        score += _WEIGHT_REMOTE
        reasons.append(f"policy {job.remote_policy}")

    return score, reasons


__all__ = [
    "DEFAULT_LIMIT",
    "JobPosting",
    "JobSubscriptionService",
    "Subscription",
    "SubscriptionCriteria",
]