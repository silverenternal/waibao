"""Tests for recruitment funnel + funnel_events (T1303)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def tracker():
    from services.funnel_events import FunnelEventTracker
    return FunnelEventTracker(supabase=None)


@pytest.fixture
def funnel(tracker):
    from services.recruitment_funnel import RecruitmentFunnel
    return RecruitmentFunnel(tracker)


# ---------------------------------------------------------------------------
# FunnelEventTracker
# ---------------------------------------------------------------------------


class TestFunnelEventTracker:
    @pytest.mark.asyncio
    async def test_record_stage_creates_event(self, tracker):
        ev = await tracker.record_stage(
            candidate_id="c1", stage="sourced", source="linkedin"
        )
        assert ev is not None
        assert ev.candidate_id == "c1"
        assert ev.stage == "sourced"
        assert ev.source == "linkedin"

    @pytest.mark.asyncio
    async def test_record_stage_idempotent(self, tracker):
        args = dict(candidate_id="c1", stage="screened", source="referral")
        e1 = await tracker.record_stage(**args)
        e2 = await tracker.record_stage(**args)
        assert e1 is not None
        assert e2 is not None
        assert e1.id == e2.id  # dedupe

    @pytest.mark.asyncio
    async def test_unknown_stage_rejected(self, tracker):
        ev = await tracker.record_stage(candidate_id="c1", stage="invalid")
        assert ev is None

    @pytest.mark.asyncio
    async def test_record_batch(self, tracker):
        n = await tracker.record_batch(
            [
                {"candidate_id": f"c{i}", "stage": "sourced", "source": "linkedin"}
                for i in range(5)
            ]
        )
        assert n == 5


# ---------------------------------------------------------------------------
# RecruitmentFunnel.compute_funnel
# ---------------------------------------------------------------------------


class TestRecruitmentFunnel:
    @pytest.mark.asyncio
    async def test_empty_funnel(self, funnel):
        result = await funnel.compute_funnel(since_days=30)
        assert result.total_candidates == 0
        assert all(s.candidates == 0 for s in result.stages)
        assert result.overall_conversion == 0.0

    @pytest.mark.asyncio
    async def test_basic_funnel(self, funnel, tracker):
        await tracker.record_batch(
            [
                {"candidate_id": "c1", "stage": "sourced", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "applied", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "screened", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "interviewed", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "offered", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "hired", "source": "linkedin"},
                {"candidate_id": "c2", "stage": "sourced", "source": "referral"},
                {"candidate_id": "c2", "stage": "applied", "source": "referral"},
                {"candidate_id": "c3", "stage": "sourced", "source": "indeed"},
            ]
        )
        result = await funnel.compute_funnel(since_days=30)
        counts = {s.stage: s.candidates for s in result.stages}
        assert counts["sourced"] == 3
        assert counts["applied"] == 2
        assert counts["screened"] == 1
        assert counts["interviewed"] == 1
        assert counts["offered"] == 1
        assert counts["hired"] == 1
        assert result.conversion_rates["sourced_to_applied"] == round(2 / 3 * 100, 2)
        assert result.conversion_rates["screened_to_interviewed"] == 100.0
        assert result.conversion_rates["offered_to_hired"] == 100.0
        assert result.overall_conversion == round(1 / 3 * 100, 2)
        assert result.by_source["linkedin"]["sourced"] == 1
        assert result.by_source["referral"]["sourced"] == 1
        assert result.by_source["indeed"]["sourced"] == 1

    @pytest.mark.asyncio
    async def test_since_days_filter(self, funnel, tracker):
        ev = await tracker.record_stage(
            candidate_id="old", stage="sourced", source="x"
        )
        # 强制改时间到 100 天前
        ev.occurred_at = (
            datetime.now(timezone.utc) - timedelta(days=100)
        ).isoformat()
        result_30 = await funnel.compute_funnel(since_days=30)
        assert result_30.total_candidates == 0
        result_120 = await funnel.compute_funnel(since_days=120)
        assert result_120.total_candidates == 1


# ---------------------------------------------------------------------------
# auto_transition
# ---------------------------------------------------------------------------


class TestAutoTransition:
    @pytest.mark.asyncio
    async def test_signal_to_stage_mapping(self, tracker):
        from services.funnel_events import auto_transition

        ev = await auto_transition(
            tracker,
            signal_event_type="intro_requested",
            actor_role="client",
            candidate_id="c1",
            metadata={"source": "linkedin"},
        )
        assert ev is not None
        assert ev.stage == "interviewed"
        assert ev.source == "linkedin"

    @pytest.mark.asyncio
    async def test_unknown_signal_returns_none(self, tracker):
        from services.funnel_events import auto_transition

        ev = await auto_transition(
            tracker,
            signal_event_type="candidate_viewed",
            actor_role="client",
            candidate_id="c1",
        )
        assert ev is None
