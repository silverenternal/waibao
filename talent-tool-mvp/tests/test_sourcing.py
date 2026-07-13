"""T3002: AI 主动 Sourcing 测试.

覆盖:
  * types — JobProfile.query_terms / MatchScore.overall 加权
  * mock provider — 50+ 候选人 / 关键词 + 地域过滤 / profile 回查
  * github provider — 查询串拼接 (location) / 解析 (httpx mock)
  * sourcing_agent — 5 维打分 / 排序 / target 补齐 / 详情缓存 / 上游失败回退
"""
from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from providers.sourcing import (  # noqa: E402
    GitHubSourcingProvider,
    JobProfile,
    MatchScore,
    MockSourcingProvider,
    SourcedCandidate,
    get_sourcing_provider,
    reset_sourcing_cache,
)
from services.platform.sourcing_agent import (  # noqa: E402
    SourcingAgent,
    get_sourcing_agent,
    reset_sourcing_agent,
    score_candidate,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_sourcing_cache()
    reset_sourcing_agent()
    yield
    reset_sourcing_cache()
    reset_sourcing_agent()


# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------
class TestTypes:
    def test_query_terms(self):
        p = JobProfile(title="后端", skills=["Go", "Redis"], keywords=["分布式"])
        terms = p.query_terms()
        assert "Go" in terms and "Redis" in terms and "分布式" in terms and "后端" in terms

    def test_match_score_overall_weighting(self):
        s = MatchScore(skill=100, experience=100, location=100, activity=100, seniority=100)
        assert s.overall == 100.0
        s2 = MatchScore(skill=100, experience=0, location=0, activity=0, seniority=0)
        assert s2.overall == 40.0  # skill 权重 0.40

    def test_scored_candidate_to_dict(self):
        c = SourcedCandidate(id="mock:x", source="mock", name="张三", skills=["Go"])
        sc = score_candidate(JobProfile(title="后端", skills=["Go"]), c)
        d = sc.to_dict()
        assert d["id"] == "mock:x"
        assert "match" in d and "overall" in d["match"]
        assert "reasons" in d


# ---------------------------------------------------------------------------
# mock provider
# ---------------------------------------------------------------------------
class TestMockProvider:
    @pytest.mark.asyncio
    async def test_pool_has_50_plus(self):
        p = MockSourcingProvider()
        assert len(p.pool) >= 50

    @pytest.mark.asyncio
    async def test_search_keyword_filter(self):
        p = MockSourcingProvider()
        res = await p.search_users(q="PyTorch", limit=50)
        assert res
        assert all(
            any("pytorch" in s.lower() for s in c.skills) or "pytorch" in (c.headline or "").lower()
            for c in res
        )

    @pytest.mark.asyncio
    async def test_search_location_filter(self):
        p = MockSourcingProvider()
        res = await p.search_users(q="", location="上海", limit=50)
        assert res
        assert all(c.location == "上海" for c in res)

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_all(self):
        p = MockSourcingProvider()
        res = await p.search_users(q="", limit=200)
        assert len(res) == len(p.pool)

    @pytest.mark.asyncio
    async def test_get_user_profile(self):
        p = MockSourcingProvider()
        first = p.pool[0]
        got = await p.get_user_profile(first.raw["login"])
        assert got is not None and got.id == first.id

    @pytest.mark.asyncio
    async def test_get_user_profile_missing(self):
        p = MockSourcingProvider()
        assert await p.get_user_profile("nonexistent-xyz") is None

    @pytest.mark.asyncio
    async def test_candidates_are_domestic(self):
        p = MockSourcingProvider()
        cities = {c.location for c in p.pool}
        assert cities & {"北京", "上海", "深圳", "杭州"}


# ---------------------------------------------------------------------------
# github provider
# ---------------------------------------------------------------------------
class TestGitHubProvider:
    @pytest.mark.asyncio
    async def test_search_builds_query_with_location(self, monkeypatch):
        captured = {}

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"items": [{"login": "octocat", "html_url": "u", "avatar_url": "a"}]}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None, headers=None):
                captured["params"] = params
                return _Resp()

        import providers.sourcing.github as gh

        monkeypatch.setattr(gh.httpx, "AsyncClient", _Client)
        prov = GitHubSourcingProvider(token="")
        res = await prov.search_users(q="Go Kubernetes", location="Beijing", limit=10)
        assert "location:Beijing" in captured["params"]["q"]
        assert res[0].id == "github:octocat"
        assert res[0].source == "github"

    @pytest.mark.asyncio
    async def test_get_profile_parses_fields(self, monkeypatch):
        class _Resp:
            def __init__(self, payload, code=200):
                self._p = payload
                self.status_code = code

            def raise_for_status(self):
                pass

            def json(self):
                return self._p

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None, headers=None):
                if url.endswith("/repos"):
                    return _Resp([{"language": "Go"}, {"language": "Go"}, {"language": "Python"}])
                return _Resp(
                    {
                        "login": "octocat",
                        "name": "Octo Cat",
                        "bio": "hacker",
                        "location": "Shanghai",
                        "followers": 500,
                        "public_repos": 42,
                        "html_url": "u",
                        "avatar_url": "a",
                    }
                )

        import providers.sourcing.github as gh

        monkeypatch.setattr(gh.httpx, "AsyncClient", _Client)
        prov = GitHubSourcingProvider(token="tok")
        c = await prov.get_user_profile("octocat")
        assert c is not None
        assert c.name == "Octo Cat" and c.followers == 500
        assert "Go" in c.top_languages

    @pytest.mark.asyncio
    async def test_get_profile_404(self, monkeypatch):
        class _Resp:
            status_code = 404

            def raise_for_status(self):
                pass

            def json(self):
                return {}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, params=None, headers=None):
                return _Resp()

        import providers.sourcing.github as gh

        monkeypatch.setattr(gh.httpx, "AsyncClient", _Client)
        prov = GitHubSourcingProvider(token="")
        assert await prov.get_user_profile("ghost") is None


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
class TestScoring:
    def test_skill_overlap_scores_high(self):
        c = SourcedCandidate(id="mock:a", source="mock", name="A", skills=["Go", "Redis", "Kafka"])
        p = JobProfile(title="后端", skills=["Go", "Redis"])
        sc = score_candidate(p, c)
        assert sc.score.skill == 100.0

    def test_location_match(self):
        c = SourcedCandidate(id="mock:a", source="mock", name="A", location="北京")
        p = JobProfile(title="后端", location="北京")
        assert score_candidate(p, c).score.location == 100.0
        p2 = JobProfile(title="后端", location="上海")
        assert score_candidate(p2, c).score.location < 100.0

    def test_experience_below_min_penalized(self):
        c = SourcedCandidate(id="mock:a", source="mock", name="A", years_experience=1)
        p = JobProfile(title="后端", min_years=5)
        low = score_candidate(p, c).score.experience
        c2 = SourcedCandidate(id="mock:b", source="mock", name="B", years_experience=8)
        high = score_candidate(p, c2).score.experience
        assert high > low

    def test_reasons_generated(self):
        c = SourcedCandidate(
            id="mock:a", source="mock", name="A", skills=["Go"], location="北京", years_experience=6
        )
        p = JobProfile(title="后端", skills=["Go"], location="北京", min_years=3)
        reasons = score_candidate(p, c).reasons
        assert any("技能命中" in r for r in reasons)
        assert any("北京" in r for r in reasons)


