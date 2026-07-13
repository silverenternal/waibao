"""T3002: AI 主动 Sourcing 领域类型.

所有 SourcingProvider 输出的统一候选人结构 + 岗位画像输入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JobProfile:
    """岗位画像 (sourcing 输入)。"""

    title: str
    skills: list[str] = field(default_factory=list)
    location: str | None = None            # 城市, 如 "北京" / "Shanghai"
    seniority: str | None = None           # junior / mid / senior / staff
    min_years: int = 0
    keywords: list[str] = field(default_factory=list)
    company_stage: str | None = None       # startup / growth / enterprise

    def query_terms(self) -> list[str]:
        """用于外部搜索的关键词集合。"""
        terms = list(self.skills) + list(self.keywords)
        if self.title:
            terms.append(self.title)
        return [t for t in terms if t]


@dataclass(slots=True)
class SourcedCandidate:
    """统一的候选人画像 (跨源标准化)。"""

    id: str                                # "<source>:<external_id>"
    source: str                            # github / mock / linkedin ...
    name: str
    headline: str | None = None            # 一句话简介
    location: str | None = None
    skills: list[str] = field(default_factory=list)
    years_experience: int | None = None
    company: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None
    email: str | None = None               # 多数源不可得, 需外部富化
    followers: int = 0
    public_repos: int = 0
    top_languages: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "name": self.name,
            "headline": self.headline,
            "location": self.location,
            "skills": self.skills,
            "years_experience": self.years_experience,
            "company": self.company,
            "profile_url": self.profile_url,
            "avatar_url": self.avatar_url,
            "email": self.email,
            "followers": self.followers,
            "public_repos": self.public_repos,
            "top_languages": self.top_languages,
        }


@dataclass(slots=True)
class MatchScore:
    """5 维度匹配评分 (0-100)。"""

    skill: float = 0.0            # 技能栈重合度
    experience: float = 0.0       # 经验年限匹配
    location: float = 0.0         # 地域匹配
    activity: float = 0.0         # 开源活跃度 / 影响力
    seniority: float = 0.0        # 资历匹配

    @property
    def overall(self) -> float:
        """加权综合分: skill 40 / experience 20 / activity 20 / location 10 / seniority 10。"""
        return round(
            self.skill * 0.40
            + self.experience * 0.20
            + self.activity * 0.20
            + self.location * 0.10
            + self.seniority * 0.10,
            1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": round(self.skill, 1),
            "experience": round(self.experience, 1),
            "location": round(self.location, 1),
            "activity": round(self.activity, 1),
            "seniority": round(self.seniority, 1),
            "overall": self.overall,
        }


@dataclass(slots=True)
class ScoredCandidate:
    """候选人 + 匹配分 + 匹配理由。"""

    candidate: SourcedCandidate
    score: MatchScore
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.candidate.to_dict()
        d["match"] = self.score.to_dict()
        d["reasons"] = self.reasons
        return d
