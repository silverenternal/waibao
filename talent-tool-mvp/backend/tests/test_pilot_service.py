"""T1702 — Pilot 服务层单测 (pilot_service.py)."""
from __future__ import annotations

import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Reuse the fake Supabase store from test_pilot.py
# ---------------------------------------------------------------------------

from tests.test_pilot import FakeStore  # type: ignore

# 把模块引用先 import, 让 monkeypatch.setattr 能解析
import services.integrations.pilot_service  # noqa: F401
import services.integrations.pilot_invitation  # noqa: F401
import api.pilot  # noqa: F401
import api.deps  # noqa: F401


@pytest.fixture
def fake_supabase(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("api.deps.get_supabase_admin", lambda: store)
    monkeypatch.setattr("services.integrations.pilot_invitation.get_supabase_admin", lambda: store)
    monkeypatch.setattr("services.integrations.pilot_service.get_supabase_admin", lambda: store)
    monkeypatch.setattr("api.pilot.get_supabase_admin", lambda: store)
    return store


@pytest.fixture
def fake_dispatch(monkeypatch):
    calls: list[dict] = []

    async def _dispatch(*, channel, user_id, title, content, payload=None, recipients=None):
        calls.append({"channel": channel, "user_id": user_id, "title": title, "content": content})
        return True

    monkeypatch.setattr("services.notify.dispatch", _dispatch)
    return calls


# ---------------------------------------------------------------------------
# compute_nps
# ---------------------------------------------------------------------------


def test_compute_nps_classic():
    from services.integrations.pilot_service import compute_nps

    res = compute_nps([10, 10, 9, 8, 7, 6, 0])
    # 3 promoter (10,10,9) + 2 passive (8,7) + 2 detractor (6,0) = 7
    assert res["promoters"] == 3
    assert res["passives"] == 2
    assert res["detractors"] == 2
    assert res["responses"] == 7
    # (3 - 2) / 7 = 14.2857... → 14.3
    assert res["nps"] == 14.3


def test_compute_nps_empty_returns_none():
    from services.integrations.pilot_service import compute_nps

    res = compute_nps([])
    assert res["nps"] is None
    assert res["responses"] == 0


def test_compute_nps_ignores_none_scores():
    from services.integrations.pilot_service import compute_nps

    res = compute_nps([10, None, 9, None])
    assert res["responses"] == 2
    assert res["promoters"] == 2
    assert res["nps"] == 100.0


def test_compute_nps_all_promoters():
    from services.integrations.pilot_service import compute_nps

    res = compute_nps([10, 9, 10])
    assert res["promoters"] == 3
    assert res["passives"] == 0
    assert res["detractors"] == 0
    assert res["nps"] == 100.0


def test_compute_nps_all_detractors():
    from services.integrations.pilot_service import compute_nps

    res = compute_nps([0, 1, 6])
    assert res["detractors"] == 3
    assert res["nps"] == -100.0


# ---------------------------------------------------------------------------
# create_program
# ---------------------------------------------------------------------------


def test_create_program_inserts_row(fake_supabase):
    from services.integrations.pilot_service import create_program

    row = create_program(
        organisation_id="org-1",
        name="Acme Pilot",
        target_nps=45,
        max_users=10,
        created_by="user-1",
    )
    assert row["name"] == "Acme Pilot"
    assert row["status"] == "recruiting"
    assert row["target_nps"] == 45
    assert row["max_users"] == 10
    assert row["metadata"]["created_by"] == "user-1"
    # stored
    assert fake_supabase.tables["pilot_programs"][0]["id"] == row["id"]


def test_create_program_validates_name(fake_supabase):
    from services.integrations.pilot_service import create_program

    with pytest.raises(ValueError):
        create_program(organisation_id="org-1", name="A")
    with pytest.raises(ValueError):
        create_program(organisation_id="org-1", name="")


def test_create_program_validates_org(fake_supabase):
    from services.integrations.pilot_service import create_program

    with pytest.raises(ValueError):
        create_program(organisation_id="", name="Acme")


def test_create_program_clamps_extreme_nps(fake_supabase):
    from services.integrations.pilot_service import create_program

    row = create_program(organisation_id="org-1", name="Acme Pilot", target_nps=999)
    assert row["target_nps"] == 100


# ---------------------------------------------------------------------------
# invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_creates_invitation(fake_supabase, fake_dispatch):
    from services.integrations.pilot_service import invite

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "P1", "status": "active", "max_users": 10},
    ]

    inv = await invite(program_id="prog-1", email="alice@x.com", role="employer")
    assert inv.email == "alice@x.com"
    assert inv.status == "pending"
    rows = fake_supabase.tables["pilot_invitations"]
    assert len(rows) == 1
    assert rows[0]["program_id"] == "prog-1"


