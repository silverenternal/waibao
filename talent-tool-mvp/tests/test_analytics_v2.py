"""T2801 — analytics_v2 API 测试 (用 TestClient + mock ClickHouse)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_ch():
    """替换 get_clickhouse_client 为一个可控 mock."""
    ch = MagicMock()
    ch.health.return_value = {"ok": True, "version": "24.3", "host": "localhost", "database": "warehouse"}
    ch.query.return_value = []
    ch.query_one.return_value = None
    yield ch


@pytest.fixture
def auth_user():
    from contracts.shared import UserRole
    return MagicMock(user_id="u-1", tenant_id="t-1", role=UserRole.admin, email="admin@x.com")


@pytest.fixture
def client(fake_ch, auth_user):
    """构造 TestClient + 覆盖 auth / ch."""
    from fastapi.testclient import TestClient

    # Patch 在 import 之前
    fake_driver = MagicMock()
    fake_driver.Client = MagicMock()
    sys.modules["clickhouse_driver"] = fake_driver

    with patch("services.warehouse.get_clickhouse_client", return_value=fake_ch), \
         patch("services.warehouse.clickhouse_client.ClickHouseClient", return_value=fake_ch), \
         patch("api.analytics_v2.get_clickhouse_client", return_value=fake_ch), \
         patch("api.analytics_v2.get_scheduler") as sched:
        sched.return_value.status.return_value = {
            "enabled": True, "running": True, "interval_seconds": 3600,
            "total_runs": 5, "failed_runs": 0,
            "last_run_at": None, "next_run_at": None, "last_result": None,
        }
        sched.return_value.run_now.return_value.to_dict.return_value = {"job_id": "1", "status": "succeeded"}

        # 用一个最小 FastAPI app 单独挂这个 router, 避免启动整个后端
        from fastapi import FastAPI
        from api.analytics_v2 import router

        # 替换 auth dep
        from api.auth import get_current_user, require_admin
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: auth_user
        app.dependency_overrides[require_admin] = lambda: auth_user

        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health_returns_ok(client, fake_ch):
    r = client.get("/api/analytics-v2/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"] == "24.3"


# ---------------------------------------------------------------------------
# 漏斗
# ---------------------------------------------------------------------------
def test_funnel_overall(client, fake_ch):
    fake_ch.query.return_value = [
        {"stage": "applied", "candidates": 100},
        {"stage": "screened", "candidates": 60},
        {"stage": "hired", "candidates": 5},
    ]
    r = client.get("/api/analytics-v2/funnel")
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 3
    assert body["data"][0]["stage"] == "applied"
    # 调用了 ClickHouse
    assert fake_ch.query.called


def test_funnel_by_channel(client, fake_ch):
    fake_ch.query.return_value = [
        {"channel": "linkedin", "stage": "applied", "candidates": 50},
        {"channel": "linkedin", "stage": "hired", "candidates": 2},
    ]
    r = client.get("/api/analytics-v2/funnel/by-channel")
    assert r.status_code == 200
    assert r.json()["row_count"] == 2


def test_funnel_by_country(client, fake_ch):
    fake_ch.query.return_value = [
        {"country": "us", "stage": "applied", "candidates": 30},
    ]
    r = client.get("/api/analytics-v2/funnel/by-country?limit=10")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------
def test_matches_trend(client, fake_ch):
    fake_ch.query.return_value = [
        {"bucket": "2026-07-01", "matches": 50, "candidates": 40, "jobs": 5, "avg_score": 0.7, "accepted": 10},
    ]
    r = client.get("/api/analytics-v2/matches/trend?granularity=day")
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["matches"] == 50


def test_matches_trend_granularity_validation(client):
    r = client.get("/api/analytics-v2/matches/trend?granularity=year")
    assert r.status_code == 422  # pattern 不通过


def test_matches_top_jobs(client, fake_ch):
    fake_ch.query.return_value = [
        {"job_id": "j1", "title": "Eng", "industry": "saas", "country": "us",
         "matches": 100, "accepted": 20, "avg_score": 0.8},
    ]
    r = client.get("/api/analytics-v2/matches/top-jobs?limit=5")
    assert r.status_code == 200
    assert r.json()["data"][0]["matches"] == 100


# ---------------------------------------------------------------------------
# Cohort 留存
# ---------------------------------------------------------------------------
def test_candidate_cohort(client, fake_ch):
    fake_ch.query.return_value = [
        {"cohort_day": "2026-06-01", "cohort_size": 100, "d1": 30, "d7": 15, "d14": 10, "d30": 5},
    ]
    r = client.get("/api/analytics-v2/candidates/cohort")
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["cohort_size"] == 100
    # d30 留存率 5/100 = 0.05
    assert body["data"][0]["d30"] <= body["data"][0]["cohort_size"]


# ---------------------------------------------------------------------------
# SLA
# ---------------------------------------------------------------------------
def test_sla_daily(client, fake_ch):
    fake_ch.query.return_value = [
        {"event_date": "2026-07-01", "tickets": 100, "sla_met": 90, "sla_rate": 0.9,
         "avg_first_min": 10.0, "p95_first_min": 30.0, "avg_resolve_min": 240.0, "p95_resolve_min": 600.0},
    ]
    r = client.get("/api/analytics-v2/sla/daily")
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["sla_rate"] == 0.9


def test_sla_breakdown(client, fake_ch):
    fake_ch.query.return_value = [
        {"priority": "urgent", "tickets": 10, "sla_met": 9, "sla_rate": 0.9,
         "avg_first_min": 5.0, "avg_resolve_min": 60.0},
    ]
    r = client.get("/api/analytics-v2/sla/breakdown")
    assert r.status_code == 200
    assert r.json()["data"][0]["priority"] == "urgent"


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def test_admin_etl_status(client):
    r = client.get("/api/analytics-v2/admin/etl/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_admin_etl_run(client):
    r = client.post("/api/analytics-v2/admin/etl/run")
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Drilldown
# ---------------------------------------------------------------------------
def test_drilldown_blocklist_table(client):
    r = client.post("/api/analytics-v2/drilldown", json={
        "table": "raw_candidates",  # 不在白名单
        "dimensions": ["country"],
        "metrics": ["count"],
    })
    assert r.status_code == 400


def test_drilldown_blocklist_column(client):
    r = client.post("/api/analytics-v2/drilldown", json={
        "table": "marts.dim_candidates",
        "dimensions": ["__import__"],   # 不在白名单
        "metrics": ["count"],
    })
    assert r.status_code == 400


def test_drilldown_runs(client, fake_ch):
    fake_ch.query.return_value = [
        {"country": "us", "count": 100},
    ]
    r = client.post("/api/analytics-v2/drilldown", json={
        "table": "marts.dim_candidates",
        "dimensions": ["country"],
        "metrics": ["count"],
        "start": "2026-06-01",
        "end": "2026-07-01",
        "limit": 100,
    })
    assert r.status_code == 200
    assert r.json()["data"][0]["country"] == "us"


# ---------------------------------------------------------------------------
# 性能: 必须 < 100ms
# ---------------------------------------------------------------------------
def test_query_took_ms_recorded(client, fake_ch):
    """用 mock 让查询瞬间完成, 但前端应该拿到 < 100ms 字段."""
    fake_ch.query.return_value = [{"x": 1}]
    r = client.get("/api/analytics-v2/funnel")
    body = r.json()
    assert "took_ms" in body
    assert isinstance(body["took_ms"], (int, float))
    # mock 路径下查询应该 < 100ms
    assert body["took_ms"] < 100, f"expected <100ms, got {body['took_ms']}"
