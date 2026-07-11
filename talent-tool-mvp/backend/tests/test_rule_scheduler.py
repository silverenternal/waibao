"""T804 - Scheduler 测试."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from services.rule_engine.dsl import Action, Condition, Rule
from services.rule_engine.evaluator import ComparisonOp, RuleEvaluator
from services.rule_engine.scheduler import (
    DEFAULT_METRIC_SOURCES,
    RuleScheduler,
    hr_autoresolve_metric,
    match_funnel_metric,
)


# ---------------------------------------------------------------------------
# 内置 metric sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hr_autoresolve_metric_returns_dict(monkeypatch):
    """无 DB 时返回默认 rate=1.0 (无触发)."""
    class _FakeSB:
        def table(self, _):
            class _Q:
                def select(self, *_a, **_kw):
                    return self

                def gte(self, *_a, **_kw):
                    return self

                def execute(self):
                    return type("R", (), {"data": []})()

            return _Q()

    from api import deps

    deps._supabase_admin_client = _FakeSB()  # type: ignore[attr-defined]
    out = await hr_autoresolve_metric({})
    assert "rate" in out
    assert "window" in out


@pytest.mark.asyncio
async def test_match_funnel_metric_handles_missing_table(monkeypatch):
    class _FakeSB:
        def table(self, _):
            class _Q:
                def select(self, *_a, **_kw):
                    return self

                def eq(self, *_a, **_kw):
                    return self

                def gte(self, *_a, **_kw):
                    return self

                def lt(self, *_a, **_kw):
                    return self

                def execute(self):
                    return type("R", (), {"count": 0})()

            return _Q()

    from api import deps

    deps._supabase_admin_client = _FakeSB()  # type: ignore[attr-defined]
    out = await match_funnel_metric({"step": "apply"})
    assert out["step"] == "apply"
    assert "current_rate" in out


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_scans_metric_triggers():
    rule = Rule.new(
        name="hr_low",
        trigger="HR_SERVICE_AUTORESOLVE_RATE_LOW",
        actions=[Action(type="emit_event", params={"event": "ping"})],
        condition=Condition(op=ComparisonOp.LT, field="rate", value=0.6),
    )
    ev = RuleEvaluator(rules=[rule])

    called = []

    async def fake_metric(ctx):
        called.append("metric")
        return {"rate": 0.3, "window": "7d", "sample_size": 100}

    ev.register_metric_source(
        "HR_SERVICE_AUTORESOLVE_RATE_LOW", fake_metric
    )

    recs = []

    async def recorder(rec):
        recs.append(rec)

    sched = RuleScheduler(
        evaluator=ev,
        run_recorder=recorder,
        interval_seconds=60,
    )
    summary = await sched.tick()
    assert summary["scanned"] >= 1
    assert "metric" in called


@pytest.mark.asyncio
async def test_scheduler_handles_metric_failure():
    rule = Rule.new(
        name="x",
        trigger="HR_SERVICE_AUTORESOLVE_RATE_LOW",
        actions=[Action(type="emit_event", params={})],
        condition=Condition(op=ComparisonOp.LT, field="rate", value=0.6),
    )
    ev = RuleEvaluator(rules=[rule])

    async def bad_metric(ctx):
        raise RuntimeError("db down")

    ev.register_metric_source("HR_SERVICE_AUTORESOLVE_RATE_LOW", bad_metric)
    sched = RuleScheduler(evaluator=ev, interval_seconds=60)
    summary = await sched.tick()
    # metric 失败但 scheduler 不抛
    assert "errors" in summary


@pytest.mark.asyncio
async def test_scheduler_no_matching_rules():
    ev = RuleEvaluator(rules=[])
    sched = RuleScheduler(evaluator=ev, interval_seconds=60)
    summary = await sched.tick()
    assert summary["scanned"] == 0


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    ev = RuleEvaluator(rules=[])
    sched = RuleScheduler(evaluator=ev, interval_seconds=0.1)

    async def loader():
        return []

    sched._rule_loader = loader
    await sched.start()
    await asyncio.sleep(0.15)
    await sched.stop()
    # 进程未挂即可


def test_default_metric_sources_registered():
    assert "HR_SERVICE_AUTORESOLVE_RATE_LOW" in DEFAULT_METRIC_SOURCES
    assert "MATCH_FUNNEL_DROP" in DEFAULT_METRIC_SOURCES
