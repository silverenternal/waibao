"""Tests for candidate_recommender (T1304)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fake_supabase(role=None, candidates=None, raise_role=False, raise_cand=False):
    """构造一个最小 supabase mock,满足 recommender 的调用."""
    sb = MagicMock()
    if raise_role:
        sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("role fetch failed")
    else:
        sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=role)
    if raise_cand:
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("candidate fetch failed")
    else:
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=candidates or [])
    return sb


def _role_dict(**overrides):
    base = dict(
        id="r1",
        title="Senior Backend",
        required_skills=[
            {"name": "python", "min_years": 3, "importance": "required"},
            {"name": "django", "importance": "required"},
        ],
        preferred_skills=[
            {"name": "kubernetes", "importance": "preferred"},
        ],
        seniority="senior",
        remote_policy="remote",
        city="Shanghai",
        salary_min=30_000,
        salary_max=60_000,
        currency="CNY",
    )
    base.update(overrides)
    return base


def _candidate_dict(**overrides):
    base = dict(
        id="c1",
        full_name="Alice",
        headline="Senior Python Engineer",
        city="Shanghai",
        seniority="senior",
        extracted_skills=[
            {"name": "python", "years": 5, "confidence": 0.95},
            {"name": "django", "years": 4},
            {"name": "kubernetes", "years": 2},
        ],
        years_experience=7,
        availability_status="1_month",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# recommend_to_employer
# ---------------------------------------------------------------------------


class TestRecommendToEmployer:
    @pytest.mark.asyncio
    async def test_returns_recommended_candidates(self):
        from services.candidate_recommender import CandidateRecommender

        sb = _fake_supabase(role=_role_dict(), candidates=[_candidate_dict()])
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert len(result) == 1
        c = result[0]
        assert c.candidate_id == "c1"
        assert c.full_name == "Alice"
        assert c.overall_score > 0.5
        assert c.confidence in ("strong", "good", "possible")
        # 匹配了所有 required + preferred
        assert "python" in c.skills
        assert "django" in c.skills

    @pytest.mark.asyncio
    async def test_role_not_found_returns_empty(self):
        from services.candidate_recommender import CandidateRecommender

        sb = _fake_supabase(role=None, candidates=[])
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("missing", limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_supabase_failure_returns_empty(self):
        from services.candidate_recommender import CandidateRecommender

        sb = _fake_supabase(raise_role=True)
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_skills_listed(self):
        from services.candidate_recommender import CandidateRecommender

        cand = _candidate_dict(
            extracted_skills=[{"name": "python", "years": 3}],
        )
        sb = _fake_supabase(role=_role_dict(), candidates=[cand])
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert len(result) == 1
        assert "django" in result[0].missing_skills

    @pytest.mark.asyncio
    async def test_seniority_match(self):
        from services.candidate_recommender import CandidateRecommender

        # senior ↔ senior → strong
        sb = _fake_supabase(
            role=_role_dict(seniority="senior"),
            candidates=[_candidate_dict(seniority="senior")],
        )
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert len(result) == 1
        assert any("seniority" in r for r in result[0].reasons)

    @pytest.mark.asyncio
    async def test_over_qualified_candidate_still_recommended(self):
        from services.candidate_recommender import CandidateRecommender

        # role=mid, candidate=principal -> over-qualified
        sb = _fake_supabase(
            role=_role_dict(seniority="mid"),
            candidates=[_candidate_dict(seniority="principal", years_experience=15)],
        )
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert len(result) == 1
        # experience_score 仍 > 0.5
        assert result[0].experience_score > 0.5

    @pytest.mark.asyncio
    async def test_limit_truncates_results(self):
        from services.candidate_recommender import CandidateRecommender

        cands = [
            _candidate_dict(id=f"c{i}", years_experience=10 - i)
            for i in range(5)
        ]
        sb = _fake_supabase(role=_role_dict(), candidates=cands)
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_results_sorted_desc(self):
        from services.candidate_recommender import CandidateRecommender

        cands = [
            _candidate_dict(id="lo", extracted_skills=[{"name": "python", "years": 1}]),
            _candidate_dict(
                id="hi",
                extracted_skills=[
                    {"name": "python", "years": 8},
                    {"name": "django", "years": 6},
                    {"name": "kubernetes", "years": 4},
                ],
                years_experience=10,
            ),
        ]
        sb = _fake_supabase(role=_role_dict(), candidates=cands)
        rec = CandidateRecommender(supabase=sb)
        result = await rec.recommend_to_employer("r1", limit=10)
        assert len(result) == 2
        assert result[0].overall_score >= result[1].overall_score
        assert result[0].candidate_id == "hi"


# ---------------------------------------------------------------------------
# recommend_for_active_roles
# ---------------------------------------------------------------------------


class TestRecommendForActiveRoles:
    @pytest.mark.asyncio
    async def test_returns_dict_per_role(self):
        from services.candidate_recommender import CandidateRecommender

        sb = MagicMock()
        # 1) .table("roles").select("id").eq("status","active").limit(N).execute()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "r1"}, {"id": "r2"}]
        )
        rec = CandidateRecommender(supabase=sb)
        # patch recommend_to_employer to return known list
        async def fake_recommend(role_id, *, limit=20):
            return []
        rec.recommend_to_employer = fake_recommend  # type: ignore
        out = await rec.recommend_for_active_roles()
        assert set(out.keys()) == {"r1", "r2"}

    @pytest.mark.asyncio
    async def test_supabase_failure_returns_empty(self):
        from services.candidate_recommender import CandidateRecommender

        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("fail")
        rec = CandidateRecommender(supabase=sb)
        out = await rec.recommend_for_active_roles()
        assert out == {}
