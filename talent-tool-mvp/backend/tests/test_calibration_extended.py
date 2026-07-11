"""T903 — calibration 扩展测试 (桶分布 + segment)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from services import calibration as cal


# ---------------------------------------------------------------------------
# compute_bucket_distribution
# ---------------------------------------------------------------------------


def test_bucket_distribution_empty_input():
    out = cal.compute_bucket_distribution([])
    # 实现返回所有桶(便于 dashboard 渲染空桶),但每桶 count=0
    assert set(out.keys()) == {"0.0-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"}
    for k, v in out.items():
        assert v["count"] == 0
        assert v["placed_rate"] == 0.0
        assert v["rejected_rate"] == 0.0


def test_bucket_distribution_classifies_scores():
    matches = [
        {"status": "placed", "harmonic_score": 0.9},
        {"status": "placed", "harmonic_score": 0.85},
        {"status": "rejected_by_candidate", "harmonic_score": 0.5},
        {"status": "pending", "harmonic_score": 0.2},
        {"status": "placed", "harmonic_score": 0.7},
        {"status": "rejected_by_employer", "harmonic_score": 0.3},
    ]
    out = cal.compute_bucket_distribution(matches)
    assert set(out.keys()) == {"0.0-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"}

    high = out["0.8-1.0"]
    assert high["count"] == 2
    assert high["placed_rate"] == pytest.approx(1.0)

    mid = out["0.4-0.6"]
    assert mid["count"] == 1
    assert mid["rejected_rate"] == pytest.approx(1.0)

    low_mid = out["0.6-0.8"]
    assert low_mid["count"] == 1

    low = out["0.0-0.4"]
    assert low["count"] == 2


def test_bucket_distribution_includes_avg_harmonic():
    matches = [
        {"status": "placed", "harmonic_score": 0.85},
        {"status": "placed", "harmonic_score": 0.75},
    ]
    out = cal.compute_bucket_distribution(matches)
    # 0.75 不在 [0.8, 1.0),会落到 0.6-0.8 桶
    assert "avg_harmonic" in out["0.8-1.0"]
    assert out["0.8-1.0"]["avg_harmonic"] == pytest.approx(0.85, abs=1e-3)
    assert out["0.6-0.8"]["avg_harmonic"] == pytest.approx(0.75, abs=1e-3)


# ---------------------------------------------------------------------------
# compute_segment_metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_segment_metrics_groups_by_role_seniority():
    class _Table:
        def __init__(self, rows):
            self.rows = rows

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def in_(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(data=self.rows)

    def table(name):
        if name == "candidates":
            return _Table(
                [
                    {"id": "c1", "seniority": "Senior"},
                ]
            )
        if name == "roles":
            return _Table(
                [
                    {"id": "r1", "seniority": "Senior"},
                    {"id": "r2", "seniority": "Mid"},
                ]
            )
        return _Table([])

    matches = [
        {"candidate_id": "c1", "role_id": "r1", "status": "placed"},
        {"candidate_id": "c1", "role_id": "r1", "status": "placed"},
        {"candidate_id": "c1", "role_id": "r2", "status": "rejected_by_employer"},
        {"candidate_id": "c1", "role_id": "r2", "status": "pending"},
    ]
    sb = SimpleNamespace(table=table)
    out = await cal.compute_segment_metrics(matches, sb)  # type: ignore[arg-type]

    assert "Senior" in out
    assert "Mid" in out
    assert out["Senior"]["count"] == 2
    assert out["Senior"]["tp"] == 2
    assert out["Senior"]["precision"] == pytest.approx(1.0)
    assert out["Mid"]["count"] == 2


@pytest.mark.asyncio
async def test_segment_metrics_handles_missing_tables_gracefully():
    def table(name):
        raise RuntimeError("table missing")

    matches = [
        {"candidate_id": "c1", "role_id": "r1", "status": "placed"},
    ]
    sb = SimpleNamespace(table=table)
    out = await cal.compute_segment_metrics(matches, sb)  # type: ignore[arg-type]
    # 全部归类到 unknown,不应抛
    assert "unknown" in out


# ---------------------------------------------------------------------------
# compute_metrics 聚合
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_aggregates_with_buckets_and_segments():
    class _AllTable:
        def select(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {"status": "placed", "harmonic_score": 0.9, "role_id": "r1", "candidate_id": "c1"},
                    {"status": "placed", "harmonic_score": 0.85, "role_id": "r1", "candidate_id": "c1"},
                    {"status": "rejected_by_employer", "harmonic_score": 0.5, "role_id": "r2", "candidate_id": "c1"},
                    {"status": "pending", "harmonic_score": 0.3, "role_id": "r2", "candidate_id": "c1"},
                ]
            )

    class _CandTable:
        def select(self, *_a, **_k):
            return self

        def in_(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "c1", "seniority": "Senior"}])

    class _RoleTable:
        def select(self, *_a, **_k):
            return self

        def in_(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {"id": "r1", "seniority": "Senior"},
                    {"id": "r2", "seniority": "Mid"},
                ]
            )

    def table(name):
        if name == "two_way_matches":
            return _AllTable()
        if name == "candidates":
            return _CandTable()
        if name == "roles":
            return _RoleTable()
        return _AllTable()

    sb = SimpleNamespace(table=table)
    out = await cal.compute_metrics(supabase=sb, since_days=90)  # type: ignore[arg-type]
    assert "bucket_distribution" in out
    assert "segment_metrics" in out
    assert out["precision"] == pytest.approx(2 / 3, rel=1e-3)
    assert "Senior" in out["segment_metrics"]
    assert "Mid" in out["segment_metrics"]


# ---------------------------------------------------------------------------
# suggest_weight_adjustment (向后兼容)
# ---------------------------------------------------------------------------


def test_suggest_weight_adjustment_low_precision():
    s = cal.suggest_weight_adjustment({"precision": 0.4})
    assert s["action"] == "tighten_hard_requirements"


def test_suggest_weight_adjustment_low_recall():
    s = cal.suggest_weight_adjustment({"precision": 0.8, "recall": 0.3})
    assert s["action"] == "loosen_constraints"


def test_suggest_weight_adjustment_stable():
    s = cal.suggest_weight_adjustment({"precision": 0.85, "recall": 0.75})
    assert s["action"] == "no_change"