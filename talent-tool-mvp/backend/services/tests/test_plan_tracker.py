"""plan_tracker 服务测试 (T607)."""
from __future__ import annotations

import pytest

from backend.services.plan_tracker import (
    CareerPlan,
    PlanTrackerService,
    get_plan_tracker,
    reset_plan_tracker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_plan_tracker()
    yield
    reset_plan_tracker()


# ---------------------------------------------------------------------------
# 创建 / 获取
# ---------------------------------------------------------------------------
def test_create_plan_assigns_id_and_user():
    svc = PlanTrackerService()
    plan = svc.create_plan("user-1")
    assert plan.id
    assert plan.user_id == "user-1"
    assert plan.created_at


def test_create_plan_with_data():
    svc = PlanTrackerService()
    data = {
        "short_term": [{"title": "投递简历", "priority": "high"}],
        "mid_term": [{"title": "完成项目", "duration": "3 个月"}],
        "skill_gaps": ["FastAPI", "Kubernetes"],
    }
    plan = svc.create_plan("user-2", plan_data=data)
    assert len(plan.short_term) == 1
    assert plan.short_term[0].title == "投递简历"
    assert plan.short_term[0].priority == "high"
    assert plan.skill_gaps == ["FastAPI", "Kubernetes"]


def test_get_plan_by_user():
    svc = PlanTrackerService()
    p = svc.create_plan("user-3")
    assert svc.get_plan("user-3") is p


def test_get_plan_for_unknown_user_returns_none():
    svc = PlanTrackerService()
    assert svc.get_plan("nope") is None


# ---------------------------------------------------------------------------
# 打卡
# ---------------------------------------------------------------------------
def test_checkin_increments_progress():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "学 Rust"}]})
    ck = svc.checkin("u1", "学 Rust", progress_delta=0.25)
    plan = svc.get_plan("u1")
    assert plan.short_term[0].progress == 0.25
    assert ck.progress_delta == 0.25


def test_checkin_progress_caps_at_one():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "学 Rust"}]})
    svc.checkin("u1", "学 Rust", progress_delta=0.9)
    svc.checkin("u1", "学 Rust", progress_delta=0.5)
    plan = svc.get_plan("u1")
    assert plan.short_term[0].progress == 1.0
    assert plan.short_term[0].completed is True


def test_checkin_unknown_item_raises():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a"}]})
    with pytest.raises(ValueError):
        svc.checkin("u1", "不存在的项")


def test_checkin_no_plan_raises():
    svc = PlanTrackerService()
    with pytest.raises(ValueError):
        svc.checkin("u-unknown", "x")


def test_checkin_records_history():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a"}]})
    svc.checkin("u1", "a", progress_delta=0.1, note="完成 module 1")
    history = svc.list_checkins("u1")
    assert len(history) == 1
    assert history[0].note == "完成 module 1"


# ---------------------------------------------------------------------------
# 调整
# ---------------------------------------------------------------------------
def test_adjust_delay_extends_duration():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a", "duration": "1 周"}]})
    svc.adjust("u1", "delay", "a", delta_days=7)
    plan = svc.get_plan("u1")
    assert "+7d" in plan.short_term[0].duration


def test_adjust_accelerate_sets_high_priority():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a", "priority": "medium"}]})
    svc.adjust("u1", "accelerate", "a", delta_days=5)
    plan = svc.get_plan("u1")
    assert plan.short_term[0].priority == "high"


def test_adjust_remove_deletes_item():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a"}, {"title": "b"}]})
    svc.adjust("u1", "remove", "a")
    plan = svc.get_plan("u1")
    titles = [i.title for i in plan.short_term]
    assert "a" not in titles
    assert "b" in titles


def test_adjust_unknown_action_raises():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a"}]})
    with pytest.raises(ValueError):
        svc.adjust("u1", "fly-to-moon", "a")


def test_adjust_records_history():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={"short_term": [{"title": "a"}]})
    svc.adjust("u1", "delay", "a", delta_days=3)
    history = svc.list_adjustments("u1")
    assert len(history) == 1
    assert history[0].action == "delay"
    assert history[0].delta_days == 3


# ---------------------------------------------------------------------------
# 进度
# ---------------------------------------------------------------------------
def test_progress_for_no_plan_returns_empty():
    svc = PlanTrackerService()
    p = svc.progress("nobody")
    assert p["plan_id"] is None
    assert p["overall_progress"] == 0.0
    assert p["items"] == []


def test_progress_aggregates_items():
    svc = PlanTrackerService()
    svc.create_plan("u1", plan_data={
        "short_term": [{"title": "a"}, {"title": "b"}],
        "milestones": [{"title": "M1", "target_date": "2099-12-31T00:00:00Z"}],
    })
    svc.checkin("u1", "a", progress_delta=0.5)
    p = svc.progress("u1")
    assert p["plan_id"]
    assert len(p["items"]) == 2
    # a=0.5, b=0.0 → 平均 0.25
    assert p["overall_progress"] == pytest.approx(0.25, abs=1e-6)
    assert any(m["title"] == "M1" for m in p["upcoming_milestones"])


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
def test_singleton_returns_same_instance():
    a = get_plan_tracker()
    b = get_plan_tracker()
    assert a is b