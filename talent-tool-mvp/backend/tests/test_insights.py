"""Tests for v8.0 T3901 — insights API."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import get_current_user
from api.insights import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin():
    u = MagicMock()
    u.id = "u-1"
    u.role = "admin"
    u.tenant_id = "t-1"
    return u


def _normal_user():
    u = MagicMock()
    u.id = "u-1"
    u.role = "user"
    u.tenant_id = "t-1"
    return u


@pytest.fixture
def admin_app():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: _admin()
    return a


@pytest.fixture
def admin_client(admin_app):
    return TestClient(admin_app)


@pytest.fixture
def user_client():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: _normal_user()
    return TestClient(a)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_list_weekly_reports_forbidden(user_client):
    r = user_client.get("/api/insights/weekly")
    assert r.status_code == 403


def test_latest_forbidden(user_client):
    r = user_client.get("/api/insights/weekly/latest")
    assert r.status_code == 403


def test_anomalies_forbidden(user_client):
    r = user_client.get("/api/insights/anomalies")
    assert r.status_code == 403


def test_behavior_forbidden(user_client):
    r = user_client.get("/api/insights/behavior")
    assert r.status_code == 403


def test_cycle_forbidden(user_client):
    r = user_client.post("/api/insights/cycle")
    assert r.status_code == 403


def test_generate_forbidden(user_client):
    r = user_client.post(
        "/api/insights/weekly/generate",
        json={"fmt": "txt"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# List weekly
# ---------------------------------------------------------------------------


def test_list_weekly_no_supabase(admin_client):
    with patch("api.insights.get_supabase_admin", return_value=None):
        r = admin_client.get("/api/insights/weekly")
    assert r.status_code == 200
    assert r.json() == []


def test_list_weekly_with_data(admin_client):
    sb = MagicMock()
    sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {
            "week_start": "2026-07-06",
            "week_end": "2026-07-12",
            "format": "pdf",
            "filename": "weekly_report.pdf",
            "size_bytes": 1024,
            "summary": {"total_dau": 100},
            "generated_at": "2026-07-13T00:00:00Z",
        }
    ]
    with patch("api.insights.get_supabase_admin", return_value=sb):
        r = admin_client.get("/api/insights/weekly")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["week_start"] == "2026-07-06"


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def test_generate_txt(admin_client):
    r = admin_client.post(
        "/api/insights/weekly/generate",
        json={"fmt": "txt"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["format"] == "txt"
    assert "summary" in data
    assert "delivery" in data


def test_generate_invalid_fmt(admin_client):
    r = admin_client.post(
        "/api/insights/weekly/generate",
        json={"fmt": "doc"},
    )
    assert r.status_code == 422


def test_generate_with_anomalies(admin_client):
    r = admin_client.post(
        "/api/insights/weekly/generate",
        json={
            "fmt": "txt",
            "anomalies": [{"type": "test", "severity": "warning", "metric": "m",
                            "current": 1, "baseline": 2, "delta_pct": -50,
                            "message": "x", "detected_at": "2026-01-01T00:00:00Z"}],
        },
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Anomalies / behavior
# ---------------------------------------------------------------------------


def test_list_anomalies(admin_client):
    with patch("api.insights.get_supabase_admin", return_value=None):
        r = admin_client.get("/api/insights/anomalies")
    assert r.status_code == 200
    data = r.json()
    assert "anomalies" in data
    assert "behavior_insights" in data


def test_behavior_insights(admin_client):
    r = admin_client.get("/api/insights/behavior")
    assert r.status_code == 200
    data = r.json()
    assert "insights" in data


def test_run_cycle(admin_client):
    r = admin_client.post("/api/insights/cycle")
    assert r.status_code == 200
    data = r.json()
    assert "anomalies" in data
    assert "behavior_insights" in data
    assert "alert" in data


def test_latest_weekly(admin_client):
    with patch("api.insights.get_supabase_admin", return_value=None):
        r = admin_client.get("/api/insights/weekly/latest")
    assert r.status_code == 200
    data = r.json()
    assert "anomalies" in data
    assert "behavior_insights" in data
    assert "alert" in data
    assert "generated_at" in data
