"""Tests for job_subscription (T1304)."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def service():
    from services.job_subscription import JobSubscriptionService
    return JobSubscriptionService(supabase=None)


def _sample_job(**overrides):
    from services.job_subscription import JobPosting
    base = dict(
        id="job-1",
        title="Senior Backend Engineer",
        company="Acme",
        city="Shanghai",
        salary_min=30_000,
        salary_max=50_000,
        currency="CNY",
        skills=["python", "django", "postgres"],
        seniority="senior",
        remote_policy="hybrid",
    )
    base.update(overrides)
    return JobPosting(**base)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_create_and_list(self, service):
        sub = service.create(
            user_id="u1",
            name="Shanghai Python",
            criteria={"role": "engineer", "city": "Shanghai", "skills": ["python"]},
            channels=["web", "email"],
        )
        assert sub.id
        assert sub.user_id == "u1"
        assert sub.criteria.role == "engineer"
        assert sub.channels == ["web", "email"]
        listed = service.list_for_user("u1")
        assert len(listed) == 1
        assert listed[0].id == sub.id

    @pytest.mark.asyncio
    async def test_create_accepts_dict_or_criteria(self, service):
        from services.job_subscription import SubscriptionCriteria

        sub = service.create(
            user_id="u1",
            name="dict",
            criteria=SubscriptionCriteria(role="PM", city="Beijing"),
        )
        assert sub.criteria.role == "PM"
        assert sub.criteria.city == "Beijing"

    @pytest.mark.asyncio
    async def test_update(self, service):
        sub = service.create(
            user_id="u1",
            name="orig",
            criteria={"role": "engineer"},
        )
        updated = service.update(
            sub.id,
            user_id="u1",
            name="renamed",
            criteria={"role": "pm"},
            enabled=False,
        )
        assert updated is not None
        assert updated.name == "renamed"
        assert updated.criteria.role == "pm"
        assert updated.enabled is False

    @pytest.mark.asyncio
    async def test_update_rejects_other_users(self, service):
        sub = service.create(user_id="u1", name="x", criteria={})
        result = service.update(sub.id, user_id="u2", name="hijack")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, service):
        sub = service.create(user_id="u1", name="x", criteria={})
        ok = service.delete(sub.id, user_id="u1")
        assert ok is True
        assert service.list_for_user("u1") == []

    @pytest.mark.asyncio
    async def test_delete_rejects_other_users(self, service):
        sub = service.create(user_id="u1", name="x", criteria={})
        ok = service.delete(sub.id, user_id="u2")
        assert ok is False
        assert len(service.list_for_user("u1")) == 1

    @pytest.mark.asyncio
    async def test_get_returns_owner_match(self, service):
        sub = service.create(user_id="u1", name="x", criteria={})
        assert service.get(sub.id) is not None
        assert service.get(sub.id, user_id="u1") is not None
        assert service.get(sub.id, user_id="u2") is None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class TestMatching:
    @pytest.mark.asyncio
    async def test_role_keyword_match(self, service):
        matches = await service.match_subscription(
            {"role": "backend", "city": "Shanghai"},
            jobs=[_sample_job()],
        )
        assert len(matches) == 1
        assert matches[0].title == "Senior Backend Engineer"
        assert "title matches 'backend'" in matches[0].reasons

    @pytest.mark.asyncio
    async def test_role_keyword_mismatch_returns_empty(self, service):
        matches = await service.match_subscription(
            {"role": "frontend"},
            jobs=[_sample_job()],
        )
        assert matches == []

    @pytest.mark.asyncio
    async def test_skills_jaccard_score(self, service):
        matches = await service.match_subscription(
            {"role": "engineer", "skills": ["python", "django"]},
            jobs=[_sample_job()],
        )
        assert len(matches) == 1
        # 2/3 jaccard * 0.4 weight = 0.2667 partial
        assert matches[0].score > 0.4
        assert any("python" in r for r in matches[0].reasons)

    @pytest.mark.asyncio
    async def test_salary_filter(self, service):
        # job max 50k, target 80k -> 不匹配
        matches = await service.match_subscription(
            {"role": "engineer", "salary_min": 80_000},
            jobs=[_sample_job()],
        )
        assert matches == []

        # target 40k -> 匹配
        matches = await service.match_subscription(
            {"role": "engineer", "salary_min": 40_000},
            jobs=[_sample_job()],
        )
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_remote_policy_filter(self, service):
        matches = await service.match_subscription(
            {"role": "engineer", "remote_policy": "remote"},
            jobs=[_sample_job()],  # hybrid
        )
        assert matches == []
        matches = await service.match_subscription(
            {"role": "engineer", "remote_policy": "hybrid"},
            jobs=[_sample_job()],
        )
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_results_sorted_desc(self, service):
        jobs = [
            _sample_job(id="j1", title="Backend A"),
            _sample_job(id="j2", title="Backend B", skills=["python", "django", "postgres", "redis"]),
            _sample_job(id="j3", title="Backend C", skills=[]),
        ]
        matches = await service.match_subscription(
            {"role": "backend", "skills": ["python", "django", "postgres", "redis"]},
            jobs=jobs,
        )
        scores = [m.score for m in matches]
        assert scores == sorted(scores, reverse=True)
        assert matches[0].id == "j2"

    @pytest.mark.asyncio
    async def test_match_all_subscriptions(self, service):
        service.create(user_id="u1", name="a", criteria={"role": "engineer"})
        service.create(user_id="u2", name="b", criteria={"role": "sales"})  # 无匹配
        service.create(user_id="u3", name="c", criteria={"role": "backend"}, enabled=False)
        pairs = await service.match_all_subscriptions(jobs=[_sample_job()])
        # 只有 u1 启用且 role 匹配
        assert len(pairs) == 1
        sub, matches = pairs[0]
        assert sub.name == "a"
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# Subscription.from_row
# ---------------------------------------------------------------------------


class TestFromRow:
    def test_from_row_dict_criteria(self):
        from services.job_subscription import Subscription
        s = Subscription.from_row(
            {
                "id": "x",
                "user_id": "u",
                "name": "n",
                "criteria": {"role": "r", "skills": ["a"]},
                "channels": ["web"],
                "enabled": True,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-02T00:00:00",
            }
        )
        assert s.criteria.role == "r"
        assert s.criteria.skills == ["a"]
        assert s.channels == ["web"]

    def test_from_row_missing_criteria(self):
        from services.job_subscription import Subscription
        s = Subscription.from_row(
            {
                "id": "x",
                "user_id": "u",
                "name": "n",
                "channels": [],
                "enabled": False,
                "created_at": "",
                "updated_at": "",
            }
        )
        # 不抛异常;criteria 是默认空对象
        assert s.criteria.role == ""
        assert s.criteria.skills == []
