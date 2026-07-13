"""v8.1 T3606 — Plan Tracker v3 tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.jobseeker.plan_tracker import (
    CareerPlan,
    Checkin,
    Milestone,
    PlanItem,
    PlanTrackerService,
    adjust_suggestions,
    daily_checkin,
    gantt_data,
    get_plan_tracker,
    link_action_item_to_plan,
    reset_plan_tracker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_plan_tracker()
    yield
    reset_plan_tracker()


def _make_plan(svc=None, *, user="u1", items=None):
    svc = svc or get_plan_tracker()
    items = items or [
        {"title": "learn rust", "duration": "30d", "priority": "high"},
        {"title": "write blog", "duration": "7d", "priority": "medium"},
    ]
    plan = svc.create_plan(user, plan_data={
        "short_term": items,
        "milestones": [
            {"title": "ms1", "target_date": "2026-12-31"},
        ],
    })
    return svc, plan


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------
def test_create_plan():
    svc, plan = _make_plan()
    assert plan.user_id == "u1"
    assert len(plan.short_term) == 2
    assert len(plan.milestones) == 1


def test_get_plan():
    svc, plan = _make_plan()
    fetched = svc.get_plan("u1")
    assert fetched is not None
    assert fetched.id == plan.id


def test_get_plan_unknown_user():
    svc = get_plan_tracker()
    assert svc.get_plan("ghost") is None


def test_overall_progress_zero_initially():
    svc, plan = _make_plan()
    assert plan.overall_progress == 0.0


def test_overall_progress_after_checkin():
    svc, plan = _make_plan()
    svc.checkin("u1", "learn rust", progress_delta=0.5)
    assert plan.overall_progress > 0


def test_checkin_completes_at_99_percent():
    svc, plan = _make_plan()
    svc.checkin("u1", "learn rust", progress_delta=0.99)
    item = next(i for i in plan.all_items if i.title == "learn rust")
    assert item.completed is True


def test_checkin_progress_clamped_to_1():
    svc, plan = _make_plan()
    svc.checkin("u1", "learn rust", progress_delta=0.99)
    svc.checkin("u1", "learn rust", progress_delta=0.99)
    item = next(i for i in plan.all_items if i.title == "learn rust")
    assert item.progress <= 1.0


def test_checkin_unknown_user_raises():
    svc = get_plan_tracker()
    with pytest.raises(ValueError):
        svc.checkin("ghost", "x", progress_delta=0.1)


def test_checkin_unknown_item_raises():
    svc, _ = _make_plan()
    with pytest.raises(ValueError):
        svc.checkin("u1", "no_such_item", progress_delta=0.1)


def test_list_checkins():
    svc, _ = _make_plan()
    svc.checkin("u1", "learn rust", progress_delta=0.1)
    svc.checkin("u1", "write blog", progress_delta=0.1)
    chks = svc.list_checkins("u1")
    assert len(chks) >= 2


def test_list_adjustments():
    svc, _ = _make_plan()
    svc.adjust("u1", "delay", "learn rust", delta_days=7)
    adjs = svc.list_adjustments("u1")
    assert len(adjs) == 1


def test_progress_returns_dict():
    svc, _ = _make_plan()
    p = svc.progress("u1")
    assert "overall_progress" in p
    assert "items" in p


def test_progress_no_plan():
    svc = PlanTrackerService()
    p = svc.progress("ghost")
    assert p["plan_id"] is None
    assert p["overall_progress"] == 0.0


def test_progress_includes_stale_items():
    svc, _ = _make_plan()
    p = svc.progress("u1")
    assert "stale_items" in p


def test_progress_includes_upcoming_milestones():
    svc, _ = _make_plan()
    p = svc.progress("u1")
    assert "upcoming_milestones" in p


# ---------------------------------------------------------------------------
# Adjust actions
# ---------------------------------------------------------------------------
def test_adjust_accelerate():
    svc, _ = _make_plan()
    svc.adjust("u1", "accelerate", "learn rust", delta_days=5)
    item = next(i for i in get_plan_tracker().get_plan("u1").all_items if i.title == "learn rust")
    assert "accelerated" in item.duration


def test_adjust_delay():
    svc, _ = _make_plan()
    svc.adjust("u1", "delay", "learn rust", delta_days=5)
    item = next(i for i in get_plan_tracker().get_plan("u1").all_items if i.title == "learn rust")
    assert "delayed" in item.duration


def test_adjust_replace():
    svc, _ = _make_plan()
    svc.adjust("u1", "replace", "learn rust", detail="learn go")
    item = next(i for i in get_plan_tracker().get_plan("u1").all_items if i.title == "learn go")
    assert item is not None


def test_adjust_add():
    svc, _ = _make_plan()
    svc.adjust("u1", "add", "any", detail="learn something")
    plan = get_plan_tracker().get_plan("u1")
    titles = [i.title for i in plan.short_term]
    assert "learn something" in titles


def test_adjust_remove():
    svc, _ = _make_plan()
    svc.adjust("u1", "remove", "write blog")
    plan = get_plan_tracker().get_plan("u1")
    titles = [i.title for i in plan.all_items]
    assert "write blog" not in titles


def test_adjust_unknown_action_raises():
    svc, _ = _make_plan()
    with pytest.raises(ValueError):
        svc.adjust("u1", "bogus_action", "learn rust")


# ---------------------------------------------------------------------------
# v8.1 — adjust_suggestions
# ---------------------------------------------------------------------------
def test_adjust_suggestions_shrink_for_behind():
    svc, _ = _make_plan()
    item = svc.get_plan("u1").all_items[0]
    item.started_at = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    item.progress = 0.05
    sugg = adjust_suggestions("u1")
    assert any(s["kind"] == "shrink_scope" for s in sugg)


def test_adjust_suggestions_bonus_for_ahead():
    svc, _ = _make_plan()
    item = svc.get_plan("u1").all_items[0]
    item.progress = 0.85
    sugg = adjust_suggestions("u1")
    assert any(s["kind"] == "add_bonus" for s in sugg)


def test_adjust_suggestions_no_plan():
    sugg = adjust_suggestions("ghost")
    assert sugg == []


def test_adjust_suggestions_excludes_completed():
    svc, _ = _make_plan()
    item = svc.get_plan("u1").all_items[0]
    item.progress = 0.99
    item.completed = True
    sugg = adjust_suggestions("u1")
    assert not any(s["item"] == item.title for s in sugg)


# ---------------------------------------------------------------------------
# v8.1 — daily_checkin
# ---------------------------------------------------------------------------
def test_daily_checkin_returns_combined_dict():
    svc, _ = _make_plan()
    result = daily_checkin("u1", item_title="learn rust", note="test")
    assert "checkin" in result
    assert "progress" in result
    assert "suggestions" in result


def test_daily_checkin_increments_progress():
    svc, _ = _make_plan()
    before = svc.get_plan("u1").overall_progress
    daily_checkin("u1", item_title="learn rust")
    after = svc.get_plan("u1").overall_progress
    assert after > before


def test_daily_checkin_invalid_item_raises():
    svc, _ = _make_plan()
    with pytest.raises(ValueError):
        daily_checkin("u1", item_title="no_such_item")


# ---------------------------------------------------------------------------
# v8.1 — gantt_data
# ---------------------------------------------------------------------------
def test_gantt_data_returns_tasks():
    svc, _ = _make_plan()
    g = gantt_data("u1")
    assert "tasks" in g
    assert len(g["tasks"]) == 2
    assert all("title" in t for t in g["tasks"])


def test_gantt_data_includes_milestones():
    svc, _ = _make_plan()
    g = gantt_data("u1")
    assert "milestones" in g
    assert len(g["milestones"]) == 1


def test_gantt_data_no_plan():
    g = gantt_data("ghost")
    assert g["tasks"] == []
    assert g["milestones"] == []


def test_gantt_data_includes_buckets():
    svc, _ = _make_plan()
    g = gantt_data("u1")
    buckets = {t["bucket"] for t in g["tasks"]}
    assert "short" in buckets


# ---------------------------------------------------------------------------
# v8.1 — link_action_item_to_plan
# ---------------------------------------------------------------------------
def test_link_action_item_to_plan_no_item_returns_error():
    """action_item_id 不存在时返回 linked=False."""
    svc, _ = _make_plan()
    result = link_action_item_to_plan("u1", "ghost_action_id", "learn rust")
    assert result["linked"] is False


def test_link_action_item_to_plan_success():
    """先创建 action item, 再 link."""
    from services.jobseeker.journal_evaluator import (
        get_journal_evaluator,
        reset_journal_evaluator,
    )
    reset_journal_evaluator()
    ev = get_journal_evaluator().evaluate(
        "text",
        "backend",
        context={"user_id": "u1"},
        parsed={"score": 7, "action_items": [{"title": "do x"}]},
    )
    item_id = ev.action_items[0].id
    _make_plan()
    result = link_action_item_to_plan("u1", item_id, "learn rust")
    assert result["linked"] is True


# ---------------------------------------------------------------------------
# Singleton / basic
# ---------------------------------------------------------------------------
def test_singleton():
    a = get_plan_tracker()
    b = get_plan_tracker()
    assert a is b


def test_milestone_to_dict():
    m = Milestone(title="m", target_date="2026-12-31")
    d = m.to_dict()
    assert d["title"] == "m"
    assert d["completed"] is False


def test_plan_item_to_dict():
    pi = PlanItem(title="x", progress=0.5)
    d = pi.to_dict()
    assert d["title"] == "x"


def test_career_plan_to_dict():
    cp = CareerPlan(id="x", user_id="u")
    d = cp.to_dict()
    assert d["id"] == "x"


def test_checkin_to_dict():
    c = Checkin(plan_id="p", user_id="u", item_title="t", progress_delta=0.1)
    d = c.to_dict()
    assert d["progress_delta"] == 0.1


def test_progress_with_started_item():
    svc, _ = _make_plan()
    item = svc.get_plan("u1").all_items[0]
    item.started_at = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    item.progress = 0.05
    p = svc.progress("u1")
    # 进度 < 20% 且 started 14 天前 -> 进 stale_items
    assert item.title in p["stale_items"]


def test_milestone_progress_sync():
    svc, _ = _make_plan()
    plan = svc.get_plan("u1")
    plan.all_items[0].milestone_target = "2026-12-31"
    plan.all_items[0].progress = 0.5
    svc.checkin("u1", "learn rust", progress_delta=0.0)  # 触发 milestone 同步
    ms = next(m for m in plan.milestones if m.target_date == "2026-12-31")
    assert ms.progress >= 0.5