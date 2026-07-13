"""T3002: Mock Sourcing Provider — 50+ 国内候选人 (无需外部凭证).

用于开发/测试/演示: 生成一批贴近国内技术圈的候选人画像,
覆盖主流技术栈 (后端/前端/算法/移动/数据/SRE) 与一二线城市。
"""
from __future__ import annotations

import random
from typing import Any

from .base import SourcingProvider
from .types import SourcedCandidate

_CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都", "南京", "武汉", "西安", "苏州"]

_STACKS: dict[str, list[str]] = {
    "后端工程师": ["Java", "Go", "Python", "Spring", "MySQL", "Redis", "Kafka"],
    "前端工程师": ["JavaScript", "TypeScript", "React", "Vue", "Webpack", "Node.js"],
    "算法工程师": ["Python", "PyTorch", "TensorFlow", "CUDA", "NLP", "CV"],
    "移动端工程师": ["Kotlin", "Swift", "Flutter", "Android", "iOS"],
    "数据工程师": ["Spark", "Flink", "Hive", "ClickHouse", "Python", "SQL"],
    "SRE": ["Kubernetes", "Docker", "Prometheus", "Go", "Linux", "Terraform"],
    "大模型工程师": ["Python", "PyTorch", "vLLM", "LLaMA-Factory", "LangChain", "CUDA"],
}

_COMPANIES = [
    "字节跳动", "阿里巴巴", "腾讯", "美团", "百度", "蚂蚁集团", "京东", "网易",
    "小米", "快手", "拼多多", "滴滴", "华为", "商汤科技", "旷视科技", "月之暗面",
]

_SURNAMES = "王李张刘陈杨黄赵周吴徐孙马朱胡林郭何高罗"
_GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "洋", "勇", "艳", "杰", "涛", "明", "超", "霞", "平", "刚", "桂英"]


def _gen_name(rng: random.Random) -> str:
    return rng.choice(_SURNAMES) + "".join(rng.sample(_GIVEN, k=rng.randint(1, 2)))


def _build_pool(n: int = 60, *, seed: int = 20260713) -> list[SourcedCandidate]:
    rng = random.Random(seed)
    roles = list(_STACKS.keys())
    pool: list[SourcedCandidate] = []
    for i in range(n):
        role = roles[i % len(roles)]
        stack = _STACKS[role]
        skills = rng.sample(stack, k=rng.randint(3, min(5, len(stack))))
        years = rng.randint(1, 14)
        city = rng.choice(_CITIES)
        company = rng.choice(_COMPANIES)
        name = _gen_name(rng)
        login = f"dev_{role[:2]}_{i:03d}"
        pool.append(
            SourcedCandidate(
                id=f"mock:{login}",
                source="mock",
                name=name,
                headline=f"{years} 年 {role} @ {company}",
                location=city,
                skills=skills,
                years_experience=years,
                company=company,
                profile_url=f"https://example.com/candidates/{login}",
                avatar_url=f"https://i.pravatar.cc/150?u={login}",
                followers=rng.randint(0, 3000),
                public_repos=rng.randint(0, 120),
                top_languages=skills[:3],
                raw={"role": role, "login": login},
            )
        )
    return pool


class MockSourcingProvider(SourcingProvider):
    """内存 mock: 60 个国内候选人, 支持按关键词 + 地域过滤。"""

    provider_name = "mock"

    def __init__(self, *, size: int = 60) -> None:
        self._pool = _build_pool(size)

    @property
    def pool(self) -> list[SourcedCandidate]:
        return self._pool

    async def search_users(
        self,
        *,
        q: str,
        location: str | None = None,
        limit: int = 50,
    ) -> list[SourcedCandidate]:
        terms = [t.lower() for t in q.replace(",", " ").split() if t]
        results: list[tuple[int, SourcedCandidate]] = []
        for c in self._pool:
            if location and c.location != location:
                continue
            hay = " ".join([*(s.lower() for s in c.skills), (c.headline or "").lower()])
            hits = sum(1 for t in terms if t in hay)
            if not terms or hits > 0:
                results.append((hits, c))
        # 命中数降序, 其次 followers 降序
        results.sort(key=lambda x: (x[0], x[1].followers), reverse=True)
        return [c for _, c in results[:limit]]

    async def get_user_profile(self, username: str) -> SourcedCandidate | None:
        key = username.split(":", 1)[-1]
        for c in self._pool:
            if c.raw.get("login") == key or c.id.endswith(key) or c.name == username:
                return c
        return None
