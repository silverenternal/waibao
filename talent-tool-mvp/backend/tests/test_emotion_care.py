"""v8.1 T3604 — Emotion Care tests."""
from __future__ import annotations

import pytest

from services.jobseeker.emotion_care import (
    CARE_LEVEL_HEAVY,
    CARE_LEVEL_LIGHT,
    CARE_LEVEL_MEDIUM,
    CareAction,
    CareTicket,
    EmotionCareService,
    get_emotion_care_service,
    reset_emotion_care_service,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_emotion_care_service()
    yield
    reset_emotion_care_service()


def test_resources_loaded():
    svc = EmotionCareService()
    assert len(svc.categories()) > 0
    assert len(svc.resources_for("anxiety")) > 0


def test_resources_for_unknown_category():
    svc = EmotionCareService()
    assert svc.resources_for("__unknown__") == []


def test_resources_limit():
    svc = EmotionCareService()
    items = svc.resources_for("anxiety", limit=3)
    assert len(items) <= 3


def test_categories_count():
    svc = EmotionCareService()
    cats = svc.categories()
    assert len(cats) >= 10


def test_determine_level_light():
    assert EmotionCareService.determine_level("mild", intensity=0.4) == CARE_LEVEL_LIGHT


def test_determine_level_medium():
    assert EmotionCareService.determine_level("moderate", intensity=0.5) == CARE_LEVEL_MEDIUM


def test_determine_level_heavy():
    assert EmotionCareService.determine_level("severe") == CARE_LEVEL_HEAVY


def test_determine_level_intensity_driven_heavy():
    assert EmotionCareService.determine_level("none", intensity=0.95) == CARE_LEVEL_HEAVY


def test_determine_level_intensity_driven_medium():
    assert EmotionCareService.determine_level("none", intensity=0.65) == CARE_LEVEL_MEDIUM


def test_trigger_care_light():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="压力有点大", intensity=0.4)
    assert ticket.level == CARE_LEVEL_LIGHT
    assert ticket.risk_level == "mild"


def test_trigger_care_medium_creates_actions():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="moderate", primary_emotion="stress", trigger_text="工作中压力", intensity=0.6)
    actions = svc.list_actions(ticket.id)
    assert len(actions) >= 3  # warm + resource + callback
    types = {a.action_type for a in actions}
    assert "warm_message" in types
    assert "send_resource" in types
    assert "schedule_hr_callback" in types


def test_trigger_care_heavy_creates_extra_actions():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="severe", primary_emotion="anxiety", trigger_text="我撑不住了", intensity=0.95)
    actions = svc.list_actions(ticket.id)
    types = {a.action_type for a in actions}
    assert "notify_hr" in types
    assert "send_crisis_resource" in types


def test_trigger_care_records_hr_notified_for_heavy():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="severe", primary_emotion="anxiety", trigger_text="help", intensity=0.95)
    assert ticket.hr_notified is True


def test_trigger_care_medium_no_hr_notified():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="moderate", primary_emotion="anxiety", trigger_text="x", intensity=0.6)
    assert ticket.hr_notified is False


def test_close_ticket():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    closed = svc.close_ticket(ticket.id)
    assert closed.closed_at is not None


def test_close_ticket_unknown():
    svc = EmotionCareService()
    assert svc.close_ticket("ghost") is None


def test_list_tickets_filter_user():
    svc = EmotionCareService()
    svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    svc.trigger_care("u2", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    t1 = svc.list_tickets(user_id="u1")
    t2 = svc.list_tickets(user_id="u2")
    assert len(t1) == 1 and t1[0].user_id == "u1"
    assert len(t2) == 1 and t2[0].user_id == "u2"


def test_list_tickets_filter_level():
    svc = EmotionCareService()
    svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    svc.trigger_care("u1", risk_level="severe", primary_emotion="anxiety", trigger_text="x")
    heavy = svc.list_tickets(level=CARE_LEVEL_HEAVY)
    assert len(heavy) == 1


def test_dashboard_summary():
    svc = EmotionCareService()
    svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    s = svc.dashboard_summary()
    assert s["total_tickets"] >= 1
    assert s["resource_categories"] > 0


def test_care_action_to_dict():
    a = CareAction(action_id="x", user_id="u", level="light", action_type="warm_message")
    d = a.to_dict()
    assert d["action_id"] == "x"


def test_care_ticket_to_dict():
    t = CareTicket(id="x", user_id="u", level="light", risk_level="mild", primary_emotion="a", trigger_text="b")
    d = t.to_dict()
    assert d["id"] == "x"


def test_emotion_to_category_mapping():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="mild", primary_emotion="burnout", trigger_text="累")
    actions = svc.list_actions(ticket.id)
    res = next((a for a in actions if a.action_type == "send_resource"), None)
    assert res is not None
    assert res.payload["category"] == "burnout"


def test_warm_message_text_includes_emotion():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    actions = svc.list_actions(ticket.id)
    warm = next((a for a in actions if a.action_type == "warm_message"), None)
    assert warm is not None
    assert "焦虑" in warm.payload["text"] or "情绪" in warm.payload["text"]


def test_singleton():
    a = get_emotion_care_service()
    b = get_emotion_care_service()
    assert a is b


def test_reset_clears_tickets():
    svc = get_emotion_care_service()
    svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x")
    assert len(svc.list_tickets()) >= 1
    reset_emotion_care_service()
    svc2 = get_emotion_care_service()
    assert len(svc2.list_tickets()) == 0


def test_resource_categories_count():
    """wellness_resources.json 应该至少 100+ 资源."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "wellness_resources.json"
    data = json.loads(path.read_text())
    assert data["summary"]["total_resources"] >= 100


def test_multiple_tickets_for_same_user():
    svc = EmotionCareService()
    svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text="x1")
    svc.trigger_care("u1", risk_level="moderate", primary_emotion="stress", trigger_text="x2")
    assert len(svc.list_tickets(user_id="u1")) == 2


def test_ticket_trigger_text_truncated():
    svc = EmotionCareService()
    long_text = "x" * 1000
    ticket = svc.trigger_care("u1", risk_level="mild", primary_emotion="anxiety", trigger_text=long_text)
    assert len(ticket.trigger_text) <= 500


def test_hr_callback_action_payload():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="moderate", primary_emotion="anxiety", trigger_text="x", intensity=0.6)
    actions = svc.list_actions(ticket.id)
    cb = next((a for a in actions if a.action_type == "schedule_hr_callback"), None)
    assert cb is not None
    assert cb.payload["ticket_id"] == ticket.id


def test_crisis_resource_includes_hotline():
    svc = EmotionCareService()
    ticket = svc.trigger_care("u1", risk_level="severe", primary_emotion="anxiety", trigger_text="x", intensity=0.95)
    actions = svc.list_actions(ticket.id)
    cr = next((a for a in actions if a.action_type == "send_crisis_resource"), None)
    assert cr is not None
    assert "hotline" in cr.payload