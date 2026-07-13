"""T3710 - matching feedback tests."""
import pytest
from services.matching_feedback import (
    compute_hit_rate, aggregate_feedback, collect_feedback, FUNNEL_STAGES,
)


class TestComputeHitRate:
    def test_no_events(self):
        rep = compute_hit_rate([])
        d = rep.to_dict()
        assert d["totals"] == {s: 0 for s in FUNNEL_STAGES}

    def test_one_event(self):
        rep = compute_hit_rate([{"role_id": "r1", "candidate_id": "c1",
                                  "stage": "recommended"}])
        assert rep.totals["recommended"] == 1
        assert rep.by_role["r1"]["recommended"] == 1

    def test_ignore_invalid_stage(self):
        rep = compute_hit_rate([{"stage": "unknown"}])
        assert rep.totals == {s: 0 for s in FUNNEL_STAGES}

    def test_conversion_rates(self):
        rep = compute_hit_rate([
            {"stage": "recommended"}] * 10 +
            [{"stage": "contacted"}] * 5 +
            [{"stage": "interview"}] * 2 +
            [{"stage": "offer"}] * 1 +
            [{"stage": "hired"}] * 1
        )
        assert rep.totals["recommended"] == 10
        assert rep.conversion_rates["recommended->contacted"] == 0.5

    def test_weak_stages_detected(self):
        rep = compute_hit_rate([
            {"stage": "recommended"}] * 100 +
            [{"stage": "contacted"}] * 5
        )
        assert "recommended->contacted" in rep.weak_stages

    def test_by_role_breakdown(self):
        rep = compute_hit_rate([
            {"role_id": "r1", "stage": "recommended"},
            {"role_id": "r2", "stage": "recommended"},
            {"role_id": "r1", "stage": "contacted"},
        ])
        assert "r1" in rep.by_role
        assert "r2" in rep.by_role

    def test_no_group_by(self):
        rep = compute_hit_rate(
            [{"role_id": "r1", "stage": "recommended"}],
            group_by_role=False,
        )
        assert rep.by_role == {}


class TestCollectFeedback:
    def test_basic(self):
        e = collect_feedback("c1", "r1", "suitable", 5, "great")
        assert e.candidate_id == "c1"
        assert e.label == "suitable"
        assert e.rating == 5

    def test_invalid_label(self):
        with pytest.raises(ValueError):
            collect_feedback("c", "r", "x", 4)

    def test_invalid_rating(self):
        with pytest.raises(ValueError):
            collect_feedback("c", "r", "suitable", 7)

    def test_zero_rating(self):
        with pytest.raises(ValueError):
            collect_feedback("c", "r", "suitable", 0)

    def test_with_timestamp(self):
        e = collect_feedback("c", "r", "suitable", 4, now_iso="2026-01-01")
        assert e.created_at == "2026-01-01"

    def test_unsuitable(self):
        e = collect_feedback("c", "r", "unsuitable", 2)
        assert e.label == "unsuitable"


class TestAggregateFeedback:
    def test_empty(self):
        assert aggregate_feedback([])["totals"] == {}

    def test_counts_labels(self):
        from services.matching_feedback import FeedbackEntry
        entries = [
            FeedbackEntry(candidate_id="c", role_id="r",
                          label="suitable", rating=4),
            FeedbackEntry(candidate_id="c2", role_id="r",
                          label="unsuitable", rating=2),
        ]
        d = aggregate_feedback(entries)
        assert d["totals"]["suitable"] == 1
        assert d["totals"]["unsuitable"] == 1

    def test_average_rating(self):
        from services.matching_feedback import FeedbackEntry
        entries = [
            FeedbackEntry(candidate_id="c", role_id="r",
                          label="suitable", rating=5),
            FeedbackEntry(candidate_id="c2", role_id="r",
                          label="suitable", rating=3),
        ]
        d = aggregate_feedback(entries)
        assert d["average_rating"] == 4.0

    def test_no_rating(self):
        from services.matching_feedback import FeedbackEntry
        entries = [
            FeedbackEntry(candidate_id="c", role_id="r",
                          label="suitable", rating=0),
        ]
        d = aggregate_feedback(entries)
        assert d["average_rating"] == 0

    def test_weight_adjustment(self):
        from services.matching_feedback import FeedbackEntry
        entries = [
            FeedbackEntry(candidate_id=f"c{i}", role_id="r",
                          label="unsuitable", rating=2)
            for i in range(5)
        ]
        d = aggregate_feedback(entries)
        assert d["weight_adjustments"]


@pytest.mark.parametrize("stage", FUNNEL_STAGES)
def test_all_funnel_stages(stage):
    """Each stage should be a valid funnel stage."""
    rep = compute_hit_rate([{"stage": stage}])
    assert rep.totals[stage] == 1
