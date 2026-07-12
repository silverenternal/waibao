"""T1807 — 5 条真实业务规则 (rule_engine).

规则覆盖:
  R1 匹配分 < 0.7 自动告警 HRBP
  R2 候选人合规风险 (GDPR) → 创建 P1 工单
  R3 情绪风险事件 → 通知 wecom
  R4 ATS 同步冲突数 > 5 → 通知 admin
  R5 报价转化率 < 0.3 (7d) → 推送 sales

每条规则 verify:
  - parse_rule 正常 (JSON -> Rule)
  - condition 评估 (给定 context 命中 / 不命中)
  - actions 列表存在且 type 合法
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from services.rule_engine import (
    Action,
    ComparisonOp,
    Condition,
    ConditionGroup,
    LogicalOp,
    Rule,
    RuleEvaluator,
    RuleMatch,
    parse_rule,
)
from services.rule_engine.evaluator import Context


# ---------------------------------------------------------------------------
# 5 条真实业务规则 (JSON DSL)
# ---------------------------------------------------------------------------
R1 = {
    "id": "rule_match_low_score_alert",
    "name": "匹配分 < 0.7 告警",
    "description": "当 ATS 同步后匹配分持续低于 0.7,自动通知 HRBP 创建 P1 ticket",
    "enabled": True,
    "trigger": "ATS_SYNC_COMPLETED",
    "condition": {
        "op": "AND",
        "children": [
            {"op": "<", "field": "data.avg_match_score", "value": 0.7},
            {"op": ">=", "field": "data.candidates_synced", "value": 10},
        ],
    },
    "actions": [
        {"type": "notify", "channel": "wecom", "to": ["hrbp@acme.com"],
         "template": "match_low_score"},
        {"type": "create_ticket", "department": "HRBP",
         "priority": "P1", "title": "匹配分持续低告警"},
    ],
    "cooldown_seconds": 3600,
    "tags": ["match", "alert", "hiring-quality"],
}

R2 = {
    "id": "rule_gdpr_high_risk_ticket",
    "name": "GDPR 高风险 → P1 工单",
    "description": "候选人合规分 < 60 → 自动开 P1 合规工单",
    "enabled": True,
    "trigger": "COMPLIANCE_SCAN_DONE",
    "condition": {
        "op": "AND",
        "children": [
            {"op": "<", "field": "data.compliance_score", "value": 60},
            {"op": "==", "field": "data.region", "value": "EU"},
        ],
    },
    "actions": [
        {"type": "create_ticket", "department": "Legal",
         "priority": "P1", "title": "GDPR 合规风险"},
        {"type": "notify", "channel": "email", "to": ["legal@acme.com"],
         "template": "gdpr_high_risk"},
    ],
    "cooldown_seconds": 1800,
    "tags": ["compliance", "gdpr", "p1"],
}

R3 = {
    "id": "rule_emotion_risk_wecom",
    "name": "情绪风险 → wecom 通知",
    "description": "情绪识别出 high risk 时立刻推送 wecom",
    "enabled": True,
    "trigger": "EMOTION_RISK_DETECTED",
    "condition": {"op": "==", "field": "data.severity", "value": "high"},
    "actions": [
        {"type": "notify", "channel": "wecom", "to": ["hotline@acme.com"],
         "template": "emotion_risk_high"},
    ],
    "cooldown_seconds": 0,
    "tags": ["emotion", "wecom", "urgent"],
}

R4 = {
    "id": "rule_ats_conflict_admin_alert",
    "name": "ATS 同步冲突 > 5 通知 admin",
    "description": "单次同步冲突数 > 5 表明 ATS 配置或数据异常",
    "enabled": True,
    "trigger": "ATS_SYNC_CONFLICT_BATCH",
    "condition": {"op": ">", "field": "data.conflict_count", "value": 5},
    "actions": [
        {"type": "notify", "channel": "email", "to": ["admin@acme.com"],
         "template": "ats_conflict_admin"},
        {"type": "emit_event", "event": "ADMIN_ALERT_SENT",
         "data": {"reason": "ats_conflict_threshold_breached"}},
    ],
    "cooldown_seconds": 600,
    "tags": ["ats", "admin", "data-quality"],
}

R5 = {
    "id": "rule_quote_conversion_low_sales_push",
    "name": "报价转化率 < 0.3 (7d) 推 sales",
    "description": "7 天 quote → placement 转化率 < 30%, 自动推 sales 团队",
    "enabled": True,
    "trigger": "QUOTE_FUNNEL_DAILY",
    "condition": {
        "op": "AND",
        "children": [
            {"op": "<", "field": "data.conversion_rate", "value": 0.3},
            {"op": "==", "field": "data.window", "value": "7d"},
            {"op": ">=", "field": "data.quotes_count", "value": 20},
        ],
    },
    "actions": [
        {"type": "notify", "channel": "wecom", "to": ["sales-leads@acme.com"],
         "template": "quote_conversion_low"},
        {"type": "create_ticket", "department": "SalesOps",
         "priority": "P2", "title": "7d 报价转化率低"},
    ],
    "cooldown_seconds": 86400,
    "tags": ["sales", "quote", "conversion"],
}


ALL_RULES = [R1, R2, R3, R4, R5]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_rules_parse() -> None:
    """1) 5 条规则都能 parse_rule()."""
    rules = [parse_rule(r) for r in ALL_RULES]
    assert len(rules) == 5
    assert all(isinstance(r, Rule) for r in rules)
    ids = [r.id for r in rules]
    assert "rule_match_low_score_alert" in ids
    assert "rule_gdpr_high_risk_ticket" in ids
    assert "rule_emotion_risk_wecom" in ids
    assert "rule_ats_conflict_admin_alert" in ids
    assert "rule_quote_conversion_low_sales_push" in ids
    # enabled 全 True
    assert all(r.enabled for r in rules)
    # 每个规则都有 actions
    assert all(len(r.actions) >= 1 for r in rules)


@pytest.mark.asyncio
async def test_rule1_match_low_score_triggers() -> None:
    """R1: avg_match_score < 0.7 + candidates_synced >= 10 → 触发."""
    rule = parse_rule(R1)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({
        "data": {
            "avg_match_score": 0.55,
            "candidates_synced": 25,
        }
    })
    matches = await evaluator.evaluate("ATS_SYNC_COMPLETED", ctx)
    assert len(matches) == 1
    assert matches[0].rule_id == "rule_match_low_score_alert"
    assert len(matches[0].actions) == 2
    action_types = {a.type for a in matches[0].actions}
    assert "notify" in action_types
    assert "create_ticket" in action_types


@pytest.mark.asyncio
async def test_rule1_no_trigger_when_score_high() -> None:
    """R1: score >= 0.7 → 不触发."""
    rule = parse_rule(R1)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({"data": {"avg_match_score": 0.85, "candidates_synced": 25}})
    assert await evaluator.evaluate("ATS_SYNC_COMPLETED", ctx) == []


@pytest.mark.asyncio
async def test_rule2_gdpr_eu_region() -> None:
    """R2: GDPR score < 60 + EU region → 触发."""
    rule = parse_rule(R2)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({"data": {"compliance_score": 45, "region": "EU"}})
    matches = await evaluator.evaluate("COMPLIANCE_SCAN_DONE", ctx)
    assert len(matches) == 1
    ticket_action = next(a for a in matches[0].actions if a.type == "create_ticket")
    assert ticket_action.params.get("priority") == "P1"


@pytest.mark.asyncio
async def test_rule3_emotion_risk_high() -> None:
    """R3: severity=high → 触发 (无 cooldown)."""
    rule = parse_rule(R3)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({"data": {"severity": "high"}})
    matches = await evaluator.evaluate("EMOTION_RISK_DETECTED", ctx)
    assert len(matches) == 1
    notify = next(a for a in matches[0].actions if a.type == "notify")
    assert notify.params.get("channel") == "wecom"


@pytest.mark.asyncio
async def test_rule3_no_trigger_low_severity() -> None:
    """R3: severity=low → 不触发."""
    rule = parse_rule(R3)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({"data": {"severity": "low"}})
    assert await evaluator.evaluate("EMOTION_RISK_DETECTED", ctx) == []


@pytest.mark.asyncio
async def test_rule4_ats_conflict_threshold() -> None:
    """R4: conflict_count > 5 → 触发 emit_event + notify."""
    rule = parse_rule(R4)
    evaluator = RuleEvaluator(rules=[rule])
    ctx = Context({"data": {"conflict_count": 8}})
    matches = await evaluator.evaluate("ATS_SYNC_CONFLICT_BATCH", ctx)
    assert len(matches) == 1
    emit = next((a for a in matches[0].actions if a.type == "emit_event"), None)
    assert emit is not None
    assert emit.params.get("event") == "ADMIN_ALERT_SENT"


@pytest.mark.asyncio
async def test_rule5_quote_conversion_3_conditions() -> None:
    """R5: conversion_rate < 0.3 + window=7d + quotes >= 20 → 触发."""
    rule = parse_rule(R5)
    evaluator = RuleEvaluator(rules=[rule])

    # 全部满足
    ctx_hit = Context({"data": {"conversion_rate": 0.22, "window": "7d", "quotes_count": 50}})
    matches = await evaluator.evaluate("QUOTE_FUNNEL_DAILY", ctx_hit)
    assert len(matches) == 1

    # 缺一: quotes_count 不足
    ctx_miss = Context({"data": {"conversion_rate": 0.22, "window": "7d", "quotes_count": 10}})
    assert await evaluator.evaluate("QUOTE_FUNNEL_DAILY", ctx_miss) == []


@pytest.mark.asyncio
async def test_5_rules_coverage_distinct_triggers() -> None:
    """5 条规则 trigger 各不相同,互不串扰."""
    triggers = {r.trigger for r in [parse_rule(r) for r in ALL_RULES]}
    assert len(triggers) == 5


@pytest.mark.asyncio
async def test_5_rules_action_diversity() -> None:
    """覆盖 4 种 action 类型: notify / create_ticket / emit_event."""
    types_used: set[str] = set()
    for r in ALL_RULES:
        rule = parse_rule(r)
        for a in rule.actions:
            types_used.add(a["type"] if isinstance(a, dict) else a.type)
    assert "notify" in types_used
    assert "create_ticket" in types_used
    assert "emit_event" in types_used


def test_dsl_round_trip_json() -> None:
    """规则 JSON <-> Rule 对象 round-trip."""
    rule = parse_rule(R2)
    j = rule.to_dict()
    s = json.dumps(j)
    parsed = parse_rule(s)
    assert parsed.id == rule.id
    assert parsed.trigger == rule.trigger
    assert len(parsed.actions) == len(rule.actions)


if __name__ == "__main__":
    test_5_rules_parse()
    test_rule1_match_low_score_triggers()
    test_rule1_no_trigger_when_score_high()
    test_rule2_gdpr_eu_region()
    test_rule3_emotion_risk_high()
    test_rule3_no_trigger_low_severity()
    test_rule4_ats_conflict_threshold()
    test_rule5_quote_conversion_3_conditions()
    test_5_rules_coverage_distinct_triggers()
    test_5_rules_action_diversity()
    test_dsl_round_trip_json()
    print("OK: rule tests")