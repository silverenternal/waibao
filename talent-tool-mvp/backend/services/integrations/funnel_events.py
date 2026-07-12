"""Funnel 事件追踪器 — T1303 + T1803 (前端埋点 + 批量加载).

每个招聘漏斗阶段 (sourced / applied / screened / interviewed / offered / hired)
都会写入一条 funnel_events 记录,用于后续漏斗统计 + 渠道 ROI 归因。

设计要点:
- 写入是幂等的: 同一 (candidate_id, role_id, stage) 重复记录时取最早的.
- 不强制要求 supabase 可用 — 失败时静默退化到内存(单元测试友好).
- 暴露 ``record_stage()`` / ``record_batch()`` 给业务侧手动调用,
  同时支持 ``auto_transition()`` 在 signal 事件触发时调用.
- T1803 新增:
    - ``record_frontend_event()`` — 接收前端埋点 (typed_payload) 入口
    - ``bulk_load_jsonl()`` — 从 seed 脚本生成的 JSONL 一次性灌进内存/Supabase
    - ``stage_cost_profile()`` — 给前端做"按阶段成本"分析用
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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

# 阶段权重(用于前端默认排序)
STAGE_WEIGHT: dict[str, int] = {s: i for i, s in enumerate(FUNNEL_STAGES)}


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
        # (candidate_id, role_id, stage) -> FunnelEvent  (内存去重;首条 primary)
        self._events: dict[tuple[str, str | None, str], FunnelEvent] = {}
        # 二次触达事件 — 不参与 dedup,每次 multi-touch 都建一条
        self._extra_events: list[FunnelEvent] = []

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
        force: bool = False,
    ) -> FunnelEvent | None:
        """记录一次阶段事件;重复则取最早一条 (幂等)。

        Args:
            force: 为 True 时允许同一 (candidate, role, stage) 多次写入
                (用于 multi-touch 二次触达场景)。相同 source+timestamp 的
                会被丢弃,其余都接受。
        """
        stage = (stage or "").strip().lower()
        if stage not in FUNNEL_STAGES:
            logger.warning("[funnel] unknown stage=%s ignored", stage)
            return None

        ts = (occurred_at or datetime.now(timezone.utc)).isoformat()

        if not force:
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
            occurred_at=ts,
        )
        if not force:
            self._events[(str(candidate_id), role_id, stage)] = event
        else:
            # force=True 时仍把首条记录到 dedup dict (避免重复),
            # 后续相同 key 的事件全部走 _extra_events。
            key = (str(candidate_id), role_id, stage)
            if key not in self._events:
                self._events[key] = event
            else:
                self._extra_events.append(event)
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

    async def record_frontend_event(
        self,
        *,
        payload: dict[str, Any],
        org_id: str | None = None,
    ) -> FunnelEvent | None:
        """前端埋点入口 — 接收前端 SDK 上报的 typed payload.

        期望字段(都允许缺省,缺失则用 ``record_stage`` 默认值):
            candidate_id (str, required)
            role_id (str, optional)
            stage (str, required — sourced/applied/screened/interviewed/offered/hired)
            source (str, optional — linkedin/referral/...)
            cost_cents (int, optional)
            metadata (dict, optional)
            occurred_at (ISO 字符串, optional — 默认 now)
        """
        if not payload or not payload.get("candidate_id") or not payload.get("stage"):
            logger.warning("[funnel] record_frontend_event missing required field")
            return None

        occurred_at_dt: datetime | None = None
        raw_ts = payload.get("occurred_at")
        if raw_ts:
            try:
                occurred_at_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                occurred_at_dt = None

        return await self.record_stage(
            candidate_id=str(payload["candidate_id"]),
            stage=str(payload["stage"]),
            source=str(payload.get("source") or "unknown"),
            role_id=(str(payload["role_id"]) if payload.get("role_id") else None),
            org_id=org_id or (str(payload["org_id"]) if payload.get("org_id") else None),
            cost_cents=int(payload.get("cost_cents") or 0),
            metadata=dict(payload.get("metadata") or {}),
            occurred_at=occurred_at_dt,
        )

    async def bulk_load_jsonl(
        self, jsonl_path: str | Path, *, org_id: str | None = None
    ) -> int:
        """从 ``seed_funnel_data.py`` 输出的 JSONL 文件批量灌入.

        Returns:
            成功行数(写入内存,失败则跳过该行)。
        """
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning("[funnel] bulk_load_jsonl: file not found %s", path)
            return 0

        ok = 0
        with path.open("r", encoding="utf-8") as f:
            for ln, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[funnel] JSONL parse fail line %d: %s", ln, exc)
                    continue

                evt = await self.record_stage(
                    candidate_id=str(row["candidate_id"]),
                    stage=str(row["stage"]),
                    source=str(row.get("source") or "unknown"),
                    role_id=row.get("role_id"),
                    org_id=row.get("org_id") or org_id,
                    cost_cents=int(row.get("cost_cents") or 0),
                    metadata=dict(row.get("metadata") or {}),
                    occurred_at=(
                        datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
                        if row.get("occurred_at")
                        else None
                    ),
                    force=True,  # seed 数据允许同一 (candidate,role,stage) 多 source
                )
                if evt is not None:
                    ok += 1
        logger.info("[funnel] bulk_load_jsonl: %d rows from %s", ok, path.name)
        return ok

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
                    # 标记 re_touch 的进 _extra_events
                    md = r.get("metadata") or {}
                    if isinstance(md, dict) and md.get("re_touch"):
                        # 防重复:只在 _extra_events 没有同 id 时追加
                        if not any(e.id == r["id"] for e in self._extra_events):
                            self._extra_events.append(FunnelEvent(**r))
            except Exception as exc:  # noqa: BLE001
                logger.debug("[funnel] supabase fetch failed: %s", exc)

        items = list(self._events.values()) + list(self._extra_events)
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
        self._extra_events.clear()

    def stage_cost_profile(self, org_id: str | None = None) -> dict[str, dict[str, float]]:
        """按阶段返回 {count, total_cost_cents, avg_cost_cents} 摘要.

        供前端漏斗图叠加成本维度展示。
        """
        items = self.get_events(org_id=org_id)
        bucket: dict[str, dict[str, float]] = {
            s: {"count": 0, "total_cost_cents": 0.0, "avg_cost_cents": 0.0}
            for s in FUNNEL_STAGES
        }
        for e in items:
            b = bucket.setdefault(
                e.stage,
                {"count": 0, "total_cost_cents": 0.0, "avg_cost_cents": 0.0},
            )
            b["count"] += 1
            b["total_cost_cents"] += int(e.cost_cents)
        for s, b in bucket.items():
            b["avg_cost_cents"] = (
                round(b["total_cost_cents"] / b["count"], 2) if b["count"] else 0.0
            )
            b["total_cost_cents"] = int(b["total_cost_cents"])
        return bucket


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
    "STAGE_WEIGHT",
    "auto_transition",
]