"""MockJobMarketProvider — 离线可跑的招聘市场 mock (T607).

数据源: 内置 10 岗位 × 6 城市 × 4 槽位 = 240 条,完全确定性,不联网.
用于:
    1. 单元测试
    2. 后端无网络环境运行
    3. 上线前真实 API 接入前的兜底(所有真实 provider 失败时回退到这里)

缓存: 1 小时内存缓存,防止高频调用 (T607 质量要求)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..base import RetryPolicy, with_resilience
from .base import JobMarketProvider
from .types import JobPosting, SalaryPoint, SkillDemand

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 静态数据池 — 真实场景下由 API 替换
# ---------------------------------------------------------------------------
_MOCK_COMPANIES = [
    "智云科技", "新潮互娱", "数链金融", "慧舟教育", "蓝象医疗",
    "极光出行", "栖梧文化", "象限电商", "穹宇物流", "云策数据",
    "星河游戏", "海图地理", "远见制造", "扬帆跨境", "拓荒机器人",
]

_MOCK_CITIES = ["北京", "上海", "深圳", "杭州", "成都", "广州"]

# 10 个岗位 — 覆盖前后端 / 数据 / 算法 / 产品 / 设计 / 运维 / 测试 / 安全 / 嵌入式 / 销售
_MOCK_ROLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "python": {
        "title": "Python 后端工程师",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
        "salary_base": (18, 35),
    },
    "frontend": {
        "title": "前端工程师",
        "skills": ["TypeScript", "React", "Next.js", "Tailwind"],
        "salary_base": (16, 30),
    },
    "data": {
        "title": "数据分析师",
        "skills": ["SQL", "Python", "Pandas", "BI"],
        "salary_base": (14, 28),
    },
    "product": {
        "title": "产品经理",
        "skills": ["Axure", "用户调研", "数据分析"],
        "salary_base": (15, 32),
    },
    "algorithm": {
        "title": "算法工程师",
        "skills": ["PyTorch", "LLM", "RAG", "向量检索"],
        "salary_base": (25, 50),
    },
    "design": {
        "title": "UI/UX 设计师",
        "skills": ["Figma", "设计系统", "用户访谈"],
        "salary_base": (12, 25),
    },
    "ops": {
        "title": "运维工程师",
        "skills": ["Kubernetes", "Linux", "Prometheus"],
        "salary_base": (14, 26),
    },
    "qa": {
        "title": "测试工程师",
        "skills": ["Pytest", "Playwright", "接口测试"],
        "salary_base": (10, 22),
    },
    "security": {
        "title": "安全工程师",
        "skills": ["渗透测试", "OWASP", "代码审计"],
        "salary_base": (20, 40),
    },
    "embedded": {
        "title": "嵌入式工程师",
        "skills": ["C", "RTOS", "STM32"],
        "salary_base": (16, 30),
    },
    "sales": {
        "title": "解决方案销售",
        "skills": ["客户拜访", "招投标", "SaaS"],
        "salary_base": (12, 30),
    },
}

# 7 额外角色 — 用于 keyword 模糊匹配(扩展覆盖到 10 个细分领域)
_MOCK_ROLE_ALIASES: dict[str, str] = {
    "go": "python",  # 复用 python 模板 (mock 不区分后端语言)
    "java": "python",
    "rust": "python",
    "react": "frontend",
    "vue": "frontend",
    "ios": "frontend",
    "android": "frontend",
    "llm": "algorithm",
    "nlp": "algorithm",
    "cv": "algorithm",
    "pm": "product",
    "运营": "product",
    "交互": "design",
    "视觉": "design",
    "sre": "ops",
    "devops": "ops",
    "sdET": "qa",
    "自动化测试": "qa",
    "安全": "security",
    "渗透": "security",
    "嵌入式": "embedded",
    "单片机": "embedded",
    "销售": "sales",
    "bd": "sales",
    "客户成功": "sales",
}

_MOCK_SKILL_BANK = [
    "Python", "TypeScript", "Rust", "Go", "Java", "Kubernetes",
    "FastAPI", "Next.js", "PostgreSQL", "Redis", "PyTorch", "LLM",
    "RAG", "向量检索", "Figma", "SQL", "Pandas", "React", "Vue",
    "Docker", "Linux", "Prometheus", "OWASP", "Pytest", "Playwright",
]

# 全国岗位池 (240 条) — 缓存到磁盘供外部读取
_MOCK_CACHE_FILE = Path(
    os.getenv("JOB_MARKET_MOCK_CACHE_FILE", "/tmp/waibao_mock_jobs.json"),
)
_MOCK_CACHE_TTL_SEC = 3600.0  # 1 小时


def _stable_int(seed: str, mod: int, salt: str = "") -> int:
    """基于 keyword 生成稳定的 0..mod-1 整数."""
    h = hashlib.sha256(f"{salt}::{seed}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def _infer_role_key(keyword: str) -> str:
    """根据 keyword 推断 role key."""
    kw = keyword.lower().strip()
    if not kw:
        return "python"
    # 1) 直接命中 _MOCK_ROLE_TEMPLATES (role_key 或 title 包含 keyword)
    for key, tmpl in _MOCK_ROLE_TEMPLATES.items():
        title = tmpl["title"]
        if key in kw or kw in title.lower() or keyword in title:
            return key
    # 2) 别名映射
    for alias, role_key in _MOCK_ROLE_ALIASES.items():
        if alias in kw or alias in keyword or keyword in alias:
            return role_key
    return "python"


def _build_pool() -> list[JobPosting]:
    """一次性生成 10 角色 × 6 城市 × 4 槽 = 240 条岗位池."""
    pool: list[JobPosting] = []
    for role_key, tmpl in _MOCK_ROLE_TEMPLATES.items():
        for city in _MOCK_CITIES:
            for i in range(4):
                idx = _stable_int(f"{role_key}::{city}::{i}", 1000, salt="pool")
                company = _MOCK_COMPANIES[idx % len(_MOCK_COMPANIES)]
                sal_min, sal_max = tmpl["salary_base"]
                low = round(sal_min * (0.85 + (idx % 30) / 100), 1)
                high = round(sal_max * (0.85 + ((idx // 7) % 30) / 100), 1)
                posted = datetime.now(tz=timezone.utc) - timedelta(days=idx % 30)
                pool.append(JobPosting(
                    source="mock",
                    external_id=f"mock-{role_key}-{city}-{i}",
                    title=tmpl["title"],
                    company=company,
                    city=city,
                    salary_min_k=low,
                    salary_max_k=high,
                    salary_currency="CNY",
                    experience_years=f"{3 + (idx % 5)}-{5 + (idx % 5)}年",
                    education="本科",
                    skills=list(tmpl["skills"]),
                    url=f"https://mock.local/jobs/{role_key}-{city}-{i}",
                    posted_at=posted.isoformat(),
                    description_snippet=(
                        f"【{company}】诚招 {tmpl['title']},团队氛围好,"
                        f"核心技术栈:{','.join(tmpl['skills'])}。"
                    ),
                    raw={"role_key": role_key, "city": city, "slot": i},
                ))
    return pool


class MockJobMarketProvider(JobMarketProvider):
    """纯本地 mock,不联网,数据完全确定性.

    内存缓存 1 小时 (T607 质量要求),避免高频请求压垮上游.
    """

    provider_name = "mock"

    def __init__(self, *, seed: str = "waibao-v3") -> None:
        self._seed = seed
        self._cache: dict[str, tuple[float, Any]] = {}
        self._persist_path: Path | None = (
            _MOCK_CACHE_FILE if _MOCK_CACHE_FILE.exists() else None
        )

    # ------------------------------------------------------------------
    # 内部缓存
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> Any | None:
        item = self._cache.get(key)
        if item is None:
            return None
        ts, value = item
        if time.monotonic() - ts > _MOCK_CACHE_TTL_SEC:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_put(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    # ------------------------------------------------------------------
    # search_jobs
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market",
        method="search_jobs",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def search_jobs(
        self,
        keyword: str,
        *,
        city: str | None = None,
        salary_range: tuple[float, float] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[JobPosting]:
        if not keyword:
            return []
        role_key = _infer_role_key(keyword)
        tmpl = _MOCK_ROLE_TEMPLATES[role_key]
        cache_key = f"search::{role_key}::{city or 'all'}::{salary_range or 'all'}::{page_size}"
        cached = self._cache_get(cache_key)
        if cached is not None and page >= 1:
            start = (page - 1) * page_size
            return cached[start: start + page_size]

        cities = [city] if city else _MOCK_CITIES
        pool: list[JobPosting] = []
        for c in cities:
            for i in range(4):
                idx = _stable_int(f"{keyword}::{c}::{i}", 1000, salt=self._seed)
                company = _MOCK_COMPANIES[idx % len(_MOCK_COMPANIES)]
                sal_min, sal_max = tmpl["salary_base"]
                low = round(sal_min * (0.85 + (idx % 30) / 100), 1)
                high = round(sal_max * (0.85 + ((idx // 7) % 30) / 100), 1)
                posted = datetime.now(tz=timezone.utc) - timedelta(days=idx % 30)
                pool.append(JobPosting(
                    source="mock",
                    external_id=f"mock-{role_key}-{c}-{i}",
                    title=tmpl["title"],
                    company=company,
                    city=c,
                    salary_min_k=low,
                    salary_max_k=high,
                    salary_currency="CNY",
                    experience_years=f"{3 + (idx % 5)}-{5 + (idx % 5)}年",
                    education="本科",
                    skills=list(tmpl["skills"]),
                    url=f"https://mock.local/jobs/{role_key}-{c}-{i}",
                    posted_at=posted.isoformat(),
                    description_snippet=(
                        f"【{company}】诚招 {tmpl['title']},团队氛围好,"
                        f"核心技术栈:{','.join(tmpl['skills'])}。"
                    ),
                    raw={"role_key": role_key, "city": c, "slot": i},
                ))

        if salary_range is not None:
            lo, hi = salary_range
            pool = [
                j for j in pool
                if j.salary_max_k is not None
                and j.salary_min_k is not None
                and j.salary_min_k >= lo
                and j.salary_max_k <= hi
            ]

        self._cache_put(cache_key, pool)
        start = (page - 1) * page_size
        end = start + page_size
        return pool[start:end]

    # ------------------------------------------------------------------
    # get_salary_trend
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market",
        method="get_salary_trend",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_salary_trend(
        self,
        role: str,
        city: str,
        *,
        months: int = 12,
    ) -> list[SalaryPoint]:
        role_key = _infer_role_key(role)
        base_med = (_MOCK_ROLE_TEMPLATES[role_key]["salary_base"][0]
                    + _MOCK_ROLE_TEMPLATES[role_key]["salary_base"][1]) / 2
        city_factor = 1.1 if city in ("北京", "上海", "深圳", "广州") else 0.95
        base_med *= city_factor

        cache_key = f"salary::{role_key}::{city}::{months}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        now = datetime.now(tz=timezone.utc).replace(day=1)
        out: list[SalaryPoint] = []
        for m in range(months - 1, -1, -1):
            period_dt = now - timedelta(days=30 * m)
            period = period_dt.strftime("%Y-%m")
            jitter = 1.0 + (
                (_stable_int(role + city + period, 100, salt=self._seed)) % 7 - 3
            ) / 100
            median = round(base_med * jitter, 1)
            out.append(SalaryPoint(
                period=period,
                median_k=median,
                p25_k=round(median * 0.8, 1),
                p75_k=round(median * 1.2, 1),
                sample_size=200 + _stable_int(period + role + city, 800, salt=self._seed),
                currency="CNY",
            ))
        self._cache_put(cache_key, out)
        return out

    # ------------------------------------------------------------------
    # get_hot_skills
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market",
        method="get_hot_skills",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_hot_skills(
        self,
        role: str | None = None,
        *,
        limit: int = 20,
    ) -> list[SkillDemand]:
        cache_key = f"hot_skills::{role or 'all'}::{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if role:
            tmpl_skills = _MOCK_ROLE_TEMPLATES.get(
                _infer_role_key(role), _MOCK_ROLE_TEMPLATES["python"],
            )["skills"]
            skills_iter = tmpl_skills
        else:
            skills_iter = _MOCK_SKILL_BANK

        out: list[SkillDemand] = []
        for i, skill in enumerate(skills_iter):
            score = 90 - i * 4 + (_stable_int(skill, 11, salt=self._seed) - 5)
            score = max(5, min(100, score))
            out.append(SkillDemand(
                skill=skill,
                demand_score=float(score),
                job_count=1000 + _stable_int(skill + "cnt", 5000, salt=self._seed),
                growth_pct=round(((_stable_int(skill + "growth", 41, salt=self._seed)) - 20), 1),
            ))
        out.sort(key=lambda s: s.demand_score, reverse=True)
        result = out[:limit]
        self._cache_put(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # 工具: 一次性导出完整 240 条池 (用于存档 / 测试 / 兜底)
    # ------------------------------------------------------------------
    def export_full_pool(self) -> list[dict[str, Any]]:
        """导出 240 条岗位的 dict 形式 (供前端 mock / 测试使用)."""
        pool = _build_pool()
        return [
            {
                "source": j.source,
                "external_id": j.external_id,
                "title": j.title,
                "company": j.company,
                "city": j.city,
                "salary_min_k": j.salary_min_k,
                "salary_max_k": j.salary_max_k,
                "salary_currency": j.salary_currency,
                "experience_years": j.experience_years,
                "education": j.education,
                "skills": j.skills,
                "url": j.url,
                "posted_at": j.posted_at,
                "description_snippet": j.description_snippet,
            }
            for j in pool
        ]

    def export_to_disk(self) -> None:
        """写入 _MOCK_CACHE_FILE,便于离线 / 测试场景直接读 JSON."""
        if not _MOCK_CACHE_FILE:
            return
        payload = self.export_full_pool()
        _MOCK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MOCK_CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("mock.export_to_disk path=%s size=%d", _MOCK_CACHE_FILE, len(payload))


# 启动时一次性导出 (便于离线场景下其他服务直接读 JSON)
def export_default_pool_to_disk() -> None:
    """模块级导出 240 条 mock 岗位到磁盘."""
    MockJobMarketProvider().export_to_disk()