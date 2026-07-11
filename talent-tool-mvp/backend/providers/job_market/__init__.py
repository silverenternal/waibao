"""招聘市场 Provider 抽象 (T607)."""
from __future__ import annotations

from .adzuna import AdzunaProvider
from .base import (
    JobMarketProvider,
    JobPosting,
    SalaryPoint,
    SkillDemand,
)
from .boss_zhipin import BossZhipinProvider
from .lagou import LagouProvider
from .linkedin import LinkedInProvider
from .mock import MockJobMarketProvider
from .registry import get_job_market_provider, reset_job_market_cache

__all__ = [
    "AdzunaProvider",
    "BossZhipinProvider",
    "JobMarketProvider",
    "JobPosting",
    "LagouProvider",
    "LinkedInProvider",
    "MockJobMarketProvider",
    "SalaryPoint",
    "SkillDemand",
    "get_job_market_provider",
    "reset_job_market_cache",
]