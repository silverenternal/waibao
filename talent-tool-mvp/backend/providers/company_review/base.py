"""CompanyReviewProvider 抽象基类 (T2401).

所有公司评价供应商 (看准 / Glassdoor / 脉脉) 必须实现该 ABC.
复用 v2.0 base.py 的 with_resilience 中间件.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import (
    CompanyRating,
    InterviewExperience,
    Review,
    SalaryInsights,
)


class CompanyReviewProvider(ABC):
    """公司评价供应商统一接口.

    四类核心方法:
        get_company_reviews       — 综合评分
        get_employee_reviews      — 员工评价列表
        get_interview_experiences — 面试经验列表
        get_salary_insights       — 薪资洞察
    """

    provider_name: str = "abstract"

    @abstractmethod
    async def get_company_reviews(self, company_id: str) -> CompanyRating:
        """获取公司综合评分 (含维度拆解).

        Args:
            company_id: 公司 ID (跨源统一, 例如 "kanzhun:bytedance").

        Returns:
            标准化的 CompanyRating (0-5 分制).
        """
        ...

    @abstractmethod
    async def get_employee_reviews(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Review]:
        """获取员工评价列表 (按时间倒序).

        Args:
            company_id: 公司 ID.
            page: 页码 (1-based).
            page_size: 每页条数.

        Returns:
            标准化后的 Review 列表.
        """
        ...

    @abstractmethod
    async def get_interview_experiences(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[InterviewExperience]:
        """获取面试经验列表 (按时间倒序)."""
        ...

    @abstractmethod
    async def get_salary_insights(self, company_id: str) -> SalaryInsights:
        """获取公司薪资洞察 (中位数 + 分位 + 按岗位)."""
        ...