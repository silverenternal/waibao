"""T3002: GitHub Sourcing Provider.

用 GitHub REST API (search/users + users/{login}) 主动发掘开发者候选人。

    GET /search/users?q=<query>+location:<city>   → 候选人列表
    GET /users/{login}                             → 单个画像
    GET /users/{login}/repos                       → 语言分布 (top_languages)

无 GITHUB_TOKEN 时匿名调用 (rate limit 更严), 上游失败由 with_resilience 处理;
调用方 (sourcing_agent) 会在异常时回退到 mock。
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import UpstreamUnavailableError
from .base import SourcingProvider
from .types import SourcedCandidate

logger = logging.getLogger("recruittech.providers.sourcing.github")

GITHUB_API = "https://api.github.com"


class GitHubSourcingProvider(SourcingProvider):
    """GitHub 开发者 sourcing。"""

    provider_name = "github"

    def __init__(self, token: str | None = None, *, timeout: float = 15.0) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    @with_resilience(provider="github", method="search", rate_per_sec=5.0, burst=10)
    async def search_users(
        self,
        *,
        q: str,
        location: str | None = None,
        limit: int = 50,
    ) -> list[SourcedCandidate]:
        query = q.strip()
        if location:
            query += f" location:{location}"
        params = {"q": query, "per_page": min(limit, 100), "sort": "followers", "order": "desc"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GITHUB_API}/search/users", params=params, headers=self._headers()
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(str(exc), provider="github") from exc

        out: list[SourcedCandidate] = []
        for item in data.get("items", [])[:limit]:
            out.append(
                SourcedCandidate(
                    id=f"github:{item.get('login')}",
                    source="github",
                    name=item.get("login", ""),
                    profile_url=item.get("html_url"),
                    avatar_url=item.get("avatar_url"),
                    raw={"login": item.get("login")},
                )
            )
        return out

    @with_resilience(provider="github", method="profile", rate_per_sec=8.0, burst=16)
    async def get_user_profile(self, username: str) -> SourcedCandidate | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{GITHUB_API}/users/{username}", headers=self._headers()
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                user = resp.json()
                langs = await self._top_languages(client, username)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(str(exc), provider="github") from exc

        return SourcedCandidate(
            id=f"github:{user.get('login')}",
            source="github",
            name=user.get("name") or user.get("login", ""),
            headline=user.get("bio"),
            location=user.get("location"),
            company=user.get("company"),
            email=user.get("email"),
            profile_url=user.get("html_url"),
            avatar_url=user.get("avatar_url"),
            followers=int(user.get("followers", 0) or 0),
            public_repos=int(user.get("public_repos", 0) or 0),
            skills=langs,
            top_languages=langs,
            raw=user,
        )

    async def _top_languages(self, client: httpx.AsyncClient, username: str) -> list[str]:
        """从公开 repos 统计主要语言 (top 5)。"""
        try:
            resp = await client.get(
                f"{GITHUB_API}/users/{username}/repos",
                params={"per_page": 100, "sort": "pushed"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            repos = resp.json()
        except httpx.HTTPError:
            return []
        counter: Counter[str] = Counter()
        for r in repos:
            lang = r.get("language")
            if lang:
                counter[lang] += 1
        return [lang for lang, _ in counter.most_common(5)]
