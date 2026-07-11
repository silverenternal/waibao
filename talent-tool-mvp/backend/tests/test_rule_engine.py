"""T804 - 规则引擎单元测试."""
from __future__ import annotations

import asyncio

import pytest

from services.rule_engine.dsl import (
    Action,
    ComparisonOp,
    Condition,
    ConditionGroup,
    LogicalOp,
    Rule,
    parse_rule,
)
from services.rule_engine.evaluator import (
    Context,
    RULE_TIMEOUT_SECONDS,
    RuleEvaluator,
    validate_condition_depth,
)
from services.rule_engine.tester import replay_rule


# ---------------------------------------------------------------------------
# 基础求值
# ---------------------------------------------------------------------------


def _atomic_le(rule: Rule, ctx: dict) -> bool:
    ev = RuleEvaluator(rules=[rule])

    async def _go():
        m = await ev.evaluate(rule.trigger, ctx)
        return bool(m)

    return asyncio.run(_go())


def test_simple_atomic_condition():
    rule = Rule.new(
        name="low_rate",
        trigger="HR_SERVICE_AUTORESOLVE_RATE_LOW",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=Condition(op=ComparisonOp.LT, field="rate", value=0.6),
    )
    assert _atomic_le(rule, {"rate": 0.5}) is True
    assert _atomic_le(rule, {"rate": 0.7}) is False


def test_and_group():
    rule = Rule.new(
        name="both",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=ConditionGroup(
            op=LogicalOp.AND,
            children=[
                Condition(op=ComparisonOp.LT, field="rate", value=0.6),
                Condition(op=ComparisonOp.GT, field="sample_size", value=10),
            ],
        ),
    )
    assert _atomic_le(rule, {"rate": 0.5, "sample_size": 50}) is True
    assert _atomic_le(rule, {"rate": 0.7, "sample_size": 50}) is False
    assert _atomic_le(rule, {"rate": 0.5, "sample_size": 5}) is False


def test_or_group():
    rule = Rule.new(
        name="either",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=ConditionGroup(
            op=LogicalOp.OR,
            children=[
                Condition(op=ComparisonOp.EQ, field="priority", value="P1"),
                Condition(op=ComparisonOp.LT, field="remaining_minutes", value=15),
            ],
        ),
    )
    assert _atomic_le(rule, {"priority": "P1", "remaining_minutes": 60}) is True
    assert _atomic_le(rule, {"priority": "P2", "remaining_minutes": 10}) is True
    assert _atomic_le(rule, {"priority": "P2", "remaining_minutes": 60}) is False


def test_not_group():
    rule = Rule.new(
        name="not",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=ConditionGroup(
            op=LogicalOp.NOT,
            children=[
                Condition(op=ComparisonOp.EQ, field="ok", value=True),
            ],
        ),
    )
    assert _atomic_le(rule, {"ok": False}) is True
    assert _atomic_le(rule, {"ok": True}) is False