@pytest.mark.asyncio
async def test_invite_rejects_completed_program(fake_supabase, fake_dispatch):
    from services.integrations.pilot_service import invite

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "P1", "status": "completed", "max_users": 10},
    ]
    with pytest.raises(ValueError):
        await invite(program_id="prog-1", email="a@b.com")


@pytest.mark.asyncio
async def test_invite_program_not_found(fake_supabase):
    from services.integrations.pilot_service import invite

    with pytest.raises(LookupError):
        await invite(program_id="missing", email="a@b.com")


@pytest.mark.asyncio
async def test_invite_enforces_max_users(fake_supabase, fake_dispatch):
    from services.integrations.pilot_service import invite

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "P1", "status": "active", "max_users": 2},
    ]
    fake_supabase.tables["pilot_invitations"] = [
        {"id": "i1", "program_id": "prog-1", "status": "accepted", "email": "a@x.com"},
        {"id": "i2", "program_id": "prog-1", "status": "accepted", "email": "b@x.com"},
    ]
    with pytest.raises(ValueError):
        await invite(program_id="prog-1", email="c@x.com")


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


def test_get_stats_aggregates_nps_and_pain_points(fake_supabase):
    from services.integrations.pilot_service import get_stats

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "target_nps": 40, "max_users": 20, "status": "active"},
    ]
    fake_supabase.tables["pilot_invitations"] = [
        {"id": "i1", "program_id": "prog-1", "status": "accepted", "email": "a@x.com", "accepted_at": "2026-01-01"},
        {"id": "i2", "program_id": "prog-1", "status": "accepted", "email": "b@x.com", "accepted_at": "2026-01-02"},
        {"id": "i3", "program_id": "prog-1", "status": "pending", "email": "c@x.com"},
    ]
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": "", "feature_used": None},
        {"id": "f2", "program_id": "prog-1", "category": "nps", "score": 9, "comment": "", "feature_used": None},
        {"id": "f3", "program_id": "prog-1", "category": "nps", "score": 5, "comment": "", "feature_used": None},
        {"id": "f4", "program_id": "prog-1", "category": "bug", "comment": "页面崩溃", "feature_used": "matching"},
        {"id": "f5", "program_id": "prog-1", "category": "feature_request", "comment": "希望增加导出功能", "feature_used": "export"},
    ]
    # funnel_events query raises → gracefully skipped
    fake_supabase.tables["funnel_events"] = []

    stats = get_stats("prog-1")
    assert stats.invitations_total == 3
    assert stats.invitations_accepted == 2
    assert stats.nps_responses == 3
    assert stats.promoters == 2
    assert stats.detractors == 1
    assert stats.nps == round((2 - 1) / 3 * 100, 1)
    assert stats.feedback_total == 5
    assert stats.feedback_by_category["bug"] == 1
    assert len(stats.top_pain_points) >= 1
    # targets_met filled
    assert "nps" in stats.targets_met
    assert "weekly_active" in stats.targets_met
    assert "top_pain_points" in stats.targets_met


def test_get_stats_program_not_found(fake_supabase):
    from services.integrations.pilot_service import get_stats

    with pytest.raises(LookupError):
        get_stats("missing")


def test_get_stats_handles_empty_feedback(fake_supabase):
    from services.integrations.pilot_service import get_stats

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "target_nps": 40, "max_users": 10, "status": "recruiting"},
    ]
    stats = get_stats("prog-1")
    assert stats.nps is None
    assert stats.feedback_total == 0
    assert stats.top_pain_points == []


# ---------------------------------------------------------------------------
# end_program
# ---------------------------------------------------------------------------


def test_end_program_writes_metadata(fake_supabase):
    from services.integrations.pilot_service import end_program

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "status": "active", "metadata": {"existing": "value"}},
    ]
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": ""},
    ]
    fake_supabase.tables["pilot_invitations"] = []

    row = end_program(program_id="prog-1", final_notes="good run")
    assert row["status"] == "completed"
    assert row["ended_at"] is not None
    meta = row["metadata"]
    assert meta["existing"] == "value"  # 保留
    assert meta["ended_notes"] == "good run"
    assert "final_nps" in meta
    assert "targets_met" in meta


