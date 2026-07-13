"""Tests for v8.0 T3902 — feedback_v2 API.

Covers:
* classify_feedback: bug/feature/perf/exp/other
* score_priority: critical/high/medium/low
* FEEDBACK_TYPES / CATEGORIES / PRIORITIES exports
* FeedbackV2Create validation
* POST /api/feedback/v2 (offline stub + supabase)
* GET /api/feedback/v2/list
* GET /api/feedback/v2/trend
* POST /api/feedback/v2/{id}/status
* 鉴权 (admin only for list/trend/status)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import get_current_user
from api.feedback_v2 import (
    CATEGORIES,
    FEEDBACK_TYPES,
    PRIORITIES,
    classify_feedback,
    router,
    score_priority,
)


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------


def test_feedback_types_constant():
    assert "rating" in FEEDBACK_TYPES
    assert "bug" in FEEDBACK_TYPES
    assert "feature" in FEEDBACK_TYPES


def test_categories_constant():
    for c in ("bug", "feature", "experience", "performance", "other"):
        assert c in CATEGORIES


def test_priorities_constant():
    for p in ("critical", "high", "medium", "low"):
        assert p in PRIORITIES


# ---------------------------------------------------------------------------
# 2. classify_feedback
# ---------------------------------------------------------------------------


def test_classify_bug_keywords_chinese():
    assert classify_feedback(None, "页面崩溃了") == "bug"
    assert classify_feedback(None, "卡死报错") == "bug"


def test_classify_bug_keywords_english():
    assert classify_feedback(None, "App crashes on launch") == "bug"
    assert classify_feedback(None, "Error 500 when login") == "bug"


def test_classify_feature_keywords():
    assert classify_feedback(None, "希望增加暗色模式") == "feature"
    assert classify_feedback(None, "Could you add a dark mode?") == "feature"


def test_classify_performance_keywords():
    assert classify_feedback(None, "页面加载太慢") == "performance"
    assert classify_feedback(None, "Loading too long") == "performance"


def test_classify_experience_keywords():
    assert classify_feedback(None, "界面不太友好") == "experience"
    assert classify_feedback(None, "UX is confusing") == "experience"


def test_classify_no_match_returns_other():
    assert classify_feedback(None, "hello world") == "other"


def test_classify_with_explicit_category():
    assert classify_feedback("bug", "some comment") == "bug"
    assert classify_feedback("performance", "long text") == "performance"


def test_classify_invalid_hint_falls_back_to_keywords():
    assert classify_feedback("invalid", "崩溃了") == "bug"


# ---------------------------------------------------------------------------
# 3. score_priority
# ---------------------------------------------------------------------------


def test_score_priority_low_rating_is_high_for_bug():
    p = score_priority("bug", 1, "页面报错")
    assert p in ("high", "medium")


def test_score_priority_critical_keywords():
    p = score_priority("feature", None, "production bug, need urgent fix")
    assert p == "critical"


def test_score_priority_bug_with_many_keywords():
    p = score_priority("bug", None, "报错 失败 无法")
    assert p == "high"


def test_score_priority_feature_is_low():
    p = score_priority("feature", None, "希望加个功能")
    assert p == "low"


def test_score_priority_experience_is_low():
    p = score_priority("experience", None, "界面体验差")
    assert p == "low"


def test_score_priority_performance_is_medium():
    p = score_priority("performance", None, "页面加载慢")
    assert p == "medium"


def test_score_priority_other_is_low():
    p = score_priority("other", None, "随便说说")
    assert p == "low"


# ---------------------------------------------------------------------------
# 4. FastAPI app & client
# ---------------------------------------------------------------------------


def _make_user(role: str = "user", tenant_id: str = "t-1", user_id: str = "u-1"):
    u = MagicMock()
    u.id = user_id
    u.role = role
    u.tenant_id = tenant_id
    return u


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    # 默认 user
    a.dependency_overrides[get_current_user] = lambda: _make_user()
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def admin_client():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: _make_user(role="admin")
    return TestClient(a)


@pytest.fixture
def user_client():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: _make_user(role="user")
    return TestClient(a)


# ---------------------------------------------------------------------------
# 5. POST /api/feedback/v2
# ---------------------------------------------------------------------------


def test_submit_feedback_offline_returns_stub(client):
    r = client.post(
        "/api/feedback/v2",
        json={"type": "bug", "comment": "页面崩溃了", "rating": 2, "page": "/home"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "bug"
    assert data["category"] == "bug"
    assert data["priority"] in PRIORITIES
    assert data["status"] == "open"
    assert data["page"] == "/home"


def test_submit_feedback_with_supabase(client):
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "fb-001"}
    ]
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = client.post(
            "/api/feedback/v2",
            json={"type": "feature", "comment": "希望增加暗色模式"},
        )
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == "fb-001"
    assert data["category"] == "feature"


def test_submit_feedback_rating_low(client):
    r = client.post(
        "/api/feedback/v2",
        json={"type": "rating", "rating": 2, "comment": "体验差"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["category"] == "experience"
    assert data["rating"] == 2


def test_submit_feedback_rating_high(client):
    r = client.post(
        "/api/feedback/v2",
        json={"type": "rating", "rating": 5, "comment": "good"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["category"] == "other"


def test_submit_feedback_invalid_type_422(client):
    r = client.post(
        "/api/feedback/v2",
        json={"type": "wrong", "comment": "x"},
    )
    assert r.status_code == 422


def test_submit_feedback_short_comment_422(client):
    r = client.post(
        "/api/feedback/v2",
        json={"type": "bug", "comment": ""},
    )
    assert r.status_code == 422


def test_submit_feedback_metadata_merged(client):
    r = client.post(
        "/api/feedback/v2",
        json={
            "type": "performance",
            "comment": "加载慢",
            "page": "/jobs",
            "feature": "matching",
            "metadata": {"ua": "test"},
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["metadata"]["page"] == "/jobs"
    assert data["metadata"]["feature"] == "matching"
    assert data["metadata"]["ua"] == "test"
    assert data["metadata"]["source_type"] == "performance"


# ---------------------------------------------------------------------------
# 6. GET /api/feedback/v2/list
# ---------------------------------------------------------------------------


def test_list_feedback_admin_only(user_client):
    r = user_client.get("/api/feedback/v2/list")
    assert r.status_code == 403


def test_list_feedback_offline_empty(admin_client):
    with patch("api.feedback_v2.get_supabase_admin", return_value=None):
        r = admin_client.get("/api/feedback/v2/list")
    assert r.status_code == 200
    data = r.json()
    assert data["data"] == []


def test_list_feedback_with_data(admin_client):
    sb = MagicMock()
    sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "1", "type": "bug", "category": "bug", "priority": "high",
            "rating": None, "title": "x", "comment": "x", "page": None,
            "feature": None, "user_id": "u", "tenant_id": "t",
            "metadata": {}, "created_at": "2026-07-13T00:00:00Z", "status": "open"
        }
    ]
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = admin_client.get("/api/feedback/v2/list")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert "bug" in data["by_type"]


def test_list_feedback_with_filters(admin_client):
    sb = MagicMock()
    chain = sb.table.return_value
    chain.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = admin_client.get("/api/feedback/v2/list?type=bug&priority=high")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 7. GET /api/feedback/v2/trend
# ---------------------------------------------------------------------------


def test_trend_admin_only(user_client):
    r = user_client.get("/api/feedback/v2/trend")
    assert r.status_code == 403


def test_trend_offline_empty(admin_client):
    with patch("api.feedback_v2.get_supabase_admin", return_value=None):
        r = admin_client.get("/api/feedback/v2/trend")
    assert r.status_code == 200
    data = r.json()
    assert data["days"] == 14
    assert data["buckets"] == []


def test_trend_with_data(admin_client):
    sb = MagicMock()
    sb.table.return_value.select.return_value.gte.return_value.execute.return_value.data = [
        {"category": "bug", "priority": "critical", "created_at": "2026-07-10T00:00:00Z"},
        {"category": "bug", "priority": "high", "created_at": "2026-07-10T01:00:00Z"},
        {"category": "feature", "priority": "low", "created_at": "2026-07-11T00:00:00Z"},
    ]
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = admin_client.get("/api/feedback/v2/trend?days=7")
    assert r.status_code == 200
    data = r.json()
    assert data["days"] == 7
    assert len(data["buckets"]) == 2
    by_date = {b["date"]: b for b in data["buckets"]}
    assert by_date["2026-07-10"]["total"] == 2
    assert by_date["2026-07-10"]["critical"] == 1
    assert by_date["2026-07-10"]["high"] == 1
    assert data["top_categories"][0]["category"] == "bug"


# ---------------------------------------------------------------------------
# 8. POST /api/feedback/v2/{id}/status
# ---------------------------------------------------------------------------


def test_update_status_admin_only(user_client):
    r = user_client.post("/api/feedback/v2/fb-1/status?status=resolved")
    assert r.status_code == 403


def test_update_status_no_supabase(admin_client):
    with patch("api.feedback_v2.get_supabase_admin", return_value=None):
        r = admin_client.post("/api/feedback/v2/fb-1/status?status=resolved")
    assert r.status_code == 503


def test_update_status_invalid_status(admin_client):
    sb = MagicMock()
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = admin_client.post("/api/feedback/v2/fb-1/status?status=invalid")
    assert r.status_code == 422


def test_update_status_success(admin_client):
    sb = MagicMock()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"id": "fb-1"}]
    with patch("api.feedback_v2.get_supabase_admin", return_value=sb):
        r = admin_client.post("/api/feedback/v2/fb-1/status?status=resolved")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "resolved"
    assert data["updated"] is True


# ---------------------------------------------------------------------------
# 9. Pydantic models
# ---------------------------------------------------------------------------


def test_feedback_create_minimum_fields():
    from api.feedback_v2 import FeedbackV2Create
    body = FeedbackV2Create(type="bug", comment="x")
    assert body.type == "bug"
    assert body.rating is None
    assert body.metadata == {}


def test_feedback_create_with_all_fields():
    from api.feedback_v2 import FeedbackV2Create
    body = FeedbackV2Create(
        type="feature", rating=4, title="hi", comment="add dark mode",
        page="/settings", feature="theme", metadata={"k": "v"},
    )
    assert body.title == "hi"
    assert body.page == "/settings"
    assert body.metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# 10. Module exports
# ---------------------------------------------------------------------------


def test_module_exports_router():
    import api.feedback_v2 as m
    assert m.router is not None
    assert "router" in m.__all__


def test_module_exports_helpers():
    import api.feedback_v2 as m
    assert callable(m.classify_feedback)
    assert callable(m.score_priority)
