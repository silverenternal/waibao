"""T3708 - consensus v2 algorithm tests."""
import pytest
from services.consensus_v2 import (
    compute_consensus, level_for, aggregate_dimension, _variance,
    STRONG_THRESHOLD, WEAK_THRESHOLD,
)


class TestLevelFor:
    def test_strong(self):
        assert level_for(0.85) == "strong"
        assert level_for(0.9) == "strong"

    def test_weak(self):
        assert level_for(0.6) == "weak"
        assert level_for(0.79) == "weak"
        assert level_for(0.5) == "weak"

    def test_fuzzy(self):
        assert level_for(0.4) == "fuzzy"
        assert level_for(0.0) == "fuzzy"


class TestAggregateDimension:
    def test_empty(self):
        s, c = aggregate_dimension([])
        assert s == 0.0
        assert c is False

    def test_uniform(self):
        s, c = aggregate_dimension([0.7, 0.7, 0.7])
        assert c is False

    def test_high_variance(self):
        s, c = aggregate_dimension([0.2, 0.9, 0.4])
        assert c is True


class TestVariance:
    def test_constant(self):
        assert _variance([0.5, 0.5, 0.5]) == 0.0

    def test_empty(self):
        assert _variance([]) == 0.0


class TestComputeConsensus:
    def test_basic_strong(self):
        rep = compute_consensus({
            "salary": [0.9, 0.9, 0.85],
            "level": [0.85, 0.8, 0.9],
        })
        assert rep.level == "strong"
        assert rep.can_decide is True

    def test_weak(self):
        rep = compute_consensus({
            "salary": [0.6, 0.6],
            "level": [0.7, 0.7],
        })
        assert rep.level == "weak"

    def test_fuzzy(self):
        rep = compute_consensus({
            "salary": [0.3],
            "level": [0.4],
        })
        assert rep.level == "fuzzy"

    def test_conflicting_dimensions(self):
        rep = compute_consensus({
            "salary": [0.9, 0.2],
            "level": [0.7, 0.7],
        }, notes_by_dim={"salary": ["lowball"]})
        assert "salary" in rep.conflicting_dimensions
        assert rep.compromise_plan is not None

    def test_compromise_salary(self):
        rep = compute_consensus({"salary": [0.9, 0.2, 0.5]}, notes_by_dim={"salary": ["a"]})
        assert rep.compromise_plan["title"]

    def test_compromise_timeline(self):
        rep = compute_consensus({"timeline": [0.9, 0.1]}, notes_by_dim={"timeline": ["urgent"]})
        assert "timeline" in rep.compromise_plan["title"]

    def test_compromise_level(self):
        rep = compute_consensus({"level": [0.9, 0.1]}, notes_by_dim={"level": ["x"]})
        assert "P6" in rep.compromise_plan["suggested"]

    def test_compromise_generic(self):
        rep = compute_consensus({"misc": [0.9, 0.1]}, notes_by_dim={"misc": ["x"]})
        assert "决策会" in rep.compromise_plan["suggested"]

    def test_dimensions_listed(self):
        rep = compute_consensus({"a": [0.5], "b": [0.6]})
        assert len(rep.dimensions) == 2

    def test_to_dict(self):
        rep = compute_consensus({"a": [0.5]})
        d = rep.to_dict()
        assert "dimensions" in d

    def test_no_conflict_no_plan(self):
        rep = compute_consensus({"salary": [0.5, 0.5]})
        assert rep.compromise_plan is None


@pytest.mark.parametrize("score", [0.0, 0.5, 0.7, 0.85, 1.0])
def test_levels(score):
    rep = compute_consensus({"x": [score]})
    assert rep.level in {"strong", "weak", "fuzzy"}
