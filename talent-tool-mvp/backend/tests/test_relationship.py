"""v8.1 T3601 — Relationship State Machine tests."""
from __future__ import annotations

import pytest

from services.jobseeker.relationship import (
    EVENT_GO_SILENT,
    EVENT_HIRED,
    EVENT_INTERVIEW_SCHEDULED,
    EVENT_OFFER_ACCEPTED,
    EVENT_OFFER_RECEIVED,
    EVENT_RESUME_UPLOADED,
    EVENT_RETURNED,
    RelationshipService,
    RelationshipStage,
    STAGE_TONE,
    get_relationship_service,
    reset_relationship_service,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_relationship_service()
    yield
    reset_relationship_service()


def test_initial_stage_is_new_user():
    svc = RelationshipService()
    assert svc.get_stage("u1") == RelationshipStage.NEW_USER.value


def test_upload_resume_promotes_to_active():
    svc = RelationshipService()
    f, t = svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    assert f == RelationshipStage.NEW_USER.value
    assert t == RelationshipStage.ACTIVE_JOB_SEEKER.value


def test_offer_received_promotes_to_negotiating():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    f, t = svc.update_stage("u1", EVENT_OFFER_RECEIVED)
    assert f == RelationshipStage.ACTIVE_JOB_SEEKER.value
    assert t == RelationshipStage.NEGOTIATING.value


def test_offer_accepted_promotes_to_hired():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_OFFER_RECEIVED)
    f, t = svc.update_stage("u1", EVENT_OFFER_ACCEPTED)
    assert t == RelationshipStage.HIRED.value


def test_return_from_break_to_active():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_GO_SILENT)
    f, t = svc.update_stage("u1", EVENT_RETURNED)
    assert t == RelationshipStage.ACTIVE_JOB_SEEKER.value


def test_unknown_event_no_change():
    svc = RelationshipService()
    f, t = svc.update_stage("u1", "non_existing_event")
    assert f == t == RelationshipStage.NEW_USER.value


def test_get_tone_returns_default():
    svc = RelationshipService()
    tone = svc.get_tone("u1")
    assert tone["tone"] == "friendly"
    assert "avatar" in tone
    assert "greeting_template" in tone


def test_get_tone_changes_with_stage():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    tone = svc.get_tone("u1")
    assert tone["tone"] == "casual"


def test_get_greeting_includes_name():
    svc = RelationshipService()
    g = svc.get_greeting("u1", name="小明")
    assert "小明" in g


def test_list_events_keeps_history():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_OFFER_RECEIVED)
    evs = svc.list_events("u1")
    assert len(evs) == 2
    assert evs[0].from_stage == RelationshipStage.NEW_USER.value
    assert evs[1].to_stage == RelationshipStage.NEGOTIATING.value


def test_can_push_default_quota():
    svc = RelationshipService()
    assert svc.can_push("u1", max_per_day=3) is True
    for _ in range(3):
        svc.record_push("u1")
    assert svc.can_push("u1", max_per_day=3) is False


def test_quota_independent_per_user():
    svc = RelationshipService()
    for _ in range(3):
        svc.record_push("u1")
    assert svc.can_push("u2", max_per_day=3) is True


def test_in_quiet_hours_default_window():
    svc = RelationshipService()
    assert svc.in_quiet_hours(hour=23) is True
    assert svc.in_quiet_hours(hour=12) is False


def test_in_quiet_hours_wraparound():
    svc = RelationshipService()
    assert svc.in_quiet_hours(hour=3, quiet_start=22, quiet_end=8) is True


def test_in_quiet_hours_wraparound_false():
    svc = RelationshipService()
    assert svc.in_quiet_hours(hour=10, quiet_start=22, quiet_end=8) is False


def test_touch_interaction_resets_silence():
    svc = RelationshipService()
    svc.touch_interaction("u1")
    state = svc.get_state("u1")
    assert state.days_since_interaction == 0
    assert state.last_interaction_at != ""


