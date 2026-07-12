"""渠道归因 + ROI 分析 — T1303.

支持三种归因模型:

1. **first_touch** — 候选人首次接触渠道(sourced 事件)承担全部功劳.
2. **last_touch** — 候选人最近一次漏斗阶段(offered / hired)承担全部功劳.
3. **multi_touch (linear)** — 在 sourced → hired 之间的所有事件平分功劳.

ROI 计算:
- 每个渠道 cost = channel_spend 表累计 + funnel_events.cost_cents 累计.
- 每个渠道 value = hires * avg_revenue_per_hire(默认 100_000 cents = ¥1000 占位值,
  可由 channel_revenue 表或 metadata 覆盖).
- ROI = (value - cost) / cost
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from services.funnel_events import (
    FUNNEL_STAGES,
    FunnelEvent,
    FunnelEventTracker,
)

logger = logging.getLogger("recruittech.services.channel_attribution")

# 默认每次入职带来的营收估值(单位: cents);可被 channel_revenue 覆盖
DEFAULT_REVENUE_PER_HIRE_CENTS = 100_000


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

ATTRIBUTION_MODELS: tuple[str, ...] = ("first_touch", "last_touch", "multi_touch")


@dataclass(slots=True)
class ChannelAttribution:
    """单渠道在单模型下的归因结果."""

    channel: str
    model: str  # first_touch / last_touch / multi_touch
    candidates: int  # 归因到此渠道的不同候选人数
    hires: int  # 归因的入职数
    hire_credit: float  # 每次入职的贡献权重(多触点模型会 < 1)
    cost_cents: int
    revenue_cents: int
    roi: float  # (revenue - cost) / cost
    cost_per_hire: float  # cost / hires

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChannelROIReport:
    """完整 ROI 报告 (按模型分组)."""

    org_id: str | None
    since_days: int
    period_start: str
    period_end: str
    by_model: dict[str, list[ChannelAttribution]]  # model -> [ChannelAttribution]
    best_channel_by_model: dict[str, str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "since_days": self.since_days,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "by_model": {
                model: [c.to_dict() for c in chs]
                for model, chs in self.by_model.items()
            },
            "best_channel_by_model": self.best_channel_by_model,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------


class ChannelAttributionService:
    """渠道归因 + ROI 服务."""

    def __init__(
        self,
        tracker: FunnelEventTracker,
        *,
        revenue_per_hire_cents: int = DEFAULT_REVENUE_PER_HIRE_CENTS,
        channel_spend_lookup: Any | None = None,
    ) -> None:
        """Args:
        tracker: 漏斗事件追踪器.
        revenue_per_hire_cents: 默认每次 hire 营收估值(单位 cents).
        channel_spend_lookup: 可选 ``async (org_id, since) -> dict[channel, cents]``
            用于从 channel_spend 表拉取额外投放支出.
        """
        self.tracker = tracker
        self.revenue_per_hire = int(revenue_per_hire_cents)
        self._spend_lookup = channel_spend_lookup

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    async def compute_channel_roi(
        self,
        org_id: str | None = None,
        since_days: int = 30,
        *,
        models: list[str] | None = None,
    ) -> ChannelROIReport:
        """计算渠道 ROI (多个归因模型并行)."""
        models = models or list(ATTRIBUTION_MODELS)
        for m in models:
            if m not in ATTRIBUTION_MODELS:
                raise ValueError(f"unknown attribution model: {m}")

        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=max(1, since_days))

        events = self.tracker.get_events(org_id=org_id, since=period_start)
        spend = await self._fetch_spend(org_id, period_start)

        # 按渠道聚合: model -> { channel -> ChannelStats }
        report_by_model: dict[str, list[ChannelAttribution]] = {}

        for model in models:
            channel_stats = self._aggregate(events, model=model)
            attributions: list[ChannelAttribution] = []

            for channel, stats in channel_stats.items():
                cost = stats["cost_cents"] + spend.get(channel, 0)
                hires = stats["hires"]
                hire_credit = stats["hire_credit"]
                revenue = int(round(hire_credit * self.revenue_per_hire))
                roi = ((revenue - cost) / cost) if cost > 0 else 0.0
                cph = (cost / hires) if hires > 0 else float("inf")
                attributions.append(
                    ChannelAttribution(
                        channel=channel,
                        model=model,
                        candidates=stats["candidates"],
                        hires=hires,
                        hire_credit=round(hire_credit, 2),
                        cost_cents=cost,
                        revenue_cents=revenue,
                        roi=round(roi, 4),
                        cost_per_hire=round(cph, 2) if cph != float("inf") else -1.0,
                    )
                )

            attributions.sort(key=lambda a: a.roi, reverse=True)
            report_by_model[model] = attributions

        # 找出每个模型下 ROI 最高的渠道
        best: dict[str, str] = {}
        for model, attrs in report_by_model.items():
            if attrs:
                # ROI 为 0 时按 hires 数挑
                top = max(attrs, key=lambda a: (a.roi, a.hires))
                best[model] = top.channel

        summary = self._summarize(report_by_model)

        return ChannelROIReport(
            org_id=org_id,
            since_days=since_days,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            by_model=report_by_model,
            best_channel_by_model=best,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # 归因模型实现
    # ------------------------------------------------------------------
    def _aggregate(
        self, events: list[FunnelEvent], *, model: str
    ) -> dict[str, dict[str, Any]]:
        """按 model 计算每个渠道的 stats."""
        # 按 candidate 聚合其事件序列(按 occurred_at 排序)
        by_candidate: dict[str, list[FunnelEvent]] = defaultdict(list)
        for e in events:
            by_candidate[e.candidate_id].append(e)

        # channel -> {candidates, hires, hire_credit, cost_cents}
        agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "candidates": 0,
                "hires": 0,
                "hire_credit": 0.0,
                "cost_cents": 0,
            }
        )

        for cid, evts in by_candidate.items():
            evts.sort(key=lambda e: e.occurred_at)
            sources = [e.source for e in evts]
            costs = sum(e.cost_cents for e in evts)
            hired = any(e.stage == "hired" for e in evts)

            if model == "first_touch":
                # sourced 阶段的事件 / 第一条
                first = evts[0]
                ch = first.source or "unknown"
                agg[ch]["candidates"] += 1
                agg[ch]["cost_cents"] += costs
                if hired:
                    agg[ch]["hires"] += 1
                    agg[ch]["hire_credit"] += 1.0

            elif model == "last_touch":
                # offered/hired 阶段优先;否则最后一条
                terminal = next(
                    (e for e in reversed(evts) if e.stage in ("offered", "hired")),
                    evts[-1],
                )
                ch = terminal.source or "unknown"
                agg[ch]["candidates"] += 1
                agg[ch]["cost_cents"] += costs
                if hired:
                    agg[ch]["hires"] += 1
                    agg[ch]["hire_credit"] += 1.0

            elif model == "multi_touch":
                # 多触点: candidates/cost 按比例分摊到参与的渠道
                # hire_credit 平均分配给每个出现过事件的渠道
                unique_sources = list(dict.fromkeys(sources))  # 保序去重
                if not unique_sources:
                    unique_sources = ["unknown"]
                n = len(unique_sources)
                for ch in unique_sources:
                    agg[ch]["candidates"] += 1.0 / n  # 比例计数
                    agg[ch]["cost_cents"] += int(round(costs / n))
                if hired:
                    credit = 1.0 / n
                    for ch in unique_sources:
                        agg[ch]["hires"] += credit  # type: ignore[operator]
                        agg[ch]["hire_credit"] += credit

        # int 化 candidates/hires(multi_touch 可能是小数)
        for ch, stats in agg.items():
            stats["candidates"] = int(round(stats["candidates"]))
            stats["hires"] = int(round(stats["hires"]))

        return dict(agg)

    # ------------------------------------------------------------------
    # spend 查询
    # ------------------------------------------------------------------
    async def _fetch_spend(
        self, org_id: str | None, since: datetime
    ) -> dict[str, int]:
        if self._spend_lookup is None:
            return {}
        try:
            data = await self._spend_lookup(org_id, since)
            return {str(k): int(v) for k, v in (data or {}).items()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[channel-attribution] spend lookup failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    @staticmethod
    def _summarize(by_model: dict[str, list[ChannelAttribution]]) -> dict[str, Any]:
        """生成跨模型的汇总摘要."""
        out: dict[str, Any] = {}
        for model, attrs in by_model.items():
            if not attrs:
                out[model] = {"channels": 0, "total_hires": 0, "total_cost": 0}
                continue
            out[model] = {
                "channels": len(attrs),
                "total_hires": sum(a.hires for a in attrs),
                "total_cost_cents": sum(a.cost_cents for a in attrs),
                "total_revenue_cents": sum(a.revenue_cents for a in attrs),
                "avg_roi": round(
                    sum(a.roi for a in attrs) / len(attrs), 4
                ),
            }
        return out


__all__ = [
    "ATTRIBUTION_MODELS",
    "ChannelAttribution",
    "ChannelAttributionService",
    "ChannelROIReport",
    "DEFAULT_REVENUE_PER_HIRE_CENTS",
]