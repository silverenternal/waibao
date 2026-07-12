"""Tests for channel_attribution (T1303)."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def tracker():
    from services.funnel_events import FunnelEventTracker
    return FunnelEventTracker(supabase=None)


@pytest.fixture
def service(tracker):
    from services.channel_attribution import ChannelAttributionService
    return ChannelAttributionService(tracker, revenue_per_hire_cents=100_000)


async def _seed_simple(tracker):
    """1 个候选人通过 linkedin 完成全流程."""
    await tracker.record_batch(
        [
            {"candidate_id": "c1", "stage": "sourced", "source": "linkedin"},
            {"candidate_id": "c1", "stage": "applied", "source": "linkedin"},
            {"candidate_id": "c1", "stage": "screened", "source": "linkedin"},
            {"candidate_id": "c1", "stage": "interviewed", "source": "linkedin"},
            {"candidate_id": "c1", "stage": "offered", "source": "linkedin"},
            {"candidate_id": "c1", "stage": "hired", "source": "linkedin"},
        ]
    )


# ---------------------------------------------------------------------------
# first_touch
# ---------------------------------------------------------------------------


class TestFirstTouch:
    @pytest.mark.asyncio
    async def test_single_hire_credited(self, service, tracker):
        await _seed_simple(tracker)
        report = await service.compute_channel_roi(since_days=30)
        attrs = report.by_model["first_touch"]
        assert len(attrs) == 1
        assert attrs[0].channel == "linkedin"
        assert attrs[0].hires == 1
        assert attrs[0].hire_credit == 1.0

    @pytest.mark.asyncio
    async def test_multi_candidates_first_source(self, service, tracker):
        await tracker.record_batch(
            [
                {"candidate_id": "c1", "stage": "sourced", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "hired", "source": "linkedin"},
                {"candidate_id": "c2", "stage": "sourced", "source": "referral"},
                {"candidate_id": "c2", "stage": "applied", "source": "linkedin"},
                {"candidate_id": "c2", "stage": "hired", "source": "linkedin"},
            ]
        )
        report = await service.compute_channel_roi(since_days=30)
        first = {c.channel: c for c in report.by_model["first_touch"]}
        assert first["referral"].hires == 1
        assert first["linkedin"].hires == 1


# ---------------------------------------------------------------------------
# last_touch
# ---------------------------------------------------------------------------


class TestLastTouch:
    @pytest.mark.asyncio
    async def test_last_source_credited(self, service, tracker):
        await tracker.record_batch(
            [
                {"candidate_id": "c1", "stage": "sourced", "source": "referral"},
                {"candidate_id": "c1", "stage": "applied", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "hired", "source": "linkedin"},
            ]
        )
        report = await service.compute_channel_roi(since_days=30)
        last = {c.channel: c for c in report.by_model["last_touch"]}
        assert "linkedin" in last
        assert last["linkedin"].hires == 1
        # referral 没到 hired 阶段
        assert "referral" not in last


# ---------------------------------------------------------------------------
# multi_touch
# ---------------------------------------------------------------------------


class TestMultiTouch:
    @pytest.mark.asyncio
    async def test_credit_split_equally(self, service, tracker):
        await tracker.record_batch(
            [
                {"candidate_id": "c1", "stage": "sourced", "source": "linkedin"},
                {"candidate_id": "c1", "stage": "applied", "source": "referral"},
                {"candidate_id": "c1", "stage": "hired", "source": "indeed"},
            ]
        )
        report = await service.compute_channel_roi(since_days=30)
        multi = {c.channel: c for c in report.by_model["multi_touch"]}
        assert len(multi) == 3
        # multi_touch 把 1 个 hire 按 1/n 分摊到每个渠道; hire_credit 是 float,
        # hires(int) 在小分摊时会被四舍五入为 0, 用 credit 验证分摊。
        for ch in ("linkedin", "referral", "indeed"):
            assert abs(multi[ch].hire_credit - 1.0 / 3) < 0.01
            assert abs(multi[ch].revenue_cents - 100_000 / 3) < 1
        # 总 credit 应该 ≈ 1
        total_credit = sum(c.hire_credit for c in multi.values())
        assert abs(total_credit - 1.0) < 0.02  # 0.33*3 ≈ 0.99 due to rounding


# ---------------------------------------------------------------------------
# ROI
# ---------------------------------------------------------------------------


class TestROI:
    @pytest.mark.asyncio
    async def test_roi_with_cost(self, service, tracker):
        await tracker.record_batch(
            [
                {
                    "candidate_id": "c1",
                    "stage": "sourced",
                    "source": "linkedin",
                    "cost_cents": 5000,
                },
                {
                    "candidate_id": "c1",
                    "stage": "hired",
                    "source": "linkedin",
                    "cost_cents": 5000,
                },
            ]
        )
        report = await service.compute_channel_roi(since_days=30)
        first = report.by_model["first_touch"][0]
        # cost = 10000, revenue = 100_000, ROI = (100000 - 10000) / 10000 = 9.0
        assert first.cost_cents == 10000
        assert first.revenue_cents == 100_000
        assert first.roi == 9.0
        assert first.cost_per_hire == 10000.0

    @pytest.mark.asyncio
    async def test_no_cost_roi_is_zero(self, service, tracker):
        await _seed_simple(tracker)
        report = await service.compute_channel_roi(since_days=30)
        attr = report.by_model["first_touch"][0]
        assert attr.cost_cents == 0
        assert attr.roi == 0.0
        # cost=0, hires=1 -> cost_per_hire = 0/1 = 0.0
        assert attr.cost_per_hire == 0.0

    @pytest.mark.asyncio
    async def test_spend_lookup_injects_external_cost(self, tracker):
        from services.channel_attribution import ChannelAttributionService

        async def spend(org_id, since):
            return {"linkedin": 30_000}

        svc = ChannelAttributionService(
            tracker,
            revenue_per_hire_cents=200_000,
            channel_spend_lookup=spend,
        )
        await _seed_simple(tracker)
        report = await svc.compute_channel_roi(since_days=30)
        attr = report.by_model["first_touch"][0]
        assert attr.cost_cents == 30_000
        assert attr.revenue_cents == 200_000
        assert abs(attr.roi - (170_000 / 30_000)) < 0.01


# ---------------------------------------------------------------------------
# Report summary
# ---------------------------------------------------------------------------


class TestReport:
    @pytest.mark.asyncio
    async def test_best_channel_by_model(self, service, tracker):
        await tracker.record_batch(
            [
                {"candidate_id": "a", "stage": "hired", "source": "linkedin"},
                {"candidate_id": "b", "stage": "hired", "source": "linkedin"},
                {
                    "candidate_id": "c",
                    "stage": "sourced",
                    "source": "indeed",
                    "cost_cents": 50_000,
                },
                {"candidate_id": "c", "stage": "hired", "source": "indeed"},
            ]
        )
        report = await service.compute_channel_roi(since_days=30)
        # indeed ROI = (100000 - 50000) / 50000 = 1.0; linkedin ROI = 0
        # 应选 indeed
        assert report.best_channel_by_model["first_touch"] == "indeed"

    @pytest.mark.asyncio
    async def test_summary_shape(self, service, tracker):
        await _seed_simple(tracker)
        report = await service.compute_channel_roi(since_days=30)
        summary = report.summary
        for model in ("first_touch", "last_touch", "multi_touch"):
            assert model in summary
            assert "channels" in summary[model]
            assert "total_hires" in summary[model]

    @pytest.mark.asyncio
    async def test_unknown_model_raises(self, service):
        with pytest.raises(ValueError):
            await service.compute_channel_roi(models=["bogus_model"])
