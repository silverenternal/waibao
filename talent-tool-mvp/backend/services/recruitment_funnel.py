"""招聘漏斗统计 — T1303.

把 ``funnel_events`` 表里的事件聚合成 6 阶段漏斗 + 阶段间转化率。

计算要点:
- 每个阶段 = 该 stage 事件的不同 candidate 数 (去重).
- conversion_rate[i] = next_stage_count / this_stage_count.
- ``compute_funnel`` 同时返回原始计数、阶段转化率,以及 by-source 拆分.
"""
from __future__ import annotations

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