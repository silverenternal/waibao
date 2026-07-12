"""Company Review 领域类型 (T2401).

所有 Company Review Provider 输出的统一数据结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CompanyRating:
    """综合评分 (按 source 维度拆开, 0-5).

    Attributes:
        source: kanzhun / glassdoor / maimai / mock.
        score: 0-5 综合评分 (保留 1 位小数).
        review_count: 评价总数.
        recommend_pct: 推荐比例 0-100.
        ceo_pct: CEO 好评率 0-100 (看准专属).
        breakdown: 维度拆解,例如 {"compensation": 4.2, "culture": 3.8}.
    """

    source: str
    score: float
    review_count: int = 0
    recommend_pct: float | None = None
    ceo_pct: float | None = None
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Review:
    """单条员工评价.

    Attributes:
        id: 来源系统 ID.
        source: kanzhun / glassdoor / maimai / mock.
        title: 评价标题.
        content: 正文 (前 500 字).
        pros: 优点.
        cons: 缺点.
        rating: 0-5 评分.
        job_title: 岗位.
        employment_status: 在职/离职.
        created_at: ISO8601.
        author: 脱敏昵称.
        helpful_count: 有用计数.
    """

    id: str
    source: str
    title: str
    content: str
    pros: str | None = None
    cons: str | None = None
    rating: float = 0.0
    job_title: str | None = None
    employment_status: str | None = None
    created_at: str | None = None
    author: str | None = None
    helpful_count: int = 0


@dataclass(slots=True)
class InterviewExperience:
    """面试经验.

    Attributes:
        id: 来源 ID.
        source: kanzhun / glassdoor / maimai / mock.
        company_id: 公司 ID.
        job_title: 应聘岗位.
        difficulty: 1-5 (1 简单 / 5 困难).
        experience: "positive" / "neutral" / "negative".
        process: 面试流程摘要 (例如 "2 轮技术 + 1 轮 HR").
        questions: 面试题列表.
        result: "offer" / "rejected" / "pending" / "no_response".
        created_at: ISO8601.
        author: 脱敏昵称.
    """

    id: str
    source: str
    company_id: str
    job_title: str
    difficulty: int = 3
    experience: str = "neutral"
    process: str | None = None
    questions: list[str] = field(default_factory=list)
    result: str = "pending"
    created_at: str | None = None
    author: str | None = None


@dataclass(slots=True)
class SalaryInsights:
    """公司薪资洞察.

    Attributes:
        company_id: 公司 ID.
        median_k: 月薪中位数 (k, 千元).
        p25_k / p75_k: 25 / 75 分位.
        sample_size: 样本数.
        currency: CNY / USD.
        by_role: 按岗位聚合 (例如 {"python": 22.5}).
        last_updated: ISO8601.
    """

    company_id: str
    median_k: float
    p25_k: float | None = None
    p75_k: float | None = None
    sample_size: int = 0
    currency: str = "CNY"
    by_role: dict[str, float] = field(default_factory=dict)
    last_updated: str | None = None


@dataclass(slots=True)
class CompanyReviewBundle:
    """聚合后的公司评价包 (3 源合一).

    Attributes:
        company_id: 公司 ID.
        ratings: 各源评分 (list).
        reviews: 评价 (按时间倒序).
        interviews: 面试经验 (按时间倒序).
        salary: 薪资洞察.
        aggregated_score: 3 源加权平均 (0-5).
    """

    company_id: str
    ratings: list[CompanyRating] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    interviews: list[InterviewExperience] = field(default_factory=list)
    salary: SalaryInsights | None = None
    aggregated_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "aggregated_score": self.aggregated_score,
            "ratings": [
                {
                    "source": r.source,
                    "score": r.score,
                    "review_count": r.review_count,
                    "recommend_pct": r.recommend_pct,
                    "ceo_pct": r.ceo_pct,
                    "breakdown": r.breakdown,
                }
                for r in self.ratings
            ],
            "reviews": [
                {
                    "id": r.id,
                    "source": r.source,
                    "title": r.title,
                    "content": r.content,
                    "pros": r.pros,
                    "cons": r.cons,
                    "rating": r.rating,
                    "job_title": r.job_title,
                    "employment_status": r.employment_status,
                    "created_at": r.created_at,
                    "author": r.author,
                    "helpful_count": r.helpful_count,
                }
                for r in self.reviews
            ],
            "interviews": [
                {
                    "id": i.id,
                    "source": i.source,
                    "job_title": i.job_title,
                    "difficulty": i.difficulty,
                    "experience": i.experience,
                    "process": i.process,
                    "questions": i.questions,
                    "result": i.result,
                    "created_at": i.created_at,
                    "author": i.author,
                }
                for i in self.interviews
            ],
            "salary": (
                {
                    "company_id": self.salary.company_id,
                    "median_k": self.salary.median_k,
                    "p25_k": self.salary.p25_k,
                    "p75_k": self.salary.p75_k,
                    "sample_size": self.salary.sample_size,
                    "currency": self.salary.currency,
                    "by_role": self.salary.by_role,
                    "last_updated": self.salary.last_updated,
                }
                if self.salary
                else None
            ),
        }