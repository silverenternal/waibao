"""v8.1 T3602 — Journal Evaluator tests."""
from __future__ import annotations

import pytest

from services.jobseeker.journal_evaluator import (
    ActionItem,
    Evaluation,
    IndustryRole,
    JournalEvaluatorService,
    ROLE_DISPLAY,
    ROLE_DIMENSIONS,
    build_prompt,
    get_journal_evaluator,
    reset_journal_evaluator,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_journal_evaluator()
    yield
    reset_journal_evaluator()


def test_evaluator_basic():
    svc = JournalEvaluatorService()
    ev = svc.evaluate("今天跟同事吵架了, 心情不好", "backend")
    assert ev.score > 0
    assert ev.role == "backend"
    assert "code_quality" in ev.dimension_scores


def test_evaluator_with_parsed():
    svc = JournalEvaluatorService()
    parsed = {
        "score": 8.5,
        "dimension_scores": {"code_quality": 9, "system_design": 8},
        "strengths": ["速度快"],
        "improvements": ["测试覆盖"],
        "risks": [],
        "action_items": [
            {"title": "补单元测试", "feasibility": 4},
            {"title": "Code Review", "feasibility": 5},
        ],
    }
    ev = svc.evaluate("content", "backend", parsed=parsed)
    assert ev.score == 8.5
    assert ev.dimension_scores["code_quality"] == 9
    assert len(ev.action_items) == 2


def test_evaluator_action_item_feasibility_clamped():
    svc = JournalEvaluatorService()
    parsed = {
        "score": 7,
        "action_items": [
            {"title": "x", "feasibility": 99},  # clamp to 5
            {"title": "y", "feasibility": -1},  # clamp to 1
        ],
    }
    ev = svc.evaluate("content", "backend", parsed=parsed)
    feas = [a.feasibility for a in ev.action_items]
    assert 1 <= min(feas)
    assert max(feas) <= 5


def test_evaluator_action_item_from_string():
    svc = JournalEvaluatorService()
    parsed = {
        "score": 7,
        "action_items": ["string item 1", "string item 2"],
    }
    ev = svc.evaluate("c", "backend", parsed=parsed)
    titles = [a.title for a in ev.action_items]
    assert "string item 1" in titles


def test_evaluator_unknown_role_uses_generic():
    svc = JournalEvaluatorService()
    ev = svc.evaluate("c", "unknown_role")
    # 仍然能产出评价
    assert ev.score > 0
    assert ev.role == "unknown_role"


def test_update_action_item_status():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    updated = svc.update_action_item(item.id, status="in_progress")
    assert updated.status == "in_progress"
    assert updated.completed_at is None


def test_update_action_item_done_sets_completed_at():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    updated = svc.update_action_item(item.id, status="done")
    assert updated.status == "done"
    assert updated.completed_at is not None


def test_update_action_item_invalid_status_raises():
    svc = JournalEvaluatorService()
    ev = svc.evaluate("c", "backend", parsed={"score": 7, "action_items": [{"title": "x"}]}, context={"user_id": "u1"})
    with pytest.raises(ValueError):
        svc.update_action_item(ev.action_items[0].id, status="bogus")


def test_update_action_item_unknown_id_raises():
    svc = JournalEvaluatorService()
    with pytest.raises(KeyError):
        svc.update_action_item("nonexistent_id")


def test_update_action_item_quality_score():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    updated = svc.update_action_item(item.id, quality_score=8.5)
    assert updated.quality_score == 8.5


def test_list_action_items_filter_status():
    svc = JournalEvaluatorService()
    svc.evaluate("c", "backend", parsed={"score": 7, "action_items": [{"title": "a"}]}, context={"user_id": "u1"})
    svc.evaluate("c", "backend", parsed={"score": 7, "action_items": [{"title": "b"}]}, context={"user_id": "u1"})
    items = svc.list_action_items("u1")
    assert len(items) == 2
    items_done = svc.list_action_items("u1", status="pending")
    assert len(items_done) == 2
    items_done = svc.list_action_items("u1", status="done")
    assert len(items_done) == 0


def test_rating_trend():
    svc = JournalEvaluatorService()
    for i in range(3):
        svc.evaluate(f"text {i}", "backend", parsed={"score": 5 + i})
    trend = svc.rating_trend("u1")
    assert isinstance(trend, list)


def test_link_to_plan():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    linked = svc.link_to_plan(item.id, "learn python")
    assert linked.plan_item_title == "learn python"


def test_all_industry_roles_have_dimensions():
    for role in IndustryRole:
        assert role.value in ROLE_DIMENSIONS
        cfg = ROLE_DIMENSIONS[role.value]
        assert "dimensions" in cfg
        assert "weight" in cfg
        # weights sum to 1
        total = sum(cfg["weight"].values())
        assert abs(total - 1.0) < 0.01


def test_role_display_for_all_roles():
    for role in IndustryRole:
        assert role.value in ROLE_DISPLAY


def test_build_prompt_for_all_roles():
    for role in IndustryRole:
        p = build_prompt(role.value, "今天写了个测试")
        assert "JSON" in p or "json" in p
        assert isinstance(p, str)


def test_build_prompt_for_unknown_role():
    p = build_prompt("unknown", "content")
    assert isinstance(p, str)


def test_due_items_no_due_date():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    due = svc.due_items(hours=24)
    assert due == []  # no due_date set


def test_due_items_with_due_date():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    svc.update_action_item(item.id, due_date=future)
    due = svc.due_items(hours=24)
    assert len(due) == 1
    assert due[0].id == item.id


def test_mark_reminder_sent():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    svc.mark_reminder_sent(item.id)
    assert item.reminder_sent is True


def test_action_item_to_dict():
    ai = ActionItem(id="x", user_id="u", title="t")
    d = ai.to_dict()
    assert d["id"] == "x"
    assert d["status"] == "pending"


def test_evaluation_to_dict():
    e = Evaluation(
        role="backend", score=8.0,
        dimension_scores={"code_quality": 8},
        strengths=["a"], improvements=["b"], risks=[],
        action_items=[],
    )
    d = e.to_dict()
    assert d["role"] == "backend"
    assert d["action_items"] == []


def test_evaluator_singleton():
    a = get_journal_evaluator()
    b = get_journal_evaluator()
    assert a is b


def test_evaluator_resets():
    a = get_journal_evaluator()
    a.evaluate("c", "backend")
    reset_journal_evaluator()
    b = get_journal_evaluator()
    assert a is not b


def test_evaluator_heuristic_long_text():
    """启发式 — 长文高分."""
    svc = JournalEvaluatorService()
    long_text = "今天做了很多事情。" * 50
    ev = svc.evaluate(long_text, "backend")
    assert ev.score >= 7


def test_evaluator_heuristic_short_text():
    svc = JournalEvaluatorService()
    ev = svc.evaluate("hi", "backend")
    assert ev.score < 7


def test_evaluator_action_item_user_id():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "alice"})
    assert ev.action_items[0].user_id == "alice"


def test_evaluator_action_item_role_set():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "operations", parsed=parsed)
    assert ev.action_items[0].role == "operations"


def test_evaluator_dimension_scores_per_role():
    svc = JournalEvaluatorService()
    ev = svc.evaluate("c", "finance")
    dims = ROLE_DIMENSIONS["finance"]["dimensions"]
    for d in dims:
        assert d in ev.dimension_scores


def test_update_action_item_due_date():
    svc = JournalEvaluatorService()
    parsed = {"score": 7, "action_items": [{"title": "x"}]}
    ev = svc.evaluate("c", "backend", parsed=parsed, context={"user_id": "u1"})
    item = ev.action_items[0]
    updated = svc.update_action_item(item.id, due_date="2026-12-31T23:59:59")
    assert updated.due_date == "2026-12-31T23:59:59"