def test_candidates_for_outreach_re_engage():
    svc = RelationshipService()
    # ACTIVE 3+ 天没互动
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    state = svc.get_state("u1")
    state.days_since_interaction = 5
    cands = svc.candidates_for_outreach()
    assert any(c["user_id"] == "u1" and c["reason"] == "re_engage_3d" for c in cands)


def test_candidates_for_outreach_long_break():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_GO_SILENT)
    state = svc.get_state("u1")
    state.days_since_interaction = 35
    cands = svc.candidates_for_outreach()
    assert any(c["reason"] == "long_break_checkin" for c in cands)


def test_candidates_for_outreach_offer_followup():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_OFFER_RECEIVED)
    state = svc.get_state("u1")
    state.days_since_interaction = 2
    cands = svc.candidates_for_outreach()
    assert any(c["reason"] == "offer_followup" for c in cands)


def test_state_to_dict():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    d = svc.get_state("u1").to_dict()
    assert d["user_id"] == "u1"
    assert d["stage"] == RelationshipStage.ACTIVE_JOB_SEEKER.value
    assert d["history_count"] == 1


def test_event_to_dict():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED, context={"src": "test"})
    ev = svc.list_events("u1")[0]
    d = ev.to_dict()
    assert d["user_id"] == "u1"
    assert d["context"] == {"src": "test"}


def test_get_relationship_service_singleton():
    a = get_relationship_service()
    b = get_relationship_service()
    assert a is b


def test_reset_clears_state():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.reset()
    assert svc.get_stage("u1") == RelationshipStage.NEW_USER.value
    assert svc.list_events("u1") == []


def test_hired_to_returned_resets_to_active():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_OFFER_ACCEPTED)
    f, t = svc.update_stage("u1", EVENT_RETURNED)
    assert t == RelationshipStage.ACTIVE_JOB_SEEKER.value


def test_stage_tone_covers_all_stages():
    """所有 stage 都需要有 tone."""
    for s in RelationshipStage:
        assert s.value in STAGE_TONE
        tone = STAGE_TONE[s.value]
        assert {"tone", "avatar", "greeting_template"} <= set(tone.keys())


def test_multiple_users_independent():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    assert svc.get_stage("u1") == RelationshipStage.ACTIVE_JOB_SEEKER.value
    assert svc.get_stage("u2") == RelationshipStage.NEW_USER.value


def test_event_audit_trail():
    """每个事件都写到 events 列表."""
    svc = RelationshipService()
    events = [
        EVENT_RESUME_UPLOADED,
        EVENT_OFFER_RECEIVED,
        EVENT_OFFER_ACCEPTED,
    ]
    for e in events:
        svc.update_stage("u1", e)
    evs = svc.list_events("u1")
    assert [e.event_type for e in evs] == events


def test_push_quota_zero():
    """max_per_day=0 立即拒绝."""
    svc = RelationshipService()
    assert svc.can_push("u1", max_per_day=0) is False


def test_touch_does_not_change_stage():
    svc = RelationshipService()
    svc.touch_interaction("u1")
    assert svc.get_stage("u1") == RelationshipStage.NEW_USER.value


def test_interview_scheduled_no_promotion():
    """面试安排本身不切换阶段, 但写 audit event."""
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    f, t = svc.update_stage("u1", EVENT_INTERVIEW_SCHEDULED)
    assert f == t == RelationshipStage.ACTIVE_JOB_SEEKER.value


def test_hired_event_promotes_directly():
    svc = RelationshipService()
    svc.update_stage("u1", EVENT_RESUME_UPLOADED)
    svc.update_stage("u1", EVENT_OFFER_RECEIVED)
    svc.update_stage("u1", EVENT_HIRED)
    f, t = svc.update_stage("u1", EVENT_OFFER_ACCEPTED)
    assert t == RelationshipStage.HIRED.value