def test_nested_3_levels():
    rule = Rule.new(
        name="nest",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=ConditionGroup(
            op=LogicalOp.AND,
            children=[
                Condition(op=ComparisonOp.EQ, field="a", value=1),
                ConditionGroup(
                    op=LogicalOp.OR,
                    children=[
                        Condition(op=ComparisonOp.EQ, field="b", value=2),
                        ConditionGroup(
                            op=LogicalOp.NOT,
                            children=[
                                Condition(op=ComparisonOp.EQ, field="c", value=3)
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )
    # a=1, b=2 -> True
    assert _atomic_le(rule, {"a": 1, "b": 2, "c": 3}) is True
    # a=1, b!=2, c=3 (NOT false) -> False
    assert _atomic_le(rule, {"a": 1, "b": 9, "c": 3}) is False
    # a=1, b!=2, c!=3 (NOT true) -> True
    assert _atomic_le(rule, {"a": 1, "b": 9, "c": 9}) is True


def test_depth_limit():
    """嵌套超过 3 层抛 ValueError."""
    deep = Condition(
        op=ComparisonOp.EQ, field="x", value=1
    )
    for _ in range(4):
        deep = ConditionGroup(op=LogicalOp.AND, children=[deep])
    with pytest.raises(ValueError):
        validate_condition_depth(deep)


def test_dot_path_field():
    rule = Rule.new(
        name="dp",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "x"})],
        condition=Condition(op=ComparisonOp.LT, field="data.rate", value=0.5),
    )
    assert _atomic_le(rule, {"data": {"rate": 0.3}}) is True
    assert _atomic_le(rule, {"data": {"rate": 0.6}}) is False


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_handler_called():
    called = []

    async def handler(action, ctx):
        called.append(action.type)

    rule = Rule.new(
        name="x",
        trigger="T",
        actions=[Action(type="custom", params={})],
    )
    ev = RuleEvaluator(rules=[rule], handlers={"custom": handler})
    m = await ev.evaluate("T", {})
    assert m and len(m) == 1
    await ev.execute(m[0], Context({}))
    assert called == ["custom"]


@pytest.mark.asyncio
async def test_action_failure_does_not_break_business():
    async def bad(action, ctx):
        raise RuntimeError("boom")

    async def good(action, ctx):
        pass

    rule = Rule.new(
        name="x",
        trigger="T",
        actions=[
            Action(type="bad", params={}),
            Action(type="good", params={}),
        ],
    )
    ev = RuleEvaluator(rules=[rule], handlers={"bad": bad, "good": good})
    m = await ev.evaluate("T", {})
    await ev.execute(m[0], Context({}))
    # 不抛 = 通过


@pytest.mark.asyncio
async def test_rule_timeout():
    """Action handler 超过 RULE_TIMEOUT_SECONDS 也会被截断."""

    async def slow(action, ctx):
        await asyncio.sleep(RULE_TIMEOUT_SECONDS + 0.5)

    rule = Rule.new(
        name="slow",
        trigger="T",
        actions=[Action(type="slow", params={})],
    )
    ev = RuleEvaluator(rules=[rule], handlers={"slow": slow})
    m = await ev.evaluate("T", {})
    # 显式短超时以加速测试
    started = asyncio.get_event_loop().time()
    await ev.execute(m[0], Context({}), timeout=0.2)
    elapsed = asyncio.get_event_loop().time() - started
    assert elapsed < 1.0  # 没等满


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooldown_skip():
    rule = Rule.new(
        name="c",
        trigger="T",
        actions=[Action(type="emit_event", params={})],
        cooldown_seconds=60,
    )
    ev = RuleEvaluator(rules=[rule])
    m1 = await ev.evaluate("T", {})
    # 第一次执行后,cooldown 才会设置
    if m1:
        await ev.execute(m1[0], Context({}))
    m2 = await ev.evaluate("T", {})
    assert m2 == []  # cooldown 内不重复


# ---------------------------------------------------------------------------
# Tester replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_returns_match_and_actions():
    rule = Rule.new(
        name="r",
        trigger="T",
        actions=[Action(type="emit_event", params={"event": "ping"})],
        condition=Condition(op=ComparisonOp.LT, field="rate", value=0.5),
    )
    ev = RuleEvaluator(rules=[rule])
    res = await replay_rule(ev, rule, {"rate": 0.4})
    assert res.matched is True
    assert res.actions_executed and len(res.actions_executed) == 1


@pytest.mark.asyncio
async def test_replay_no_match():
    rule = Rule.new(
        name="r",
        trigger="T",
        actions=[Action(type="emit_event", params={})],
        condition=Condition(op=ComparisonOp.GT, field="rate", value=0.9),
    )
    ev = RuleEvaluator()
    res = await replay_rule(ev, rule, {"rate": 0.1})
    assert res.matched is False
    assert res.actions_executed == []


# ---------------------------------------------------------------------------
# parse_rule
# ---------------------------------------------------------------------------


def test_parse_rule_roundtrip():
    payload = {
        "id": "r1",
        "name": "demo",
        "description": "x",
        "enabled": True,
        "trigger": "T",
        "condition": {
            "op": "AND",
            "children": [{"op": "<", "field": "rate", "value": 0.5}],
        },
        "actions": [{"type": "notify", "channel": "email"}],
        "cooldown_seconds": 60,
        "tags": ["a"],
    }
    r = parse_rule(payload)
    assert r.condition is not None
    assert r.actions[0].type == "notify"
    assert r.cooldown_seconds == 60
    # 回写
    out = r.to_dict()
    assert out["id"] == "r1"
    assert out["condition"]["op"] == "AND"


def test_parse_rule_atomic_condition():
    payload = {
        "id": "r1",
        "name": "demo",
        "enabled": True,
        "trigger": "T",
        "condition": {"op": "<", "field": "rate", "value": 0.5},
        "actions": [],
    }
    r = parse_rule(payload)
    assert isinstance(r.condition, Condition)
    assert r.condition.op == ComparisonOp.LT