def test_end_program_rejects_already_completed(fake_supabase):
    from services.integrations.pilot_service import end_program

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "status": "completed", "metadata": {}},
    ]
    with pytest.raises(ValueError):
        end_program(program_id="prog-1")


def test_end_program_not_found(fake_supabase):
    from services.integrations.pilot_service import end_program

    with pytest.raises(LookupError):
        end_program(program_id="missing")


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


def test_generate_report_returns_full_payload(fake_supabase):
    from services.integrations.pilot_service import generate_report

    fake_supabase.tables["organisations"] = [{"id": "org-1", "name": "Acme"}]
    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "Acme Pilot", "status": "active", "target_nps": 50,
         "max_users": 20, "metadata": {}, "organisation_id": "org-1"},
    ]
    fake_supabase.tables["pilot_invitations"] = [
        {"id": "i1", "program_id": "prog-1", "status": "accepted", "email": "a@x.com", "role": "employer"},
        {"id": "i2", "program_id": "prog-1", "status": "pending", "email": "b@x.com", "role": "jobseeker"},
    ]
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": "好用",
         "feature_used": "matching", "user_id": "u1", "created_at": "2026-01-01"},
    ]

    report = generate_report("prog-1")
    # 注: FakeStore 不展开 *, organisations(name) join, 这里只验证主要字段
    assert report.program_name == "Acme Pilot"
    assert "employer/accepted" in report.invitation_breakdown
    assert len(report.feedback_samples) == 1
    assert report.stats.nps_responses == 1
    assert report.stats.target_nps == 50


def test_generate_report_program_not_found(fake_supabase):
    from services.integrations.pilot_service import generate_report

    with pytest.raises(LookupError):
        generate_report("missing")


# ---------------------------------------------------------------------------
# list_programs / get_program
# ---------------------------------------------------------------------------


def test_list_programs_filters_by_status(fake_supabase):
    from services.integrations.pilot_service import list_programs

    fake_supabase.tables["pilot_programs"] = [
        {"id": "p1", "name": "A", "status": "active"},
        {"id": "p2", "name": "B", "status": "recruiting"},
    ]
    rows = list_programs(status="active")
    assert len(rows) == 1
    assert rows[0]["id"] == "p1"


def test_get_program_returns_with_org(fake_supabase):
    from services.integrations.pilot_service import get_program

    fake_supabase.tables["organisations"] = [{"id": "org-1", "name": "Acme"}]
    fake_supabase.tables["pilot_programs"] = [
        {"id": "p1", "name": "X", "organisation_id": "org-1"},
    ]
    p = get_program("p1")
    assert p["name"] == "X"


def test_get_program_not_found(fake_supabase):
    from services.integrations.pilot_service import get_program

    with pytest.raises(LookupError):
        get_program("missing")


# ---------------------------------------------------------------------------
# Weekly active calculation
# ---------------------------------------------------------------------------


def test_compute_weekly_active_basic(fake_supabase):
    from services.integrations.pilot_service import _compute_weekly_active

    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=1)).isoformat()
    old_iso = (now - timedelta(days=14)).isoformat()

    invitations = [
        {"status": "accepted", "email": "a@x.com", "accepted_at": cutoff_iso, "user_id": None},
        {"status": "accepted", "email": "b@x.com", "accepted_at": cutoff_iso, "user_id": None},
    ]
    events = [
        {"user_id": None, "metadata": {"email": "a@x.com"}, "created_at": cutoff_iso},
        {"user_id": None, "metadata": {"email": "b@x.com"}, "created_at": old_iso},  # 过期
    ]
    wau, rate = _compute_weekly_active(invitations=invitations, events=events)
    assert wau == 1
    assert rate == 0.5


def test_compute_weekly_active_no_accepted(fake_supabase):
    from services.integrations.pilot_service import _compute_weekly_active

    invitations = [{"status": "pending", "email": "a@x.com"}]
    events = []
    wau, rate = _compute_weekly_active(invitations=invitations, events=events)
    assert wau == 0
    assert rate == 0.0


def test_compute_weekly_active_empty_invitations():
    from services.integrations.pilot_service import _compute_weekly_active

    wau, rate = _compute_weekly_active(invitations=[], events=[])
    assert wau == 0
    assert rate == 0.0