"""T3002: AI 主动 Sourcing (Outbound) provider 层.

从 GitHub 等外部源主动发掘候选人。切换源只需改 SOURCING_PROVIDER 环境变量。

    from providers.sourcing import get_sourcing_provider
    provider = get_sourcing_provider()
    candidates = await provider.search_users(q="Go Kubernetes", location="北京")
"""
from __future__ import annotations

from .base import SourcingProvider
from .github import GitHubSourcingProvider
from .mock import MockSourcingProvider
from .registry import get_sourcing_provider, reset_sourcing_cache
from .types import (
    JobProfile,
    MatchScore,
    ScoredCandidate,
    SourcedCandidate,
)

__all__ = [
    "GitHubSourcingProvider",
    "JobProfile",
    "MatchScore",
    "MockSourcingProvider",
    "ScoredCandidate",
    "SourcedCandidate",
    "SourcingProvider",
    "get_sourcing_provider",
    "reset_sourcing_cache",
]
