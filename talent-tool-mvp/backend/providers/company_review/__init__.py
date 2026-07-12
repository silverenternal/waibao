"""Company Review Provider Package (T2401).

聚合 3 大外部公司评价数据源:
    - kanzhun   (看准网)
    - glassdoor (Glassdoor)
    - maimai    (脉脉)

所有真实 provider 在缺失凭证或上游失败时自动 fallback 到 mock.
"""
from __future__ import annotations

from .base import CompanyReviewProvider
from .types import (
    CompanyRating,
    InterviewExperience,
    Review,
    SalaryInsights,
)

__all__ = [
    "CompanyReviewProvider",
    "CompanyRating",
    "InterviewExperience",
    "Review",
    "SalaryInsights",
]