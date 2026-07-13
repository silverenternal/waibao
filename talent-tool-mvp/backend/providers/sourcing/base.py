"""T3002: SourcingProvider 抽象基类.

所有主动 sourcing 供应商 (GitHub / LinkedIn / 脉脉 / 微博小红书) 必须实现该 ABC。
复用 providers/base.py 的 with_resilience 中间件做外部调用的熔断/限流/重试。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import JobProfile, SourcedCandidate


class SourcingProvider(ABC):
    """主动 sourcing 供应商统一接口。

    两个核心方法:
        search_users     — 按技术栈 + 地域搜候选人
        get_user_profile — 拉单个候选人完整画像
    """

    provider_name: str = "abstract"

    @abstractmethod
    async def search_users(
        self,
        *,
        q: str,
        location: str | None = None,
        limit: int = 50,
    ) -> list[SourcedCandidate]:
        """按查询词 + 地域搜候选人 (返回轻量画像)。

        Args:
            q: 技术栈 / 关键词查询串 (源特定语法由实现拼接)。
            location: 城市过滤。
            limit: 最多返回数。
        """
        ...

    @abstractmethod
    async def get_user_profile(self, username: str) -> SourcedCandidate | None:
        """拉单个候选人的完整画像 (含技能/语言/影响力)。"""
        ...

    async def search_by_profile(
        self,
        profile: JobProfile,
        *,
        limit: int = 50,
    ) -> list[SourcedCandidate]:
        """便捷入口: 用岗位画像组装查询串再搜。子类可覆盖以用源特定语法。"""
        q = " ".join(profile.query_terms()[:4])
        return await self.search_users(q=q, location=profile.location, limit=limit)
