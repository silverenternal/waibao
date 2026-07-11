"""规则调度器 (T804).

每 5 分钟扫描 metric 触发器 (HR_SERVICE_AUTORESOLVE_RATE_LOW 等),
对每个 metric 调用对应 metric_source,组装 context,执行 RuleEvaluator.

默认 metric sources:
- HR_SERVICE_AUTORESOLVE_RATE_LOW  -> 计算 hr_tickets 的 auto_resolved/total
- MATCH_FUNNEL_DROP               -> 计算 signals 中 step 转化下降
- 其他 metric 来源可在外部注册.

启动方式 (FastAPI lifespan):
    from services.rule_engine.scheduler import start_scheduler
    async def lifespan(app):
        sched = await start_scheduler()
        yield
        await sched.stop()
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from .dsl import Rule
from .evaluator import (
    Context,
    RuleEvaluator,
    RuleRunRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300  # 5 分钟

MetricSource = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


# ---------------------------------------------------------------------------
# 内置 metric sources (DB 查询)
# ---------------------------------------------------------------------------


async def hr_autoresolve_metric(ctx: dict[str, Any]) -> dict[str, Any]:
    """HR 工单自动解决率. window in {1d,7d,30d}. 失败返回 rate=1 (无触发)."""
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        window = ctx.get("window") or "7d"
        days = {"1d": 1, "7d": 7, "30d": 30}.get(window, 7)
        since = (
            datetime.now(tz=timezone.utc) - timedelta(days=days)
        ).isoformat()
        res = (
            sb.table("tickets")
            .select("id,status,created_at")
            .gte("created_at", since)
            .execute()
        )
        rows = res.data or []
        total = len(rows)
        if not total:
            return {"rate": 1.0, "window": window, "sample_size": 0}
        # 简化: "resolved"/"auto_resolved"/"closed" 视为自动解决
        auto_states = {"resolved", "auto_resolved", "closed"}
        auto = sum(1 for r in rows if (r.get("status") or "").lower() in auto_states)
        return {
            "rate": auto / total,
            "window": window,
            "sample_size": total,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("hr_autoresolve_metric.failed err=%r", exc)
        return {"rate": 1.0, "window": ctx.get("window") or "7d", "sample_size": 0}


async def match_funnel_metric(ctx: dict[str, Any]) -> dict[str, Any]:
    """匹配漏斗下降检测. step in {view, save, apply, interview}.

    返回:
        previous_rate, current_rate, step
    """
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        step = ctx.get("step") or "apply"
        # 过去 14 天 vs 前 14 天
        now = datetime.now(tz=timezone.utc)
        prev_start = (now - timedelta(days=28)).isoformat()
        prev_end = (now - timedelta(days=14)).isoformat()
        curr_start = prev_end
        curr_end = now.isoformat()

        def _count(start: str, end: str) -> int:
            try:
                r = (
                    sb.table("signals")
                    .select("id", count="exact")
                    .eq("kind", f"funnel.{step}")
                    .gte("occurred_at", start)
                    .lt("occurred_at", end)
                    .execute()
                )
                return int(r.count or 0)
            except Exception:  # noqa: BLE001
                return 0

        prev_count = _count(prev_start, prev_end)
        curr_count = _count(curr_start, curr_end)
        prev_rate = prev_count / 14.0 if prev_count else 0.0
        curr_rate = curr_count / 14.0 if curr_count else 0.0
        return {
            "step": step,
            "previous_rate": prev_rate,
            "current_rate": curr_rate,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("match_funnel_metric.failed err=%r", exc)
        return {"step": ctx.get("step"), "previous_rate": 0, "current_rate": 0}


DEFAULT_METRIC_SOURCES: dict[str, MetricSource] = {
    "HR_SERVICE_AUTORESOLVE_RATE_LOW": hr_autoresolve_metric,
    "MATCH_FUNNEL_DROP": match_funnel_metric,
}


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class RuleScheduler:
    def __init__(
        self,
        evaluator: RuleEvaluator,
        *,
        rule_loader: Callable[[], Awaitable[list[Rule]]] | None = None,
        run_recorder: Callable[[RuleRunRecord], Awaitable[None]] | None = None,
        metric_sources: dict[str, MetricSource] | None = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._evaluator = evaluator
        self._rule_loader = rule_loader
        self._run_recorder = run_recorder
        self._interval = interval_seconds
        # 仅在 evaluator 未注册时填充默认;保留外部显式注入优先.
        for k, v in (metric_sources or DEFAULT_METRIC_SOURCES).items():
            if k not in self._evaluator._metric_sources:  # noqa: SLF001
                self._evaluator.register_metric_source(k, v)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._loop(), name="rule-scheduler"
        )
        logger.info("rule_scheduler.started interval=%ss", self._interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
        logger.info("rule_scheduler.stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("rule_scheduler.tick_failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    async def tick(self) -> dict[str, Any]:
        """扫描一次 metric 触发器并执行匹配规则.

        Returns:
            {"scanned": int, "matched": int, "errors": int}
        """
        # 1. 加载规则
        rules: list[Rule]
        if self._rule_loader:
            rules = await self._rule_loader()
            # 同步到 evaluator (覆盖式)
            existing_ids = {r.id for r in self._evaluator.list_rules()}
            for r in rules:
                if r.id not in existing_ids:
                    self._evaluator.add(r)
        else:
            rules = self._evaluator.list_rules()

        scanned = 0
        matched = 0
        errors = 0
        # 2. 收集所有 metric 触发器
        metric_triggers = set((self._evaluator._metric_sources or {}).keys())  # noqa: SLF001
        # 也兜底用 builtins
        from .builtins import BUILTIN_TRIGGERS

        for name, _ in BUILTIN_TRIGGERS.items():
            # 仅 metric 类触发器进入扫描;event-based 触发器 (webhook / 业务流) 不在这里扫.
            if name.endswith("_LOW") or name.endswith("_DROP") or name.startswith("MATCH_"):
                metric_triggers.add(name)
        metric_triggers = metric_triggers & {r.trigger for r in rules if r.enabled}

        # 3. 对每个 metric 触发器,求一次当前值并求值规则
        for trigger in metric_triggers:
            source = self._evaluator._metric_sources.get(trigger)  # noqa: SLF001
            if not source:
                continue
            try:
                payload = await source({})
            except Exception:  # noqa: BLE001
                logger.exception("metric_source.failed trigger=%s", trigger)
                errors += 1
                continue
            scanned += 1
            ctx = Context(payload)
            try:
                ms = await self._evaluator.evaluate(trigger, ctx)
            except Exception:  # noqa: BLE001
                logger.exception("evaluator.failed trigger=%s", trigger)
                errors += 1
                continue
            matched += len(ms)
            for m in ms:
                # 注入 rule 元信息到 context 供 actions 使用
                ctx.set("rule_id", m.rule_id)
                ctx.set("rule_name", m.rule_name)
                try:
                    await self._evaluator.execute(m, ctx)
                except Exception:  # noqa: BLE001
                    logger.exception("execute.failed rule=%s", m.rule_id)
                    errors += 1
                if self._run_recorder:
                    try:
                        await self._run_recorder(
                            RuleRunRecord(
                                rule_id=m.rule_id,
                                organisation_id="",
                                trigger=trigger,
                                context_snapshot=ctx.raw(),
                                matched=True,
                                actions_executed=[
                                    a.to_dict() for a in m.actions
                                ],
                                duration_ms=m.duration_ms,
                            )
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("run_recorder.failed")
        logger.info(
            "rule_scheduler.tick scanned=%s matched=%s errors=%s",
            scanned, matched, errors,
        )
        return {"scanned": scanned, "matched": matched, "errors": errors}


# ---------------------------------------------------------------------------
# 默认 run recorder: 写 rule_runs 表 (best-effort)
# ---------------------------------------------------------------------------


async def default_run_recorder(record: RuleRunRecord) -> None:
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        sb.table("rule_runs").insert(
            {
                "id": str(uuid.uuid4()),
                "rule_id": record.rule_id,
                "organisation_id": record.organisation_id,
                "trigger": record.trigger,
                "context_snapshot": record.context_snapshot,
                "matched": record.matched,
                "actions_executed": record.actions_executed,
                "duration_ms": record.duration_ms,
                "error": record.error,
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.exception("default_run_recorder.failed")


# ---------------------------------------------------------------------------
# DB-backed rule loader
# ---------------------------------------------------------------------------


async def load_rules_from_db() -> list[Rule]:
    """从 rules 表加载. 失败返回 []."""
    from .dsl import Action, ConditionGroup, parse_rule

    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        res = sb.table("rules").select("*").eq("enabled", True).execute()
        out: list[Rule] = []
        for r in res.data or []:
            payload = {
                "id": r["id"],
                "name": r.get("name") or "",
                "description": r.get("description") or "",
                "enabled": r.get("enabled", True),
                "trigger": r["trigger"],
                "condition": r.get("condition"),
                "actions": r.get("actions") or [],
                "cooldown_seconds": r.get("cooldown_seconds", 0),
                "tags": r.get("tags") or [],
            }
            try:
                out.append(parse_rule(payload))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "load_rules_from_db.parse_failed id=%s", r.get("id")
                )
        return out
    except Exception:  # noqa: BLE001
        logger.exception("load_rules_from_db.failed")
        return []


# ---------------------------------------------------------------------------
# 启动辅助
# ---------------------------------------------------------------------------

_scheduler: RuleScheduler | None = None


async def start_scheduler(
    *,
    evaluator: RuleEvaluator | None = None,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> RuleScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    ev = evaluator or RuleEvaluator()
    sched = RuleScheduler(
        evaluator=ev,
        rule_loader=load_rules_from_db,
        run_recorder=default_run_recorder,
        interval_seconds=interval_seconds,
    )
    await sched.start()
    _scheduler = sched
    return sched


def get_scheduler() -> RuleScheduler | None:
    return _scheduler
