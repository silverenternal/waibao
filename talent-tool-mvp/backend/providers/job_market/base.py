"""JobMarketProvider 抽象基类 (T607).

所有招聘市场供应商 (Boss直聘 / 拉勾 / LinkedIn / Adzuna) 必须实现该 ABC.
复用 v2.0 base.py 的 with_resilience 中间件.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import JobPosting, SalaryPoint, SkillDemand


class JobMarketProvider(ABC):
    """招聘市场供应商统一接口.

    三类核心方法:
        search_jobs        — 按关键词 / 城市 / 薪资 / 页码 在招岗位检索
        get_salary_trend   — 历史薪资趋势
        get_hot_skills     — 热门技能需求
    """

    provider_name: str = "abstract"

    @abstractmethod
    async def search_jobs(
        self,
        keyword: str,
        *,
        city: str | None = None,
        salary_range: tuple[float, float] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[JobPosting]:
        """检索在招岗位.

        Args:
            keyword: 关键词 (岗位名 / 技能 / 公司名).
            city: 城市过滤,None 表示全国.
            salary_range: (min_k, max_k) 月薪千位过滤.
            page: 页码 (1-based).
            page_size: 每页条数,默认 20.

        Returns:
            标准化后的 JobPosting 列表 (按相关度倒序).
        """
        ...

    @abstractmethod
    async def get_salary_trend(
        self,
        role: str,
        city: str,
        *,
        months: int = 12,
    ) -> list[SalaryPoint]:
        """获取指定岗位在某城市的历史薪资中位数趋势.

        Args:
            role: 岗位名 (例 "Python 后端").
            city: 城市.
            months: 回看月数 (默认 12).

        Returns:
            按 period 升序排列的 SalaryPoint 列表.
        """
        ...

    @abstractmethod
    async def get_hot_skills(
        self,
        role: str | None = None,
        *,
        limit: int = 20,
    ) -> list[SkillDemand]:
        """热门技能需求榜.

        Args:
            role: 限定到具体岗位,None 表示大盘.
            limit: 最多返回 N 条.

        Returns:
            按 demand_score 倒序的 SkillDemand 列表.
        """
        ...

    # ------------------------------------------------------------------
    # 辅助方法 — 默认基于已实现方法的组合
    # ------------------------------------------------------------------
    async def search_jobs_combined(
        self,
        keywords: list[str],
        **kwargs: Any,
    ) -> list[JobPosting]:
        """多关键词并行检索并去重 (按 source+external_id)."""
        import asyncio

        if not keywords:
            return []
        results_per_kw = await asyncio.gather(
            *(self.search_jobs(k, **kwargs) for k in keywords),
            return_exceptions=True,
        )
        seen: set[tuple[str, str]] = set()
        merged: list[JobPosting] = []
        for kw, results in zip(keywords, results_per_kw):
            if isinstance(results, Exception):
                continue
            for job in results:
                key = (job.source, job.external_id)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(job)
        return merged