"""T3002: AI 主动 Sourcing Agent.

输入岗位画像, 输出打分排序后的候选人 (目标 100 名)。

流程:
    1. 用 JobProfile 组装查询, 调 SourcingProvider.search_users (github/mock)
    2. github 失败 / 结果不足 → 回退 / 补充 mock, 保证产出充足
    3. 对每个候选人算 5 维匹配分 (skill/experience/location/activity/seniority)
    4. 按综合分排序, 生成匹配理由

结果缓存在进程内, 供 API 详情页按 candidate_id 回查。
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Optional

from providers.sourcing import (
    JobProfile,
    MatchScore,
    MockSourcingProvider,
    ScoredCandidate,
    SourcedCandidate,
    SourcingProvider,
    get_sourcing_provider,
)

logger = logging.getLogger("recruittech.platform.sourcing_agent")

_SENIORITY_YEARS = {"junior": 1, "mid": 3, "senior": 6, "staff": 9}


def _score_skill(profile: JobProfile, cand: SourcedCandidate) -> tuple[float, list[str]]:
    wanted = {s.lower() for s in profile.skills}
    if not wanted:
        return 60.0, []
    have = {s.lower() for s in (cand.skills + cand.top_languages)}
    overlap = wanted & have
    ratio = len(overlap) / len(wanted)
    reasons = []
    if overlap:
        matched = [s for s in profile.skills if s.lower() in overlap]
        reasons.append(f"技能命中 {', '.join(matched)}")
    return round(ratio * 100, 1), reasons


def _score_experience(profile: JobProfile, cand: SourcedCandidate) -> tuple[float, list[str]]:
    yrs = cand.years_experience
    if yrs is None:
        return 55.0, []
    if profile.min_years <= 0:
        base = min(100.0, 50 + yrs * 5)
        return round(base, 1), []
    if yrs >= profile.min_years:
        # 满足要求, 超出越多分越高但封顶
        score = min(100.0, 80 + (yrs - profile.min_years) * 4)
        return round(score, 1), [f"{yrs} 年经验满足 ≥{profile.min_years} 年要求"]
    gap = profile.min_years - yrs
    return round(max(20.0, 80 - gap * 20), 1), []


def _score_location(profile: JobProfile, cand: SourcedCandidate) -> tuple[float, list[str]]:
    if not profile.location:
        return 70.0, []
    if cand.location and profile.location in cand.location:
        return 100.0, [f"位于 {profile.location}"]
    return 30.0, []


def _score_activity(cand: SourcedCandidate) -> float:
    # followers + repos 归一到 0-100 (对数感)
    import math

    f = min(1.0, math.log1p(cand.followers) / math.log1p(3000))
    r = min(1.0, math.log1p(cand.public_repos) / math.log1p(120))
    return round((f * 0.6 + r * 0.4) * 100, 1)


def _score_seniority(profile: JobProfile, cand: SourcedCandidate) -> float:
    if not profile.seniority:
        return 70.0
    target = _SENIORITY_YEARS.get(profile.seniority.lower())
    yrs = cand.years_experience
    if target is None or yrs is None:
        return 60.0
    diff = abs(yrs - target)
    return round(max(30.0, 100 - diff * 12), 1)


def score_candidate(profile: JobProfile, cand: SourcedCandidate) -> ScoredCandidate:
    """对单个候选人算 5 维匹配分。"""
    skill, skill_reasons = _score_skill(profile, cand)
    exp, exp_reasons = _score_experience(profile, cand)
    loc, loc_reasons = _score_location(profile, cand)
    activity = _score_activity(cand)
    seniority = _score_seniority(profile, cand)
    score = MatchScore(
        skill=skill,
        experience=exp,
        location=loc,
        activity=activity,
        seniority=seniority,
    )
    reasons = [*skill_reasons, *exp_reasons, *loc_reasons]
    if activity >= 70:
        reasons.append("开源活跃度高")
    return ScoredCandidate(candidate=cand, score=score, reasons=reasons)


class SourcingAgent:
    """主动 sourcing 编排器。"""

    def __init__(self, provider: SourcingProvider | None = None) -> None:
        self._provider = provider
        self._mock = MockSourcingProvider(size=120)
        # candidate_id -> ScoredCandidate (最近一次搜索的结果缓存)
        self._cache: dict[str, ScoredCandidate] = {}
        self._lock = Lock()

    @property
    def provider(self) -> SourcingProvider:
        return self._provider or get_sourcing_provider()

    async def source(
        self,
        profile: JobProfile,
        *,
        target: int = 100,
    ) -> list[ScoredCandidate]:
        """发掘并打分, 返回按综合分降序的 target 名候选人。"""
        candidates = await self._collect(profile, target)
        scored = [score_candidate(profile, c) for c in candidates]
        scored.sort(key=lambda s: s.score.overall, reverse=True)
        scored = scored[:target]
        with self._lock:
            for s in scored:
                self._cache[s.candidate.id] = s
        return scored

    async def _collect(self, profile: JobProfile, target: int) -> list[SourcedCandidate]:
        """从主 provider 收集候选人, 不足则用 mock 去重补齐。"""
        collected: list[SourcedCandidate] = []
        seen: set[str] = set()

        try:
            primary = await self.provider.search_by_profile(profile, limit=target)
            for c in primary:
                if c.id not in seen:
                    seen.add(c.id)
                    collected.append(c)
        except Exception as exc:  # noqa: BLE001 - 上游失败回退 mock
            logger.warning("primary sourcing failed, fallback to mock: %s", exc)

        if len(collected) < target:
            filler = await self._mock.search_by_profile(profile, limit=target)
            for c in filler:
                if len(collected) >= target:
                    break
                if c.id in seen:
                    continue
                seen.add(c.id)
                collected.append(c)

        # 仍不足则用整池 (放宽过滤) 补齐, 让产出尽量接近 target
        if len(collected) < target:
            broad = await self._mock.search_users(q="", location=None, limit=target * 2)
            for c in broad:
                if len(collected) >= target:
                    break
                if c.id in seen:
                    continue
                seen.add(c.id)
                collected.append(c)
        return collected

    def get_candidate(self, candidate_id: str) -> Optional[ScoredCandidate]:
        """按 id 回查最近一次搜索的候选人详情。"""
        with self._lock:
            return self._cache.get(candidate_id)


_agent: SourcingAgent | None = None
_agent_lock = Lock()


def get_sourcing_agent() -> SourcingAgent:
    """进程内单例。"""
    global _agent
    if _agent is not None:
        return _agent
    with _agent_lock:
        if _agent is None:
            _agent = SourcingAgent()
    return _agent


def reset_sourcing_agent() -> None:
    """清空单例, 主要用于单元测试。"""
    global _agent
    with _agent_lock:
        _agent = None