# ---------------------------------------------------------------------------
# sourcing agent
# ---------------------------------------------------------------------------
class TestSourcingAgent:
    @pytest.mark.asyncio
    async def test_source_returns_target_and_sorted(self):
        agent = SourcingAgent(provider=MockSourcingProvider(size=120))
        p = JobProfile(title="后端工程师", skills=["Go", "Kubernetes"], location="北京", min_years=3)
        res = await agent.source(p, target=100)
        assert len(res) == 100
        overalls = [s.score.overall for s in res]
        assert overalls == sorted(overalls, reverse=True)

    @pytest.mark.asyncio
    async def test_candidate_detail_cached(self):
        agent = SourcingAgent(provider=MockSourcingProvider(size=80))
        p = JobProfile(title="算法工程师", skills=["PyTorch"])
        res = await agent.source(p, target=30)
        cid = res[0].candidate.id
        got = agent.get_candidate(cid)
        assert got is not None and got.candidate.id == cid

    @pytest.mark.asyncio
    async def test_unknown_candidate_returns_none(self):
        agent = SourcingAgent(provider=MockSourcingProvider())
        assert agent.get_candidate("mock:does-not-exist") is None

    @pytest.mark.asyncio
    async def test_falls_back_to_mock_on_provider_error(self):
        class _Broken(MockSourcingProvider):
            async def search_by_profile(self, profile, *, limit=50):
                raise RuntimeError("upstream down")

        agent = SourcingAgent(provider=_Broken())
        p = JobProfile(title="SRE", skills=["Kubernetes"])
        res = await agent.source(p, target=20)
        assert len(res) == 20  # 回退 mock 填充

    @pytest.mark.asyncio
    async def test_singleton(self):
        a1 = get_sourcing_agent()
        a2 = get_sourcing_agent()
        assert a1 is a2


# ---------------------------------------------------------------------------
# provider registry
# ---------------------------------------------------------------------------
def test_registry_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("SOURCING_PROVIDER", raising=False)
    reset_sourcing_cache()
    p = get_sourcing_provider()
    assert isinstance(p, MockSourcingProvider)


def test_registry_github(monkeypatch):
    monkeypatch.setenv("SOURCING_PROVIDER", "github")
    reset_sourcing_cache()
    p = get_sourcing_provider()
    assert isinstance(p, GitHubSourcingProvider)
    reset_sourcing_cache()
