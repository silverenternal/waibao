"""招聘漏斗统计 — T1303 + T1803 (真实数据 + 90 天趋势).

把 ``funnel_events`` 表里的事件聚合成 6 阶段漏斗 + 阶段间转化率。

计算要点:
- 每个阶段 = 该 stage 事件的不同 candidate 数 (去重).
- conversion_rate[i] = next_stage_count / this_stage_count.
- ``compute_funnel`` 同时返回原始计数、阶段转化率,以及 by-source 拆分.
- T1803 新增:
    - ``compute_funnel_with_costs()`` — 漏斗 + 阶段成本合并返回,前端做"成本漏斗"。
    - ``weekly_trend()`` — 90 天回看,按周聚合各阶段候选人增量,前端做趋势图。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from services.funnel_events import (
    FUNNEL_STAGES,
    FunnelEvent,
    FunnelEventTracker,
)


@dataclass(slots=True)
class StageMetric:
    stage: str
    candidates: int  # 不同 candidate 数
    events: int  # 事件总数(含重复)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FunnelStages:
    """漏斗聚合结果."""

    org_id: str | None
    since_days: int
    period_start: str
    period_end: str
    total_candidates: int
    stages: list[StageMetric]
    conversion_rates: dict[str, float]
    by_source: dict[str, dict[str, int]]
    overall_conversion: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "since_days": self.since_days,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_candidates": self.total_candidates,
            "stages": [s.to_dict() for s in self.stages],
            "conversion_rates": self.conversion_rates,
            "by_source": self.by_source,
            "overall_conversion": self.overall_conversion,
        }


class RecruitmentFunnel:
    """Recruitment funnel analytics (聚合层)."""

    def __init__(self, tracker: FunnelEventTracker) -> None:
        self.tracker = tracker

    async def compute_funnel(
        self, org_id: str | None = None, since_days: int = 30
    ) -> FunnelStages:
        """计算漏斗统计.

        Args:
            org_id: 限定组织;None 表示全平台.
            since_days: 回溯天数(默认 30).

        Returns:
            ``FunnelStages`` — 包含各阶段计数、转化率、渠道拆分.
        """
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=max(1, since_days))

        events = self.tracker.get_events(org_id=org_id, since=period_start)

        # 1. 按阶段聚合 (candidate 去重)
        stage_events: dict[str, list[FunnelEvent]] = {s: [] for s in FUNNEL_STAGES}
        for e in events:
            if e.stage in stage_events:
                stage_events[e.stage].append(e)

        stage_metrics: list[StageMetric] = []
        for stage in FUNNEL_STAGES:
            evts = stage_events[stage]
            unique = len({e.candidate_id for e in evts})
            stage_metrics.append(
                StageMetric(stage=stage, candidates=unique, events=len(evts))
            )

        # 2. 转化率 (相邻阶段)
        conversion: dict[str, float] = {}
        for i in range(1, len(FUNNEL_STAGES)):
            prev = stage_metrics[i - 1].candidates
            curr = stage_metrics[i].candidates
            key = f"{FUNNEL_STAGES[i-1]}_to_{FUNNEL_STAGES[i]}"
            conversion[key] = round(curr / prev * 100, 2) if prev > 0 else 0.0

        # 3. 整体转化 (sourced -> hired)
        sourced = stage_metrics[0].candidates
        hired = stage_metrics[-1].candidates
        overall = round(hired / sourced * 100, 2) if sourced > 0 else 0.0

        # 4. 渠道拆分: 每个 source 在每个阶段的 candidate 数
        by_source: dict[str, dict[str, int]] = {}
        for e in events:
            src = e.source or "unknown"
            by_source.setdefault(src, {s: 0 for s in FUNNEL_STAGES})
            if e.stage in by_source[src]:
                by_source[src][e.stage] += 1

        # 5. 跨阶段唯一 candidate 数
        all_candidates = {e.candidate_id for e in events}

        return FunnelStages(
            org_id=org_id,
            since_days=since_days,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            total_candidates=len(all_candidates),
            stages=stage_metrics,
            conversion_rates=conversion,
            by_source=by_source,
            overall_conversion=overall,
        )

    # ------------------------------------------------------------------
    # T1803 — 真实数据增强
    # ------------------------------------------------------------------
    async def compute_funnel_with_costs(
        self, org_id: str | None = None, since_days: int = 30
    ) -> dict[str, Any]:
        """漏斗 + 阶段成本合并返回(给前端做"成本漏斗")。

        在 ``FunnelStages.to_dict()`` 之上叠加每个阶段的 cost 信息。
        """
        result = await self.compute_funnel(org_id=org_id, since_days=since_days)
        cost_profile = self.tracker.stage_cost_profile(org_id=org_id)

        enriched_stages = []
        for s in result.stages:
            cp = cost_profile.get(s.stage, {})
            enriched_stages.append(
                {
                    **s.to_dict(),
                    "total_cost_cents": int(cp.get("total_cost_cents", 0)),
                    "avg_cost_cents": float(cp.get("avg_cost_cents", 0.0)),
                }
            )

        return {
            **result.to_dict(),
            "stages": enriched_stages,
            "cost_profile": cost_profile,
        }

    async def weekly_trend(
        self, org_id: str | None = None, *, weeks: int = 13
    ) -> list[dict[str, Any]]:
        """返回 ``weeks`` 周 × ``FUNNEL_STAGES`` 的新增候选人趋势。

        每条形如::

            {
              "week_start": "2026-04-13",
              "week_end":   "2026-04-19",
              "by_stage":   {"sourced": 247, "applied": 153, ...},
            }

        适合前端 trend chart (T1803)。
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=weeks * 7)
        events = self.tracker.get_events(org_id=org_id, since=start)

        # 初始化 weeks 个桶
        buckets: list[dict[str, Any]] = []
        for i in range(weeks):
            ws = start + timedelta(days=i * 7)
            we = ws + timedelta(days=6)
            buckets.append(
                {
                    "week_start": ws.date().isoformat(),
                    "week_end": we.date().isoformat(),
                    "by_stage": {s: 0 for s in FUNNEL_STAGES},
                    "_seen": {s: set() for s in FUNNEL_STAGES},
                }
            )

        for e in events:
            try:
                occurred = datetime.fromisoformat(
                    e.occurred_at.replace("Z", "+00:00")
                )
            except Exception:  # noqa: BLE001
                continue
            if occurred < start or occurred > end:
                continue
            idx = min(weeks - 1, max(0, (occurred - start).days // 7))
            if e.stage not in buckets[idx]["by_stage"]:
                continue
            cid = e.candidate_id
            if cid in buckets[idx]["_seen"][e.stage]:
                continue
            buckets[idx]["_seen"][e.stage].add(cid)
            buckets[idx]["by_stage"][e.stage] += 1

        # 清理内部 _seen
        for b in buckets:
            b.pop("_seen", None)
        return buckets

    async def seed_and_compute(
        self,
        jsonl_path: str | None = None,
        *,
        org_id: str | None = None,
        since_days: int = 90,
    ) -> dict[str, Any]:
        """(测试/集成) 把 seed JSONL 灌进 tracker 后立即算漏斗。

        用于快速验证 ``scripts/seed_funnel_data.py`` 输出的真实分布。
        """
        if jsonl_path:
            await self.tracker.bulk_load_jsonl(jsonl_path, org_id=org_id)
        return await self.compute_funnel_with_costs(
            org_id=org_id, since_days=since_days
        )


# ---------------------------------------------------------------------------
# 计算工具函数 (便于单元测试和前端 mock)
# ---------------------------------------------------------------------------


def stage_conversion_rates(stages: list[StageMetric]) -> dict[str, float]:
    """从 ``StageMetric`` 列表计算相邻阶段转化率."""
    out: dict[str, float] = {}
    for i in range(1, len(stages)):
        prev = stages[i - 1].candidates
        curr = stages[i].candidates
        out[f"{stages[i-1].stage}_to_{stages[i].stage}"] = (
            round(curr / prev * 100, 2) if prev > 0 else 0.0
        )
    return out


__all__ = [
    "FunnelStages",
    "RecruitmentFunnel",
    "StageMetric",
    "stage_conversion_rates",
]