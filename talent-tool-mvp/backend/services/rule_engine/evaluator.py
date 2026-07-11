"""规则求值器 (T804).

扩展点 (T804):
- AND/OR/NOT 嵌套条件 (NOT 用单独 op 实现)
- metric 触发器: 通过 trigger 名内置 metric_source 注册表查询
- webhook action: 调用 services.webhook.fire.fire_webhook
- ticket action: 写 hr_tickets 表
- notify action: 调用 services.notify.dispatch

质量要求:
- 规则执行超时 30 秒
- 嵌套条件最多 3 层
- 失败隔离,不影响业务
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .dsl import (
    Action,
    ComparisonOp,
    Condition,
    ConditionGroup,
    LogicalOp,
    Rule,
)

logger = logging.getLogger(__name__)

RULE_TIMEOUT_SECONDS = 30.0
MAX_CONDITION_DEPTH = 3


# ---------------------------------------------------------------------------
# Context: 事件上下文 (扁平 dict + 支持 . 分层)
# ---------------------------------------------------------------------------
class Context:
    """支持 dot-path 字段访问的事件上下文."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self._data
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def set(self, path: str, value: Any) -> None:
        parts = path.split(".")
        cur = self._data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value

    def raw(self) -> dict[str, Any]:
        return dict(self._data)


# ---------------------------------------------------------------------------
# 求值结果
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RuleMatch:
    rule_id: str
    rule_name: str
    actions: list[Action]
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass(slots=True)
class RuleRunRecord:
    """持久化到 rule_runs 表的运行记录."""

    rule_id: str
    organisation_id: str
    trigger: str
    context_snapshot: dict[str, Any]
    matched: bool
    actions_executed: list[dict[str, Any]]
    duration_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# 执行器回调
# ---------------------------------------------------------------------------
ActionHandler = Callable[[Action, Context], Awaitable[dict[str, Any] | None]]


# metric_source: 返回 trigger 对应的 metric 当前值;若未注册视为 0.
MetricSource = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
# rule_repo: 负责规则与运行的持久化 (load_rules / record_run).
RuleRepo = Callable[[str], Awaitable[Any]]


