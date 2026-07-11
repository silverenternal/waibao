"""规则引擎 (T804)."""
from __future__ import annotations

from .builtins import BUILTIN_TRIGGERS, BuiltinTrigger, get_builtin_trigger
from .dsl import (
    Action,
    ComparisonOp,
    Condition,
    ConditionGroup,
    LogicalOp,
    Rule,
    parse_rule,
)
from .evaluator import RuleEvaluator, RuleMatch

__all__ = [
    "Action",
    "BUILTIN_TRIGGERS",
    "BuiltinTrigger",
    "ComparisonOp",
    "Condition",
    "ConditionGroup",
    "LogicalOp",
    "Rule",
    "RuleEvaluator",
    "RuleMatch",
    "get_builtin_trigger",
    "parse_rule",
]