"""v8.1 T3603 — Proactive Push tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.jobseeker.proactive_outreach import (
    OutreachMessage,
    ProactiveOutreachService,
    render_template,
)
from services.jobseeker.relationship import (
    RelationshipService,
    reset_relationship_service,
)
from services.platform.proactive_scheduler import (
    PushCandidate,
    ProactiveSchedulerService,
    get_proactive_scheduler,
    reset_proactive_scheduler,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_relationship_service()
    reset_proactive_scheduler()
    yield
    reset_relationship_service()
    reset_proactive_scheduler()


# ---------------------------------------------------------------------------
# T3603 Scheduler
# ---------------------------------------------------------------------------
def test_register_user():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", stage="active_job_seeker")
    cands = sched.evaluate_user("u1")
    # 没静默 → 不触发
    assert cands == []


def test_evaluate_user_re_engage():
    sched = ProactiveSchedulerService()
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    sched.register_user("u1", stage="active_job_seeker", last_interaction_at=past)
    cands = sched.evaluate_user("u1")
    assert any(c.trigger == "re_engage_3d" for c in cands)


def test_evaluate_user_long_break():
    sched = ProactiveSchedulerService()
    past = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    sched.register_user("u1", stage="active_job_seeker", last_interaction_at=past)
    cands = sched.evaluate_user("u1")
    assert any(c.trigger == "long_break" for c in cands)


def test_evaluate_user_new_jobs():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", new_jobs_count=10)
    cands = sched.evaluate_user("u1")
    assert any(c.trigger == "new_jobs" for c in cands)


def test_evaluate_user_no_new_jobs_below_threshold():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", new_jobs_count=3)
    cands = sched.evaluate_user("u1")
    assert not any(c.trigger == "new_jobs" for c in cands)


def test_evaluate_user_interview_tomorrow():
    sched = ProactiveSchedulerService()
    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    sched.register_user("u1", upcoming_interview_at=future)
    cands = sched.evaluate_user("u1")
    assert any(c.trigger == "interview_tomorrow" for c in cands)


def test_evaluate_user_interview_too_far():
    sched = ProactiveSchedulerService()
    future = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    sched.register_user("u1", upcoming_interview_at=future)
    cands = sched.evaluate_user("u1")
    assert not any(c.trigger == "interview_tomorrow" for c in cands)


def test_evaluate_user_interview_already_passed():
    sched = ProactiveSchedulerService()
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sched.register_user("u1", upcoming_interview_at=past)
    cands = sched.evaluate_user("u1")
    assert not any(c.trigger == "interview_tomorrow" for c in cands)


def test_evaluate_user_unknown_id():
    sched = ProactiveSchedulerService()
    assert sched.evaluate_user("ghost") == []


def test_stats_initial():
    sched = ProactiveSchedulerService()
    s = sched.stats()
    assert s["total"] == 0
    assert s["registered_users"] == 0


def test_get_logs_empty():
    sched = ProactiveSchedulerService()
    assert sched.get_logs() == []


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------
def test_render_template_re_engage():
    msg = render_template("re_engage_3d", name="小明", days=5)
    assert "小明" in msg.title
    assert msg.reason == "re_engage_3d"


def test_render_template_unknown():
    msg = render_template("unknown_reason")
    assert msg.title == "(unknown_reason)"


def test_render_template_offer_followup():
    msg = render_template("offer_followup", name="小红", company="字节")
    assert "字节" in msg.body


def test_render_template_birthday():
    msg = render_template("birthday", name="大明")
    assert "大明" in msg.title


def test_render_template_festival():
    msg = render_template("festival", festival_name="春节")
    assert "春节" in msg.title


def test_outreach_message_to_dict():
    msg = OutreachMessage(user_id="u1", reason="r", title="t", body="b")
    d = msg.to_dict()
    assert d["user_id"] == "u1"
    assert d["channels"] == ["in_app"]


@pytest.mark.asyncio
async def test_reach_out_respects_quiet_hours(monkeypatch):
    rel = RelationshipService()
    svc = ProactiveOutreachService(relationship=rel)

    # Force quiet hours — 通过 stub
    monkeypatch.setattr(rel, "in_quiet_hours", lambda: True)
    msg = await svc.reach_out("u1", "re_engage_3d", name="同学", days=0)
    assert msg.metadata.get("skipped") == "quiet_hours"


@pytest.mark.asyncio
async def test_reach_out_respects_quota(monkeypatch):
    rel = RelationshipService()
    svc = ProactiveOutreachService(relationship=rel)

    # Force no quiet hours, no quota
    monkeypatch.setattr(rel, "in_quiet_hours", lambda: False)
    monkeypatch.setattr(rel, "can_push", lambda uid, max_per_day=3: False)

    msg = await svc.reach_out("u1", "re_engage_3d", name="同学", days=0)
    assert msg.metadata.get("skipped") == "quota"


@pytest.mark.asyncio
async def test_reach_out_force_bypasses_checks(monkeypatch):
    rel = RelationshipService()
    svc = ProactiveOutreachService(relationship=rel)
    called = {"dispatch": False}

    async def fake_dispatch(self, msg):
        called["dispatch"] = True
        return {"success": True, "channels": msg.channels}

    monkeypatch.setattr(ProactiveOutreachService, "_dispatch", fake_dispatch)
    monkeypatch.setattr(rel, "in_quiet_hours", lambda: True)
    monkeypatch.setattr(rel, "can_push", lambda uid, max_per_day=3: False)

    msg = await svc.reach_out("u1", "re_engage_3d", name="同学", days=0, force=True)
    assert called["dispatch"] is True
    assert "skipped" not in msg.metadata


@pytest.mark.asyncio
async def test_run_scheduled_pass_executes(monkeypatch):
    sched = ProactiveSchedulerService()
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    sched.register_user("u1", stage="active_job_seeker", last_interaction_at=past)

    called = {"n": 0}

    async def fake_reach_out(self, *a, **kw):
        called["n"] += 1
        m = OutreachMessage(user_id=kw.get("user_id", "u1"), reason=kw.get("reason", "r"), title="t", body="b")
        m.metadata["skipped"] = "ok"  # 避免 record_push 触发
        return m

    monkeypatch.setattr(ProactiveOutreachService, "reach_out", fake_reach_out)

    # 调用 scheduler.run_once, 内部用 outreach.get_outreach_service()
    from services.jobseeker.proactive_outreach import reset_outreach_service, get_outreach_service
    reset_outreach_service()
    monkeypatch.setattr(
        "services.jobseeker.proactive_outreach.ProactiveOutreachService.reach_out",
        fake_reach_out,
    )

    logs = await sched.run_once()
    assert called["n"] >= 1
    assert len(logs) >= 1


def test_singleton_scheduler():
    a = get_proactive_scheduler()
    b = get_proactive_scheduler()
    assert a is b


def test_push_candidate_to_dict():
    c = PushCandidate(user_id="u1", trigger="re_engage_3d", reason="r")
    d = c.to_dict()
    assert d["user_id"] == "u1"
    assert d["trigger"] == "re_engage_3d"


def test_evaluate_user_combined_triggers():
    sched = ProactiveSchedulerService()
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    sched.register_user(
        "u1",
        stage="active_job_seeker",
        last_interaction_at=past,
        new_jobs_count=10,
    )
    cands = sched.evaluate_user("u1")
    triggers = {c.trigger for c in cands}
    assert "re_engage_3d" in triggers
    assert "new_jobs" in triggers


def test_evaluate_user_invalid_iso_date():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", last_interaction_at="not-a-date")
    # 不抛异常
    cands = sched.evaluate_user("u1")
    assert isinstance(cands, list)


def test_register_user_updates_existing():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", stage="active_job_seeker", new_jobs_count=1)
    sched.register_user("u1", stage="active_job_seeker", new_jobs_count=10)
    cands = sched.evaluate_user("u1")
    assert any(c.trigger == "new_jobs" for c in cands)


def test_interview_invalid_iso_returns_empty():
    sched = ProactiveSchedulerService()
    sched.register_user("u1", upcoming_interview_at="bad-date")
    cands = sched.evaluate_user("u1")
    # 不应触发
    assert not any(c.trigger == "interview_tomorrow" for c in cands)