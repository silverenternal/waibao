"""规则测试器 (T804).

POST /api/rules/{id}/test: 用历史数据回放规则,
返回: { matched: bool, condition_trace: [...], action_results: [...] }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .dsl import Condition, Rule
from .evaluator import Context, RuleEvaluator

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuleTestResult:
    rule_id: str
    matched: bool
    condition_trace: list[dict[str, Any]]
    actions_executed: list[dict[str, Any]]
    duration_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "matched": self.matched,
            "condition_trace": self.condition_trace,
            "actions_executed": self.actions_executed,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


async def replay_rule(
    evaluator: RuleEvaluator,
    rule: Rule,
    context: dict[str, Any],
    *,
    dry_run: bool = True,
) -> RuleTestResult:
    """回放规则.

    Args:
        evaluator: 规则评估器.
        rule:       目标规则.
        context:    测试用 context.
        dry_run:    True 时 action handler 仍被调用 (mock 副作用). UI 测试场景.
    """
    import time as _time

    ctx = Context(context)
    ctx.set("rule_id", rule.id)
    ctx.set("rule_name", rule.name)

    trace: list[dict[str, Any]] = []
    matched = False

    if rule.condition is None:
        matched = True
        trace.append({"op": "NO_CONDITION", "result": True})
    else:
        try:
            if isinstance(rule.condition, Condition):
                matched = evaluator._eval_condition(rule.condition, ctx)  # noqa: SLF001
                trace.append(
                    {
                        "op": rule.condition.op.value,
                        "matched": matched,
                        "summary": _describe_condition(rule.condition),
                    }
                )
            else:
                matched = evaluator._eval_group(rule.condition, ctx)  # noqa: SLF001
                trace.append(
                    {
                        "op": rule.condition.op.value,
                        "matched": matched,
                        "summary": _describe_condition(rule.condition),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("tester.eval_failed rule=%s", rule.id)
            return RuleTestRecord_or_error(rule, str(exc))  # type: ignore[arg-type]

    started = _time.monotonic()
    actions_out: list[dict[str, Any]] = []
    if matched:
        for a in rule.actions:
            handler = evaluator._handlers.get(a.type)  # noqa: SLF001
            if handler is None:
                actions_out.append({"type": a.type, "ok": False, "error": "no_handler"})
                continue
            try:
                res = await handler(a, ctx)
                actions_out.append(
                    {"type": a.type, "ok": True, "result": res, "dry_run": dry_run}
                )
            except Exception as exc:  # noqa: BLE001
                actions_out.append(
                    {"type": a.type, "ok": False, "error": str(exc)}
                )
    duration = int((_time.monotonic() - started) * 1000)
    return RuleTestResult(
        rule_id=rule.id,
        matched=matched,
        condition_trace=trace,
        actions_executed=actions_out,
        duration_ms=duration,
    )


def RuleTestRecord_or_error(rule: Rule, err: str) -> RuleTestResult:  # noqa: N802
    return RuleTestResult(
        rule_id=rule.id,
        matched=False,
        condition_trace=[],
        actions_executed=[],
        duration_ms=0,
        error=err,
    )


def _describe_condition(node: Any) -> str:
    """人类可读描述."""
    from .dsl import Condition, ConditionGroup

    if isinstance(node, Condition):
        return f"{node.field} {node.op.value} {node.value!r}"
    if isinstance(node, ConditionGroup):
        inner = ", ".join(_describe_condition(c) for c in node.children)
        return f"({node.op.value} [{inner}])"
    return repr(node)
