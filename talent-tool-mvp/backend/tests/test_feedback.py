"""Tests for T1106 — Feedback API."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# Reuse FakeStore from test_pilot.py
from tests.test_pilot import FakeStore  # type: ignore


@pytest.fixture
def fake_supabase(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("api.deps.get_supabase_admin", lambda: store)
    monkeypatch.setattr("api.feedback.get_supabase_admin", lambda: store)
    return store


def _user(user_id="11111111-1111-1111-1111-111111111111", email="a@b.com"):
    from api.auth import CurrentUser
    from contracts.shared import UserRole
    from uuid import UUID
    return CurrentUser(id=UUID(user_id), email=email, role=UserRole.client)


@pytest.mark.asyncio
async def test_submit_nps_writes_correct_bucket(fake_supabase):
    """NPS 9 -> promoter; 7 -> passive; 3 -> detractor."""
    from api.feedback import submit_nps, NPSCreate

    cases = [(10, "promoter"), (9, "promoter"), (8, "passive"), (7, "passive"), (3, "detractor"), (0, "detractor")]
    for score, expected_bucket in cases:
        body = NPSCreate(score=score, comment=f"test {score}")
        out = await submit_nps(body, _user())
        assert out["bucket"] == expected_bucket
        assert out["score"] == score

    rows = fake_supabase.tables["pilot_feedback"]
    assert len(rows) == len(cases)
    for r, (score, bucket) in zip(rows, cases):
        assert r["category"] == "nps"
        assert r["score"] == score
        assert r["metadata"]["bucket"] == bucket


@pytest.mark.asyncio
async def test_submit_feedback_validates_category():
    """category 必须白名单."""
    from api.feedback import FeedbackCreate

    with pytest.raises(Exception):  # pydantic ValidationError
        FeedbackCreate(category="invalid", comment="x")


@pytest.mark.asyncio
async def test_submit_feedback_inserts_row(fake_supabase):
    from api.feedback import submit_feedback, FeedbackCreate

    body = FeedbackCreate(
        category="bug",
        comment="匹配页加载慢",
        feature_used="matching",
        metadata={"path": "/match"},
    )
    out = await submit_feedback(body, _user())
    assert out["category"] == "bug"
    # user_id 写入时被 str() -> UUID 字符串
    assert out["user_id"] == "11111111-1111-1111-1111-111111111111"
    rows = fake_supabase.tables["pilot_feedback"]
    assert len(rows) == 1
    assert rows[0]["metadata"]["path"] == "/match"


@pytest.mark.asyncio
async def test_quick_survey_average_score_in_2_to_10_range(fake_supabase):
    """平均分 1-5 -> score 字段 2-10 (便于和 NPS 同图)."""
    from api.feedback import submit_quick_survey, QuickSurveyCreate

    body = QuickSurveyCreate(easy_to_use=5, value=4, speed=5, comment="nice")
    out = await submit_quick_survey(body, _user())
    assert out["average"] == pytest.approx(4.67, rel=0.01)

    row = fake_supabase.tables["pilot_feedback"][0]
    assert row["category"] == "survey"
    # avg 4.67 * 2 = 9.34 -> round = 9
    assert row["score"] == 9
    assert row["metadata"]["easy_to_use"] == 5
    assert row["metadata"]["value"] == 4
    assert row["metadata"]["speed"] == 5


@pytest.mark.asyncio
async def test_quick_survey_validates_range():
    """1-5 分,超出范围要失败."""
    from api.feedback import QuickSurveyCreate

    with pytest.raises(Exception):
        QuickSurveyCreate(easy_to_use=6, value=3, speed=3)
    with pytest.raises(Exception):
        QuickSurveyCreate(easy_to_use=0, value=3, speed=3)


@pytest.mark.asyncio
async def test_nps_score_out_of_range_rejected():
    """0-10 范围."""
    from api.feedback import NPSCreate

    with pytest.raises(Exception):
        NPSCreate(score=11)
    with pytest.raises(Exception):
        NPSCreate(score=-1)


@pytest.mark.asyncio
async def test_my_feedback_returns_user_scoped_rows(fake_supabase):
    """my_feedback 调用 supabase.eq + execute -> 至少返回 data/total 字段."""
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "user_id": "11111111-1111-1111-1111-111111111111", "category": "nps", "score": 9, "created_at": "2026-07-01T00:00:00Z"},
        {"id": "f2", "user_id": "11111111-1111-1111-1111-111111111111", "category": "bug", "comment": "x", "created_at": "2026-07-02T00:00:00Z"},
        {"id": "f3", "user_id": "22222222-2222-2222-2222-222222222222", "category": "nps", "score": 5, "created_at": "2026-07-03T00:00:00Z"},
    ]
    from api.feedback import my_feedback

    out = await my_feedback(_user(), limit=50)
    assert "data" in out
    assert "total" in out