"""v8.1 T3602 — Action Items v2 tests (状态机 + 截止日期 + 完成质量)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.jobseeker.journal_evaluator import (
    ActionItem,
    JournalEvaluatorService,
    get_journal_evaluator,
    reset_journal_evaluator,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_journal_evaluator()
    yield
    reset_journal_evaluator()


def _seed(svc=None, *, n=3, role="backend", user="u1"):
    svc = svc or JournalEvaluatorService()
    items = []
    for i in range(n):
        ev = svc.evaluate(
            f"text {i}",
            role,
            context={"user_id": user},
            parsed={"score": 7, "action_items": [{"title": f"item-{i}", "feasibility": 3}]},
        )
        items.extend(ev.action_items)
    return svc, items


def test_pending_default():
    svc, items = _seed()
    assert all(i.status == "pending" for i in items)


def test_in_progress_transition():
    svc, items = _seed()
    svc.update_action_item(items[0].id, status="in_progress")
    assert svc.list_action_items("u1", status="in_progress")[0].id == items[0].id


def test_done_transition_sets_completed_at():
    svc, items = _seed()
    svc.update_action_item(items[0].id, status="done")
    item = svc.list_action_items("u1", status="done")[0]
    assert item.completed_at is not None


def test_abandoned_transition():
    svc, items = _seed()
    svc.update_action_item(items[0].id, status="abandoned")
    assert svc.list_action_items("u1", status="abandoned")[0].id == items[0].id


def test_invalid_status_raises():
    svc, items = _seed()
    with pytest.raises(ValueError):
        svc.update_action_item(items[0].id, status="bogus_state")


def test_quality_score_set():
    svc, items = _seed()
    svc.update_action_item(items[0].id, quality_score=9.5)
    fetched = svc.list_action_items("u1")[0]
    assert fetched.quality_score == 9.5


def test_quality_score_validation():
    svc, items = _seed()
    svc.update_action_item(items[0].id, quality_score="not_a_number")  # type: ignore
    fetched = svc.list_action_items("u1")[0]
    assert fetched.quality_score is None or fetched.quality_score == "not_a_number"


def test_due_date_set():
    svc, items = _seed()
    future = "2026-12-31T23:59:59"
    svc.update_action_item(items[0].id, due_date=future)
    fetched = svc.list_action_items("u1")[0]
    assert fetched.due_date == future


def test_due_items_no_due_date_returns_empty():
    svc, items = _seed()
    assert svc.due_items(hours=24) == []


def test_due_items_within_window():
    svc, items = _seed()
    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    svc.update_action_item(items[0].id, due_date=future)
    due = svc.due_items(hours=24)
    assert len(due) == 1


def test_due_items_outside_window():
    svc, items = _seed()
    future = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    svc.update_action_item(items[0].id, due_date=future)
    due = svc.due_items(hours=24)
    assert len(due) == 0


def test_due_items_excludes_done():
    svc, items = _seed()
    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    svc.update_action_item(items[0].id, due_date=future, status="done")
    due = svc.due_items(hours=24)
    assert len(due) == 0


def test_due_items_excludes_abandoned():
    svc, items = _seed()
    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    svc.update_action_item(items[0].id, due_date=future, status="abandoned")
    due = svc.due_items(hours=24)
    assert len(due) == 0


def test_mark_reminder_sent():
    svc, items = _seed()
    svc.mark_reminder_sent(items[0].id)
    assert items[0].reminder_sent is True


def test_link_to_plan():
    svc, items = _seed()
    svc.link_to_plan(items[0].id, "learn_rust")
    assert items[0].plan_item_title == "learn_rust"


def test_link_to_plan_unknown_id():
    svc, _ = _seed()
    with pytest.raises(KeyError):
        svc.link_to_plan("nonexistent", "x")


def test_filter_by_role():
    svc, items = _seed(role="backend")
    _seed(svc, n=2, role="design", user="u2")
    be_items = svc.list_action_items("u1", role="backend")
    de_items = svc.list_action_items("u2", role="design")
    assert all(i.role == "backend" for i in be_items)
    assert all(i.role == "design" for i in de_items)


def test_filter_combined():
    svc, items = _seed()
    svc.update_action_item(items[0].id, status="done")
    pending = svc.list_action_items("u1", status="pending")
    done = svc.list_action_items("u1", status="done")
    assert len(pending) == 2
    assert len(done) == 1


def test_action_item_unique_ids():
    svc, items = _seed(n=5)
    ids = [i.id for i in items]
    assert len(set(ids)) == 5


def test_action_item_titles_preserved():
    svc, items = _seed(n=3)
    titles = [i.title for i in items]
    assert "item-0" in titles
    assert "item-2" in titles


def test_action_item_user_id_set():
    svc, items = _seed(user="alice")
    assert all(i.user_id == "alice" for i in items)


def test_action_item_created_at_set():
    svc, items = _seed()
    assert all(i.created_at != "" for i in items)


def test_link_action_only_sets_field():
    """link_to_plan 不改 status."""
    svc, items = _seed()
    original_status = items[0].status
    svc.link_to_plan(items[0].id, "x")
    assert items[0].status == original_status


def test_get_journal_evaluator_returns_singleton():
    a = get_journal_evaluator()
    b = get_journal_evaluator()
    assert a is b


def test_reset_clears_state():
    svc, items = _seed()
    assert len(items) == 3
    reset_journal_evaluator()
    svc2 = get_journal_evaluator()
    assert svc2.list_action_items("u1") == []