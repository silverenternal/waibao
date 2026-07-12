"""Tests for T1904 cross-platform DAU/WAU/MAU analytics.

Uses in-memory fallback (no Supabase required) for fast unit testing.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    from api.analytics.cross_platform import _SessionStore

    return _SessionStore(supabase=None)


@pytest.fixture
def report():
    from api.analytics.cross_platform import compute_cross_platform_report

    return compute_cross_platform_report


def _evt(user_id: str, platform: str, when: datetime, **kw):
    from api.analytics.cross_platform import SessionEvent

    return SessionEvent(
        user_id=user_id,
        platform=platform,
        occurred_at=when,
        anonymous_id=kw.get("anonymous_id"),
        app_version=kw.get("app_version"),
        device_id=kw.get("device_id"),
    )


# ---------------------------------------------------------------------------
# Test: platform normalization
# ---------------------------------------------------------------------------


class TestPlatformNormalization:
    def test_known_platforms_unchanged(self):
        from api.analytics.cross_platform import _normalize_platform

        for p in ("webapp", "minip", "feishu", "dingtalk"):
            assert _normalize_platform(p) == p

    def test_aliases_resolved(self):
        from api.analytics.cross_platform import _normalize_platform

        assert _normalize_platform("h5") == "webapp"
        assert _normalize_platform("wechat") == "minip"
        assert _normalize_platform("lark") == "feishu"
        assert _normalize_platform("DT") == "dingtalk"

    def test_unknown_defaults_to_webapp(self):
        from api.analytics.cross_platform import _normalize_platform

        assert _normalize_platform(None) == "webapp"
        assert _normalize_platform("") == "webapp"
        assert _normalize_platform("ios-app") == "webapp"


# ---------------------------------------------------------------------------
# Test: _SessionStore
# ---------------------------------------------------------------------------


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_add_and_query_in_memory(self, store):
        now = datetime.now(timezone.utc)
        await store.add(_evt("u1", "webapp", now))
        await store.add(_evt("u1", "feishu", now + timedelta(hours=1)))
        result = await store.query(
            now - timedelta(minutes=10),
            now + timedelta(hours=2),
        )
        assert len(result) == 2
        platforms = {e.platform for e in result}
        assert platforms == {"webapp", "feishu"}

    @pytest.mark.asyncio
    async def test_query_filters_window(self, store):
        now = datetime.now(timezone.utc)
        await store.add(_evt("u1", "webapp", now))
        await store.add(_evt("u2", "webapp", now + timedelta(days=2)))
        result = await store.query(now - timedelta(minutes=1), now + timedelta(hours=1))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Test: bucket helpers
# ---------------------------------------------------------------------------


class TestBucketing:
    def test_dau_dedupes_users(self):
        from api.analytics.cross_platform import _dau_for

        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [
            _evt("u1", "webapp", now),
            _evt("u1", "feishu", now + timedelta(hours=1)),  # same user diff platform
            _evt("u2", "webapp", now + timedelta(minutes=30)),
        ]
        users = _dau_for(events, today)
        assert users == {"u1", "u2"}

    def test_wau_covers_7_days(self):
        from api.analytics.cross_platform import _wau_for

        today = datetime.now(timezone.utc).date()
        events = [
            _evt("u_old", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=6)),
            _evt("u_out_of_range", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=10)),
            _evt("u_today", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)),
        ]
        users = _wau_for(events, today)
        assert "u_old" in users
        assert "u_out_of_range" not in users
        assert "u_today" in users

    def test_mau_covers_30_days(self):
        from api.analytics.cross_platform import _mau_for

        today = datetime.now(timezone.utc).date()
        events = [
            _evt("u_d29", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=29)),
            _evt("u_d30", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=30)),
            _evt("u_today", "webapp", datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)),
        ]
        users = _mau_for(events, today)
        assert "u_d29" in users
        assert "u_d30" not in users
        assert "u_today" in users


# ---------------------------------------------------------------------------
# Test: compute_cross_platform_report
# ---------------------------------------------------------------------------


class TestCrossPlatformReport:
    def test_empty_returns_zero_metrics(self, report):
        r = report([])
        assert r.unified_dau == 0
        assert r.unified_mau == 0
        assert r.multi_platform_users == 0
        assert r.multi_platform_share == 0
        for p in r.by_platform:
            assert p.dau == 0 and p.wau == 0 and p.mau == 0

    def test_single_platform_single_user(self, report):
        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [_evt("u1", "webapp", now)]
        r = report(events, ref_day=today)
        assert r.unified_dau == 1
        assert r.unified_mau == 1
        assert r.multi_platform_users == 0
        wp = next(p for p in r.by_platform if p.platform == "webapp")
        assert wp.dau == 1 and wp.mau == 1

    def test_multi_platform_user_dedup(self, report):
        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [
            _evt("u1", "webapp", now),
            _evt("u1", "feishu", now + timedelta(minutes=5)),
            _evt("u2", "dingtalk", now + timedelta(minutes=10)),
        ]
        r = report(events, ref_day=today)
        # 跨端去重 → u1, u2 共 2 个独立用户
        assert r.unified_dau == 2
        # u1 跨 webapp + feishu 属于多端
        assert r.multi_platform_users == 1
        assert r.multi_platform_share == 0.5

    def test_four_platforms_all_present(self, report):
        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [
            _evt("u1", "webapp", now),
            _evt("u1", "minip", now),
            _evt("u2", "feishu", now),
            _evt("u2", "dingtalk", now),
        ]
        r = report(events, ref_day=today)
        # 4 端都应有数据
        platforms_present = {p.platform for p in r.by_platform if p.dau > 0}
        assert platforms_present == {"webapp", "minip", "feishu", "dingtalk"}
        # u1 和 u2 都跨 2 端
        assert r.multi_platform_users == 2

    def test_overlap_matrix_symmetric(self, report):
        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [
            _evt("u1", "webapp", now),
            _evt("u1", "feishu", now + timedelta(minutes=5)),
            _evt("u2", "webapp", now + timedelta(minutes=10)),
            _evt("u2", "dingtalk", now + timedelta(minutes=15)),
        ]
        r = report(events, ref_day=today)
        # 对角 = 该端 user 数；off-diag = 同时活跃于两端的人数
        assert r.overlap_matrix["webapp"]["webapp"] == 2  # u1, u2
        assert r.overlap_matrix["feishu"]["feishu"] == 1
        assert r.overlap_matrix["webapp"]["feishu"] == 1  # u1
        assert r.overlap_matrix["feishu"]["webapp"] == 1  # symmetric
        # u2 在 webapp + dingtalk，不与 feishu 重合
        assert r.overlap_matrix["webapp"]["dingtalk"] == 1
        assert r.overlap_matrix["feishu"]["dingtalk"] == 0

    def test_period_dates(self, report):
        today = datetime.now(timezone.utc).date()
        r = report([], ref_day=today)
        assert r.period_end == today
        assert r.period_start == today - timedelta(days=29)

    def test_serializable(self, report):
        today = datetime.now(timezone.utc).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        events = [_evt("u1", "webapp", now)]
        r = report(events, ref_day=today)
        d = r.to_dict()
        # 所有字段均可 JSON 序列化
        import json

        s = json.dumps(d)
        assert "unified" in s
        assert "by_platform" in s
        assert "cross_platform" in s
        assert "overlap" in s


# ---------------------------------------------------------------------------
# Test: API endpoints (smoke)
# ---------------------------------------------------------------------------


class TestCrossPlatformAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        from api.auth import require_role, get_current_user
        from api.analytics import cross_platform as cp

        # Inject isolated test store so we don't hit Supabase
        cp._TEST_STORE = cp._SessionStore(supabase=None)
        try:
            # Build a minimal app with auth override (avoids importing main.py
            # which would instantiate OpenAI / etc. and require real keys)
            app = FastAPI()

            async def fake_user():
                from contracts.shared import UserRole
                from uuid import uuid4

                return type(
                    "U",
                    (),
                    {"id": uuid4(), "email": "admin@test.com", "role": UserRole.admin},
                )()

            app.dependency_overrides[get_current_user] = fake_user

            # require_role internally depends on get_current_user, so the
            # override above propagates.

            app.include_router(cp.router)
            return TestClient(app)
        finally:
            # leave _TEST_STORE in place for next test to inspect; cleared
            # at module teardown if needed
            pass

    def test_post_sessions_smoke(self, client):
        r = client.post(
            "/sessions",
            json={
                "events": [
                    {
                        "user_id": "u1",
                        "platform": "webapp",
                        "occurred_at": "2025-07-01T10:00:00Z",
                    },
                    {
                        "user_id": "u1",
                        "platform": "feishu",
                        "occurred_at": "2025-07-01T11:00:00Z",
                    },
                ]
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] == 2
        assert body["total"] == 2

    def test_summary_endpoint_smoke(self, client):
        r = client.get("/cross-platform/summary")
        assert r.status_code == 200
        body = r.json()
        assert "by_platform" in body
        assert "unified" in body
        assert "cross_platform" in body
        assert len(body["by_platform"]) == 4

    def test_dau_series_endpoint_smoke(self, client):
        r = client.get("/cross-platform/dau?days=7")
        assert r.status_code == 200
        body = r.json()
        assert body["days"] == 7
        assert len(body["series"]) == 7
