"""招聘市场领域类型 (T607).

所有招聘市场 Provider 输出的统一数据结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JobPosting:
    """统一在招岗位.

    Attributes:
        source: 数据源 (boss / lagou / linkedin / adzuna / mock).
        external_id: 源系统的岗位 ID.
        title: 岗位标题.
        company: 公司名.
        city: 城市 (例如 "上海" / "Shanghai").
        salary_min_k / salary_max_k: 月薪区间,单位千 (CNY 或 USD,见 salary_currency).
        salary_currency: 货币代码 (CNY / USD).
        experience_years: 经验要求 ("3-5年" / "3+").
        education: 学历要求 ("本科" / "Bachelor").
        skills: 技能标签.
        url: 岗位详情 URL.
        posted_at: ISO8601 字符串.
        description_snippet: 简介前 280 字.
        raw: 源系统原始字段.
    """

    source: str
    external_id: str
    title: str
    company: str
    city: str | None = None
    salary_min_k: float | None = None
    salary_max_k: float | None = None
    salary_currency: str = "CNY"
    experience_years: str | None = None
    education: str | None = None
    skills: list[str] = field(default_factory=list)
    url: str | None = None
    posted_at: str | None = None
    description_snippet: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SalaryPoint:
    """历史薪资点位.

    Attributes:
        period: 月份 (YYYY-MM).
        median_k: 中位数月薪 (单位千,见 currency).
        p25_k / p75_k: 25/75 分位.
        sample_size: 样本数.
        currency: 货币代码.
    """

    period: str
    median_k: float
    p25_k: float | None = None
    p75_k: float | None = None
    sample_size: int | None = None
    currency: str = "CNY"


@dataclass(slots=True)
class SkillDemand:
    """热门技能需求.

    Attributes:
        skill: 技能名.
        demand_score: 0-100 需求热度.
        job_count: 在招岗位中要求该技能的岗位数.
        growth_pct: 同比/环比增长百分比 (可正可负).
    """

    skill: str
    demand_score: float
    job_count: int = 0
    growth_pct: float | None = None