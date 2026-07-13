"""Tests for v8.0 T3901 — Anomaly detector + behavior analysis.

Covers:
* DEFAULT_THRESHOLDS env override
* AnomalyResult.to_dict / from_dict
* detect_match_rate_drop / detect_active_user_drop / detect_ticket_backlog
* detect_error_rate_spike / detect_feature_abandoned
* analyze_feature_usage: popular / low_usage / abandoned
* detect_from_metrics (combination)
* z_score_anomaly
* alert (no dispatcher / dispatcher / critical-only)
* run_cycle (end-to-end)
* _collect_metrics mock fallback
* Singleton + reset
"""
from __future__ import annotations

import asyncio
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from services.platform import anomaly_detector as ad
from services.platform.anomaly_detector import (
    AnomalyDetector,
    AnomalyResult,
    AnomalyType,
    BehaviorInsight,
    FeatureUsageRow,
    Severity,
    get_anomaly_detector,
    reset_anomaly_detector,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fixed_now() -> datetime:
    return datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _make_detector(
    *,
    now: Optional[Any] = None,
    supabase: Any = None,
    dispatcher: Any = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> AnomalyDetector:
    return AnomalyDetector(
        thresholds=thresholds,
        clock=now or _fixed_now,
        supabase_factory=(lambda: supabase) if supabase is not None else (lambda: None),
        dispatcher_factory=(lambda: dispatcher) if dispatcher is not None else (lambda: None),
    )


def _dispatcher_ok(channels=("smtp", "dingtalk", "feishu")):
    d = MagicMock()
    out = MagicMock()
    out.results = [
        MagicMock(channel=ch, success=True, message_id=f"m-{ch}", error=None, skipped=False)
        for ch in channels
    ]
    async def _async_dispatch_multi(*args, **kwargs):
        return out
    d.dispatch_multi = _async_dispatch_multi
    return d


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_anomaly_detector()
    yield
    reset_anomaly_detector()


# ---------------------------------------------------------------------------
# 1. Thresholds
# ---------------------------------------------------------------------------


def test_default_thresholds_have_all_keys():
    keys = {"match_rate_drop_pct", "active_user_drop_pct", "ticket_backlog_count",
            "error_rate_spike_pct", "feature_abandoned_days", "feature_min_usage",
            "z_score_threshold"}
    assert keys.issubset(set(ad.DEFAULT_THRESHOLDS.keys()))


def test_thresholds_env_override(monkeypatch):
    monkeypatch.setenv("ANOMALY_MATCH_RATE_DROP_PCT", "30.0")
    d = _make_detector()
    assert d.thresholds["match_rate_drop_pct"] == 30.0


def test_thresholds_invalid_env_ignored(monkeypatch):
    monkeypatch.setenv("ANOMALY_MATCH_RATE_DROP_PCT", "not-a-number")
    d = _make_detector()
    assert d.thresholds["match_rate_drop_pct"] == ad.DEFAULT_THRESHOLDS["match_rate_drop_pct"]


def test_update_threshold_valid():
    d = _make_detector()
    d.update_threshold("match_rate_drop_pct", 25.0)
    assert d.thresholds["match_rate_drop_pct"] == 25.0


def test_update_threshold_invalid_key_raises():
    d = _make_detector()
    with pytest.raises(KeyError):
        d.update_threshold("not_a_key", 1.0)


# ---------------------------------------------------------------------------
# 2. AnomalyResult serialization
# ---------------------------------------------------------------------------


def test_anomaly_result_to_dict():
    r = AnomalyResult(
        type="x", severity="warning", metric="m", current=1.0, baseline=2.0,
        delta_pct=-50.0, message="msg", detected_at="2026-01-01T00:00:00Z",
        metadata={"k": "v"},
    )
    d = r.to_dict()
    assert d["type"] == "x"
    assert d["metadata"] == {"k": "v"}


def test_anomaly_result_from_dict_roundtrip():
    r = AnomalyResult(
        type="x", severity="warning", metric="m", current=1.0, baseline=2.0,
        delta_pct=-50.0, message="msg", detected_at="2026-01-01T00:00:00Z",
    )
    d = r.to_dict()
    r2 = AnomalyResult.from_dict(d)
    assert r2.type == r.type
    assert r2.metric == r.metric


# ---------------------------------------------------------------------------
# 3. Match rate drop
# ---------------------------------------------------------------------------


def test_match_rate_drop_below_threshold_returns_none():
    d = _make_detector()
    r = d.detect_match_rate_drop(current=85.0, baseline=86.0)  # 1pp drop
    assert r is None


def test_match_rate_drop_above_threshold_returns_warning():
    d = _make_detector()
    r = d.detect_match_rate_drop(current=60.0, baseline=86.0)  # 26pp drop
    assert r is not None
    assert r.type == AnomalyType.MATCH_RATE_DROP.value
    assert r.severity in {Severity.WARNING.value, Severity.CRITICAL.value}


def test_match_rate_drop_critical_at_40pp():
    d = _make_detector()
    r = d.detect_match_rate_drop(current=40.0, baseline=86.0)
    assert r is not None
    assert r.severity == Severity.CRITICAL.value


# ---------------------------------------------------------------------------
# 4. Active user drop
# ---------------------------------------------------------------------------


def test_active_user_drop_below_threshold():
    d = _make_detector()
    r = d.detect_active_user_drop(current=290, baseline=312)  # ~7%
    assert r is None


def test_active_user_drop_warning_at_20pct():
    d = _make_detector()
    r = d.detect_active_user_drop(current=240, baseline=312)  # ~23%
    assert r is not None
    assert r.severity == Severity.WARNING.value


def test_active_user_drop_zero_baseline_returns_none():
    d = _make_detector()
    r = d.detect_active_user_drop(current=10, baseline=0)
    assert r is None


# ---------------------------------------------------------------------------
# 5. Ticket backlog
# ---------------------------------------------------------------------------


def test_ticket_backlog_below_threshold_none():
    d = _make_detector()
    r = d.detect_ticket_backlog(open_tickets=30)
    assert r is None


def test_ticket_backlog_at_threshold_critical():
    d = _make_detector()
    r = d.detect_ticket_backlog(open_tickets=80)
    assert r is not None
    assert r.severity == Severity.CRITICAL.value


def test_ticket_backlog_custom_threshold():
    d = _make_detector()
    r = d.detect_ticket_backlog(open_tickets=10, threshold=5)
    assert r is not None


# ---------------------------------------------------------------------------
# 6. Error rate spike
# ---------------------------------------------------------------------------


def test_error_rate_spike_below_threshold():
    d = _make_detector()
    r = d.detect_error_rate_spike(current=2.0, baseline=1.0)  # +1pp
    assert r is None


def test_error_rate_spike_critical_above_15pp():
    d = _make_detector()
    r = d.detect_error_rate_spike(current=20.0, baseline=1.0)
    assert r is not None
    assert r.severity == Severity.CRITICAL.value


# ---------------------------------------------------------------------------
# 7. Feature abandoned
# ---------------------------------------------------------------------------


def test_feature_abandoned_includes_old_features():
    d = _make_detector()
    now = _fixed_now()
    features = [
        FeatureUsageRow(feature="old", invocations=10, unique_users=2,
                        last_used_at=(now - timedelta(days=10)).isoformat()),
        FeatureUsageRow(feature="new", invocations=100, unique_users=20,
                        last_used_at=(now - timedelta(hours=1)).isoformat()),
    ]
    results = d.detect_feature_abandoned(features)
    assert len(results) == 1
    assert results[0].metadata["feature"] == "old"


def test_feature_abandoned_skips_none_timestamp():
    d = _make_detector()
    features = [FeatureUsageRow(feature="x", invocations=1, unique_users=1, last_used_at=None)]
    assert d.detect_feature_abandoned(features) == []


# ---------------------------------------------------------------------------
# 8. Behavior analysis
# ---------------------------------------------------------------------------


def test_analyze_feature_usage_popular():
    d = _make_detector()
    features = [
        FeatureUsageRow("a", 100, 10, _fixed_now().isoformat()),
        FeatureUsageRow("b", 80, 8, _fixed_now().isoformat()),
        FeatureUsageRow("c", 60, 6, _fixed_now().isoformat()),
        FeatureUsageRow("d", 40, 4, _fixed_now().isoformat()),
        FeatureUsageRow("e", 20, 2, _fixed_now().isoformat()),
    ]
    insights = d.analyze_feature_usage(features)
    cats = {i.category for i in insights}
    assert "popular" in cats


def test_analyze_feature_usage_low_usage():
    d = _make_detector()
    features = [FeatureUsageRow("x", 1, 1, _fixed_now().isoformat())]
    insights = d.analyze_feature_usage(features)
    assert any(i.category == "low_usage" for i in insights)


def test_analyze_feature_usage_abandoned():
    d = _make_detector()
    now = _fixed_now()
    features = [FeatureUsageRow("old", 5, 1, (now - timedelta(days=15)).isoformat())]
    insights = d.analyze_feature_usage(features)
    assert any(i.category == "abandoned" for i in insights)


def test_analyze_feature_usage_empty():
    d = _make_detector()
    assert d.analyze_feature_usage([]) == []


# ---------------------------------------------------------------------------
# 9. Combined detection
# ---------------------------------------------------------------------------


def test_detect_from_metrics_returns_all():
    d = _make_detector()
    now = _fixed_now()
    features = [
        FeatureUsageRow("a", 100, 10, _fixed_now().isoformat()),
        FeatureUsageRow("old", 5, 1, (now - timedelta(days=10)).isoformat()),
    ]
    results = d.detect_from_metrics(
        match_rate_current=60.0, match_rate_baseline=86.0,  # drop
        dau_current=200, dau_baseline=312,  # drop
        open_tickets=80,  # backlog
        error_rate_current=20.0, error_rate_baseline=0.5,  # spike
        features=features,  # 1 abandoned
    )
    types = {r.type for r in results}
    assert AnomalyType.MATCH_RATE_DROP.value in types
    assert AnomalyType.ACTIVE_USER_DROP.value in types
    assert AnomalyType.TICKET_BACKLOG.value in types
    assert AnomalyType.ERROR_RATE_SPIKE.value in types
    assert AnomalyType.FEATURE_ABANDONED.value in types


def test_detect_from_metrics_clean_returns_empty():
    d = _make_detector()
    results = d.detect_from_metrics(
        match_rate_current=85.0, match_rate_baseline=86.0,
        dau_current=300, dau_baseline=312,
        open_tickets=20,
        error_rate_current=1.0, error_rate_baseline=1.0,
    )
    assert results == []


# ---------------------------------------------------------------------------
# 10. z-score
# ---------------------------------------------------------------------------


def test_z_score_anomaly_short_history():
    d = _make_detector()
    r = d.z_score_anomaly(current=100, history=[1, 2])
    assert r is None


def test_z_score_anomaly_zero_stdev():
    d = _make_detector()
    r = d.z_score_anomaly(current=5, history=[5, 5, 5, 5, 5])
    assert r is None


def test_z_score_anomaly_high_z_detected():
    d = _make_detector()
    history = [10, 11, 12, 10, 11, 12, 11, 10]
    r = d.z_score_anomaly(current=50, history=history)
    assert r is not None


# ---------------------------------------------------------------------------
# 11. Alert
# ---------------------------------------------------------------------------


def test_alert_empty_anomalies():
    d = _make_detector()
    result = asyncio.run(d.alert([]))
    assert result["delivered"] is False


def test_alert_no_dispatcher():
    d = _make_detector(dispatcher=None)
    a = AnomalyResult(
        type="x", severity="warning", metric="m", current=1, baseline=2,
        delta_pct=-50, message="m", detected_at="t",
    )
    result = asyncio.run(d.alert([a]))
    assert result["delivered"] is False


def test_alert_with_dispatcher():
    dispatcher = _dispatcher_ok()
    d = _make_detector(dispatcher=dispatcher)
    a = AnomalyResult(
        type="x", severity="critical", metric="m", current=1, baseline=2,
        delta_pct=-50, message="m", detected_at="t",
    )
    result = asyncio.run(d.alert([a], recipients=["oncall@x"]))
    assert result["delivered"] is True
    assert "smtp" in result["channels"]


# ---------------------------------------------------------------------------
# 12. run_cycle
# ---------------------------------------------------------------------------


def test_run_cycle_clean():
    d = _make_detector()
    metrics = {
        "match_rate_current": 85.0, "match_rate_baseline": 86.0,
        "dau_current": 300, "dau_baseline": 312,
        "open_tickets": 20,
        "error_rate_current": 1.0, "error_rate_baseline": 1.0,
        "features": [],
    }
    result = asyncio.run(d.run_cycle(metrics))
    assert "anomalies" in result
    assert "behavior_insights" in result


def test_run_cycle_with_real_anomalies():
    dispatcher = _dispatcher_ok()
    d = _make_detector(dispatcher=dispatcher)
    metrics = {
        "match_rate_current": 50.0, "match_rate_baseline": 86.0,
        "dau_current": 100, "dau_baseline": 312,
        "open_tickets": 80,
        "error_rate_current": 20.0, "error_rate_baseline": 0.5,
        "features": [],
    }
    result = asyncio.run(d.run_cycle(metrics))
    assert len(result["anomalies"]) > 0
    # 触发告警
    assert result["alert"]["delivered"] is True


def test_run_cycle_uses_mock_when_no_supabase():
    d = _make_detector(supabase=None)
    result = asyncio.run(d.run_cycle(metrics=None))
    assert "metrics_used" in result


# ---------------------------------------------------------------------------
# 13. Singleton
# ---------------------------------------------------------------------------


def test_singleton_same():
    a = get_anomaly_detector()
    b = get_anomaly_detector()
    assert a is b


def test_reset_singleton():
    a = get_anomaly_detector()
    reset_anomaly_detector()
    b = get_anomaly_detector()
    assert a is not b


# ---------------------------------------------------------------------------
# 14. Helpers
# ---------------------------------------------------------------------------


def test_severity_for_anomaly_backlog_always_critical():
    s = ad._severity_for_anomaly(AnomalyType.TICKET_BACKLOG.value, 5.0)
    assert s == Severity.CRITICAL


def test_parse_iso_valid():
    dt = ad._parse_iso("2026-07-13T00:00:00+00:00")
    assert isinstance(dt, datetime)


def test_parse_iso_invalid():
    assert ad._parse_iso("not-a-date") is None
    assert ad._parse_iso(None) is None


def test_percent_change_zero_baseline_zero_current():
    assert ad._percent_change(0, 0) == 0.0


def test_percent_change_zero_baseline_positive_current():
    assert ad._percent_change(5, 0) == 100.0


# ---------------------------------------------------------------------------
# 15. FeatureUsageRow.from_dict
# ---------------------------------------------------------------------------


def test_feature_usage_row_from_dict():
    row = FeatureUsageRow.from_dict({"feature": "x", "invocations": 5, "unique_users": 2, "last_used_at": "2026-01-01T00:00:00Z"})
    assert row.feature == "x"
    assert row.invocations == 5
    assert row.last_used_at == "2026-01-01T00:00:00Z"