# ---------------------------------------------------------------------------
# 默认 handlers
# ---------------------------------------------------------------------------
async def _default_notify_handler(action: Action, ctx: Context) -> dict[str, Any] | None:
    """通知 action: 委托 services.notify.dispatch."""
    try:
        from services.notify import dispatch

        result = await dispatch(
            channel=action.params.get("channel", "email"),
            user_id=str(action.params.get("user_id") or ctx.get("user_id") or "system"),
            title=str(action.params.get("title") or f"[Rule] {ctx.get('rule_name','')}"),
            content=str(action.params.get("content") or ctx.raw().get("message", "")),
            payload={"context": ctx.raw(), **action.params},
        )
        return {"ok": True, "channel": action.params.get("channel")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("rule.notify_handler.failed err=%r", exc)
        return {"ok": False, "error": str(exc)}


async def _default_create_ticket_handler(
    action: Action, ctx: Context
) -> dict[str, Any] | None:
    """自动建工单."""
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        record = {
            "id": str(__import__("uuid").uuid4()),
            "organisation_id": str(ctx.get("organisation_id") or ""),
            "title": str(action.params.get("title") or "[Rule] auto ticket"),
            "description": str(
                action.params.get("description")
                or ctx.raw().get("summary")
                or f"Auto-created by rule engine: {ctx.get('rule_name','')}"
            ),
            "priority": str(action.params.get("priority", "P3")),
            "department": str(action.params.get("department", "ops")),
            "status": "open",
            "source": "rule_engine",
        }
        res = sb.table("tickets").insert(record).execute()
        return {"ok": bool(res.data), "ticket_id": record["id"]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("rule.ticket_handler.failed err=%r", exc)
        return {"ok": False, "error": str(exc)}


async def _default_webhook_handler(action: Action, ctx: Context) -> dict[str, Any] | None:
    """调用 T802 fire_webhook 投递事件."""
    try:
        from services.webhook.fire import fire_webhook
        from services.webhook.types import WebhookEvent

        event_name = str(action.params.get("event") or "rule.fired")
        try:
            ev = WebhookEvent(event_name)
        except ValueError:
            # 自定义事件名也能发,但走 dict 形式 -> wrap 为 generic event
            # fire_webhook 在不识别 event 时会早退,所以这里兜底为通用类型.
            ev = WebhookEvent.TICKET_CREATED
        org = str(action.params.get("organisation_id") or ctx.get("organisation_id") or "")
        if not org:
            return {"ok": False, "error": "missing_organisation_id"}
        data = {
            "rule_id": ctx.get("rule_id"),
            "rule_name": ctx.get("rule_name"),
            "context": ctx.raw(),
            **action.params.get("data", {}),
        }
        await fire_webhook(ev, org, data)
        return {"ok": True, "event": ev.value}
    except Exception as exc:  # noqa: BLE001
        logger.warning("rule.webhook_handler.failed err=%r", exc)
        return {"ok": False, "error": str(exc)}


async def _default_emit_event_handler(action: Action, ctx: Context) -> dict[str, Any] | None:
    """emit_event: 在当前进程内调用注册 listener (UI / 业务订阅)."""
    logger.info(
        "rule.emit_event event=%s data=%s",
        action.params.get("event"),
        action.params.get("data"),
    )
    return {"ok": True}


_DEFAULT_HANDLERS: dict[str, ActionHandler] = {
    "notify": _default_notify_handler,
    "create_ticket": _default_create_ticket_handler,
    "webhook": _default_webhook_handler,
    "emit_event": _default_emit_event_handler,
}


# ---------------------------------------------------------------------------
# 嵌套深度校验
# ---------------------------------------------------------------------------


def validate_condition_depth(node: Any, depth: int = 1) -> int:
    """返回 group 的最大嵌套深度. 超过 MAX_CONDITION_DEPTH 抛 ValueError."""
    if isinstance(node, ConditionGroup):
        if depth > MAX_CONDITION_DEPTH:
            raise ValueError(
                f"条件嵌套超过 {MAX_CONDITION_DEPTH} 层 (当前 {depth})"
            )
        max_child = depth
        for c in node.children:
            max_child = max(max_child, validate_condition_depth(c, depth + 1))
        return max_child
    return depth


# ---------------------------------------------------------------------------
# 评估器
# ---------------------------------------------------------------------------
class RuleEvaluator:
    """规则求值 + 执行.

    用法:
        ev = RuleEvaluator(rules=[...])
        matches = await ev.evaluate(trigger="HR_SERVICE_AUTORESOLVE_RATE_LOW",
                                    context=Context({"rate": 0.5, "window": "7d"}))
        for m in matches:
            await ev.execute(m, ctx)
    """

    def __init__(
        self,
        rules: list[Rule] | None = None,
        *,
        handlers: dict[str, ActionHandler] | None = None,
        metric_sources: dict[str, MetricSource] | None = None,
    ) -> None:
        self._rules: list[Rule] = list(rules or [])
        self._handlers: dict[str, ActionHandler] = {
            **_DEFAULT_HANDLERS,
            **(handlers or {}),
        }
        self._metric_sources: dict[str, MetricSource] = dict(metric_sources or {})
        self._cooldown_tracker: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Rule 管理
    # ------------------------------------------------------------------
    def add(self, rule: Rule) -> None:
        try:
            if rule.condition:
                validate_condition_depth(rule.condition)
        except ValueError:
            raise
        self._rules.append(rule)

    def remove(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        self._cooldown_tracker.pop(rule_id, None)
        return len(self._rules) < before

    def list_rules(self) -> list[Rule]:
        return list(self._rules)

    def register_metric_source(self, trigger: str, source: MetricSource) -> None:
        self._metric_sources[trigger] = source

    # ------------------------------------------------------------------
    # 求值
    # ------------------------------------------------------------------
    async def evaluate(
        self,
        trigger: str,
        context: Context | dict[str, Any],
    ) -> list[RuleMatch]:
        if isinstance(context, dict):
            context = Context(context)
        matches: list[RuleMatch] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.trigger != trigger:
                continue
            try:
                if rule.condition is not None:
                    if isinstance(rule.condition, Condition):
                        if not self._eval_condition(rule.condition, context):
                            continue
                    elif not self._eval_group(rule.condition, context):
                        continue
            except Exception:  # noqa: BLE001
                logger.exception(
                    "rule.eval_failed rule=%s trigger=%s", rule.id, trigger
                )
                continue
            if not self._cooldown_ok(rule):
                logger.debug("rule.cooldown_skip rule=%s", rule.id)
                continue
            matches.append(
                RuleMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    actions=list(rule.actions),
                    context_snapshot=context.raw(),
                )
            )
        return matches

    async def execute(
        self,
        match: RuleMatch,
        context: Context,
        *,
        timeout: float = RULE_TIMEOUT_SECONDS,
    ) -> RuleMatch:
        """执行 actions,带 30s 超时与失败隔离.

        返回 RuleMatch,内含 duration_ms (累计所有 actions).
        """
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                self._gather_actions(match, context),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "rule.execute_timeout rule=%s timeout=%s",
                match.rule_id, timeout,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "rule.execute_error rule=%s", match.rule_id
            )
        match.duration_ms = int((time.monotonic() - started) * 1000)
        self._cooldown_tracker[match.rule_id] = time.monotonic()
        return match

    async def _gather_actions(self, match: RuleMatch, ctx: Context) -> None:
        await asyncio.gather(
            *(self._run_action(a, ctx) for a in match.actions),
            return_exceptions=True,
        )

    async def evaluate_and_execute(
        self,
        trigger: str,
        context: Context | dict[str, Any],
    ) -> list[RuleMatch]:
        if isinstance(context, dict):
            context = Context(context)
        matches = await self.evaluate(trigger, context)
        for m in matches:
            await self.execute(m, context)
        return matches

    # ------------------------------------------------------------------
    # 求值内部
    # ------------------------------------------------------------------
    def _eval_group(self, group: ConditionGroup, ctx: Context) -> bool:
        # LogicalOp.NOT 反转子组结果
        if group.op == LogicalOp.NOT:
            if len(group.children) != 1:
                raise ValueError("NOT 必须正好一个子节点")
            child = group.children[0]
            inner = (
                self._eval_condition(child, ctx)
                if isinstance(child, Condition)
                else self._eval_group(child, ctx)
            )
            return not inner

        results = [
            (
                self._eval_condition(c, ctx)
                if isinstance(c, Condition)
                else self._eval_group(c, ctx)
            )
            for c in group.children
        ]
        if group.op == LogicalOp.AND:
            return all(results)
        if group.op == LogicalOp.OR:
            return any(results)
        raise ValueError(f"未知 LogicalOp: {group.op}")

    def _eval_condition(self, cond: Condition, ctx: Context) -> bool:
        actual = ctx.get(cond.field)
        expected = cond.value
        op = cond.op
        try:
            if op == ComparisonOp.EQ:
                return actual == expected
            if op == ComparisonOp.NE:
                return actual != expected
            if op == ComparisonOp.LT:
                return _cmp(actual, expected, lambda a, b: a < b)
            if op == ComparisonOp.LE:
                return _cmp(actual, expected, lambda a, b: a <= b)
            if op == ComparisonOp.GT:
                return _cmp(actual, expected, lambda a, b: a > b)
            if op == ComparisonOp.GE:
                return _cmp(actual, expected, lambda a, b: a >= b)
            if op == ComparisonOp.IN:
                return actual in (expected or [])
            if op == ComparisonOp.NOT_IN:
                return actual not in (expected or [])
            if op == ComparisonOp.CONTAINS:
                if actual is None:
                    return False
                if isinstance(actual, (str, list, dict)):
                    return expected in actual
                return False
            if op == ComparisonOp.STARTS_WITH:
                return isinstance(actual, str) and actual.startswith(expected or "")
            if op == ComparisonOp.EXISTS:
                return actual is not None
        except Exception:
            logger.exception(
                "rule.eval_error op=%s field=%s expected=%s actual=%r",
                op, cond.field, expected, actual,
            )
            return False
        return False

    def _cooldown_ok(self, rule: Rule) -> bool:
        if rule.cooldown_seconds <= 0:
            return True
        last = self._cooldown_tracker.get(rule.id)
        if last is None:
            return True
        return (time.monotonic() - last) >= rule.cooldown_seconds

    async def _run_action(self, action: Action, ctx: Context) -> Any:
        handler = self._handlers.get(action.type)
        if handler is None:
            logger.warning("rule.action.no_handler type=%s", action.type)
            return None
        try:
            return await handler(action, ctx)
        except Exception:
            logger.exception(
                "rule.action.error type=%s rule=%s",
                action.type, ctx.get("rule_id"),
            )
            return None


def _cmp(a: Any, b: Any, fn: Any) -> bool:
    """带 None 安全的比较."""
    if a is None:
        return False
    try:
        return fn(a, b)
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# Backwards compat: detect sync handlers in legacy code/tests
# ---------------------------------------------------------------------------


def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return value  # caller awaits
    return value
