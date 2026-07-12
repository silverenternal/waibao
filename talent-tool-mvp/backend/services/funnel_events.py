"""Funnel 事件追踪器 — T1303.

每个招聘漏斗阶段 (sourced / applied / screened / interviewed / offered / hired)
都会写入一条 funnel_events 记录,用于后续漏斗统计 + 渠道 ROI 归因。

设计要点:
- 写入是幂等的: 同一 (candidate_id, role_id, stage) 重复记录时取最早的.
- 不强制要求 supabase 可用 — 失败时静默退化到内存(单元测试友好).
- 暴露 ``record_stage()`` / ``record_batch()`` 给业务侧手动调用,
  同时支持 ``auto_transition()`` 在 signal 事件触发时调用.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger("recruittech.services.funnel_events")


# 漏斗阶段定义(从粗到细)
FUNNEL_STAGES: tuple[str, ...] = (
    "sourced",
    "applied",
    "screened",
    "interviewed",
    "offered",
    "hired",
)

# 阶段索引 → 用于计算 stage_conversion_rates
STAGE_INDEX: dict[str, int] = {s: i for i, s in enumerate(FUNNEL_STAGES)}


@dataclass(slots=True)
class FunnelEvent:
    """单条漏斗事件."""

    id: str
    org_id: str | None
    candidate_id: str
    role_id: str | None
    stage: str
    source: str
    cost_cents: int
    metadata: dict[str, Any]
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FunnelEventTracker:
    """Funnel 事件追踪 — 内存仓储 + Supabase 持久化双通道.

    用法::

        tracker = FunnelEventTracker(supabase)
        await tracker.record_stage(
            candidate_id=cid, role_id=rid, stage="screened", source="linkedin"
        )
    """

    def __init__(self, supabase: Any | None = None) -> None:
        self.supabase = supabase
        # (candidate_id, role_id, stage) -> FunnelEvent  (内存去重)
        self._events: dict[tuple[str, str | None, str], FunnelEvent] = {}

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    async def record_stage(
        self,
        *,
        candidate_id: str,
        stage: str,
        source: str = "unknown",
        role_id: str | None = None,
        org_id: str | None = None,
        cost_cents: int = 0,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> FunnelEvent | None:
        """记录一次阶段事件;重复则取最早一条 (幂等)."""
        stage = (stage or "").strip().lower()
        if stage not in FUNNEL_STAGES:
            logger.warning("[funnel] unknown stage=%s ignored", stage)
            return None

        key = (str(candidate_id), role_id, stage)
        if key in self._events:
            return self._events[key]

        event = FunnelEvent(
            id=str(uuid.uuid4()),
            org_id=str(org_id) if org_id else None,
            candidate_id=str(candidate_id),
            role_id=str(role_id) if role_id else None,
            stage=stage,
            source=source or "unknown",
            cost_cents=max(0, int(cost_cents)),
            metadata=metadata or {},
            occurred_at=(occurred_at or datetime.now(timezone.utc)).isoformat(),
        )
        self._events[key] = event
        self._persist(event)
        return event

    async def record_batch(self, events: Iterable[dict[str, Any]]) -> int:
        """批量写入;返回成功条数."""
        n = 0
        for e in events:
            res = await self.record_stage(**e)
            if res is not None:
                n += 1
        return n

    def _persist(self, event: FunnelEvent) -> None:
        """尝试写 Supabase;失败则只保留内存记录."""
        if self.supabase is None:
            return
        try:
            self.supabase.table("funnel_events").insert(event.to_dict()).execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[funnel] supabase persist failed: %s", exc)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_events(
        self,
        *,
        org_id: str | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[FunnelEvent]:
        """读取事件 (内存优先;若 supabase 可用则拉真实数据)."""
        if self.supabase is not None:
            try:
                q = self.supabase.table("funnel_events").select("*")
                if org_id:
                    q = q.eq("org_id", org_id)
                if source:
                    q = q.eq("source", source)
                if since:
                    q = q.gte("occurred_at", since.isoformat())
                rows = q.execute().data or []
                # 同步到内存(便于后续去重判断)
                for r in rows:
                    key = (r["candidate_id"], r.get("role_id"), r["stage"])
                    self._events.setdefault(key, FunnelEvent(**r))
            except Exception as exc:  # noqa: BLE001
                logger.debug("[funnel] supabase fetch failed: %s", exc)

        items = list(self._events.values())
        if org_id:
            items = [e for e in items if e.org_id == org_id]
        if source:
            items = [e for e in items if e.source == source]
        if since:
            since_iso = since.isoformat()
            items = [e for e in items if e.occurred_at >= since_iso]
        return items

    def clear(self) -> None:
        """清空内存(主要用于测试)."""
        self._events.clear()


# ---------------------------------------------------------------------------
# Signal -> 漏斗阶段的自动映射
# ---------------------------------------------------------------------------

# 把已有的 SignalType 映射到漏斗阶段
_SIGNAL_TO_STAGE: dict[str, str] = {
    "candidate_ingested": "sourced",
    "candidate_shortlisted": "screened",
    "intro_requested": "interviewed",
    "placement_made": "hired",
}

# 候选 -> 渠道默认值:无法从 metadata 推断 source 时使用
DEFAULT_SOURCE_BY_ACTOR: dict[str, str] = {
    "client": "company_site",
    "talent_partner": "referral",
    "admin": "internal",
}


async def auto_transition(
    tracker: FunnelEventTracker,
    *,
    signal_event_type: str,
    actor_role: str,
    candidate_id: str,
    metadata: dict[str, Any] | None = None,
    role_id: str | None = None,
) -> FunnelEvent | None:
    """根据 signal 事件自动追加一条漏斗记录.

    找不到对应阶段时返回 ``None`` (例如 candidate_viewed 不算漏斗事件).
    """
    stage = _SIGNAL_TO_STAGE.get(signal_event_type)
    if not stage:
        return None

    metadata = metadata or {}
    source = (
        metadata.get("source")
        or metadata.get("channel")
        or DEFAULT_SOURCE_BY_ACTOR.get(actor_role, "unknown")
    )
    cost_cents = int(metadata.get("cost_cents", 0) or 0)

    return await tracker.record_stage(
        candidate_id=candidate_id,
        stage=stage,
        source=str(source),
        role_id=role_id,
        cost_cents=cost_cents,
        metadata=metadata,
    )


__all__ = [
    "FUNNEL_STAGES",
    "FunnelEvent",
    "FunnelEventTracker",
    "STAGE_INDEX",
    "auto_transition",
]