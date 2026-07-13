"""T3707 - silence activator tests."""
import pytest
from datetime import datetime, timedelta
from services.silence_activator import (
    detect_silence, plan_schedule, plan_activation,
    RoomState, DEFAULT_SCHEDULE, MORNING_HOUR, AFTERNOON_HOUR,
)


class TestDetectSilence:
    def test_no_rooms(self):
        assert detect_silence([]) == []

    def test_recent_message(self):
        now = datetime.utcnow()
        r = RoomState(room_id="r1", last_message_at=now, participants=["u1"])
        assert detect_silence([r], now=now) == []

    def test_old_message(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=25)
        r = RoomState(room_id="r1", last_message_at=old, participants=["u1"])
        nudges = detect_silence([r], now=now)
        assert len(nudges) == 1
        assert nudges[0].severity == "warn"

    def test_very_old_message_urgent(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=72)
        r = RoomState(room_id="r1", last_message_at=old, participants=["u1"])
        nudges = detect_silence([r], now=now, silence_hours=24)
        assert nudges[0].severity == "urgent"

    def test_no_last_message(self):
        r = RoomState(room_id="r1", last_message_at=None)
        assert detect_silence([r]) == []

    def test_target_admin(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=30)
        r = RoomState(room_id="r1", last_message_at=old, admin_id="admin-x")
        nudges = detect_silence([r], now=now)
        assert nudges[0].target_user == "admin-x"

    def test_target_first_participant(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=30)
        r = RoomState(room_id="r1", last_message_at=old, participants=["p1", "p2"])
        nudges = detect_silence([r], now=now)
        assert nudges[0].target_user == "p1"

    def test_suggested_message_contains_room(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=30)
        r = RoomState(room_id="R-100", last_message_at=old, participants=["u"])
        nudges = detect_silence([r], now=now)
        assert "R-100" in nudges[0].suggested_message


class TestSchedule:
    def test_default_schedule_count(self):
        slots = plan_schedule()
        assert len(slots) == len(DEFAULT_SCHEDULE)

    def test_morning_slot(self):
        slots = plan_schedule()
        morning = [s for s in slots if s["hour"] == MORNING_HOUR]
        assert any(s["audience"] == "all" for s in morning)

    def test_afternoon_slot(self):
        slots = plan_schedule()
        afternoon = [s for s in slots if s["hour"] == AFTERNOON_HOUR]
        assert afternoon

    def test_custom_schedule(self):
        from services.silence_activator import ScheduleSlot
        custom = [ScheduleSlot(8, "hr", "x"), ScheduleSlot(20, "all", "y")]
        slots = plan_schedule(override=custom)
        assert len(slots) == 2

    def test_schedule_has_iso(self):
        slots = plan_schedule()
        assert all("scheduled_at" in s for s in slots)


class TestActivation:
    def test_no_nudges(self):
        r = RoomState(room_id="r1", participants=["u1"])
        actions = plan_activation(r, [])
        assert len(actions) == 1
        assert actions[0].action_type == "auto_summary"

    def test_with_nudge(self):
        now = datetime.utcnow()
        old = now - timedelta(hours=30)
        r = RoomState(room_id="r1", last_message_at=old, participants=["u1"], admin_id="a1")
        from services.silence_activator import detect_silence
        nudges = detect_silence([r], now=now)
        actions = plan_activation(r, nudges)
        # 30h > 24h default → produce nudge (warn OR urgent)
        assert len(actions) >= 1
        assert any(a.action_type in {"nudge_admin", "split_topic"} for a in actions)

    def test_skip_other_rooms(self):
        r = RoomState(room_id="r1", participants=["u1"])
        from services.silence_activator import Nudge
        other = Nudge("other", "x", "warn", "y", "u")
        actions = plan_activation(r, [other])
        assert all(a.room_id == "r1" for a in actions)
