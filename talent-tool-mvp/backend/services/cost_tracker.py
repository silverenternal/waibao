"""Cost Tracker 服务 — T806.

作用:
- 聚合 per tenant / provider / model / 日期 的 LLM 成本
- 异步批量持久化到 Supabase (供 cost dashboard 直接查询)
- 内存 hot path (providers.base.CostTracker) 不阻塞业务
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger("recruittech.services.cost_tracker")

# 批量刷新间隔 (秒) — 保证 cost dashboard latency < 1 分钟
FLUSH_INTERVAL_SECONDS = 30
BATCH_MAX = 200


class CostTrackerService:
    """单实例成本聚合 + 周期持久化到 Supabase."""

    def __init__(self, supabase_client: Any | None = None):
        self.supabase = supabase_client
        self._buffer: list[dict[str, Any]] = []
        self._aggregate: dict[tuple[str, str, str, str], float] = defaultdict(float)
        # key = (tenant, provider, model, date_str)
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()
        # persistence cb (设置时用,如主成本追踪)
        self._supabase_writer = self._default_supabase_writer if supabase_client else None

    def set_supabase(self, client: Any) -> None:
        self.supabase = client
        self._supabase_writer = self._default_supabase_writer

    # ---- buffer ingest -----------------------------------------------------
    def ingest(self, event: dict[str, Any]) -> None:
        """从 providers.base.CostTracker 注入单条成本事件 (写失败容忍)."""
        try:
            tenant = str(event.get("tenant") or "default")
            provider = str(event.get("provider") or "unknown")
            model = str(event.get("model") or "unknown")
            cost = float(event.get("cost_usd") or 0.0)
            occurred_at = event.get("occurred_at") or datetime.now(timezone.utc).isoformat()
            date_str = occurred_at[:10]
            with self._lock:
                self._aggregate[(tenant, provider, model, date_str)] += cost
                self._buffer.append(
                    {
                        "tenant_id": tenant,
                        "provider": provider,
                        "model": model,
                        "cost_usd": cost,
                        "occurred_at": occurred_at,
                    }
                )
            self._maybe_flush()
        except Exception:
            logger.exception("cost_tracker_service.ingest_failed")

    def flush(self) -> bool:
        """强制持久化 buffer 到 Supabase;返回是否成功."""
        with self._lock:
            batch = self._buffer[:BATCH_MAX]
            self._buffer = self._buffer[BATCH_MAX:]
            aggregates = dict(self._aggregate)
        if not batch and not aggregates:
            self._last_flush = time.monotonic()
            return True
        try:
            if self._supabase_writer is not None:
                self._supabase_writer(batch, aggregates)
            self._last_flush = time.monotonic()
            return True
        except Exception:
            logger.exception("cost_tracker_service.flush_failed")
            # 回滚 buffer 以便下次重试
            with self._lock:
                self._buffer = batch + self._buffer
            return False

    def _maybe_flush(self) -> None:
        if time.monotonic() - self._last_flush >= FLUSH_INTERVAL_SECONDS:
            self.flush()

    def _default_supabase_writer(
        self,
        batch: list[dict[str, Any]],
        aggregates: dict[tuple[str, str, str, str], float],
    ) -> None:
        """默认 Supabase writer: 写入 llm_cost_events 表.

        表结构由 supabase/migrations/017_llm_cost.sql 定义.
        """
        if not self.supabase:
            return
        try:
            rows = []
            # 写明细 (供 by-day dashboard)
            if batch:
                for evt in batch:
                    rows.append(
                        {
                            "tenant_id": evt["tenant_id"],
                            "provider": evt["provider"],
                            "model": evt["model"],
                            "cost_usd": float(evt["cost_usd"]),
                            "occurred_at": evt["occurred_at"],
                        }
                    )
                try:
                    self.supabase.table("llm_cost_events").insert(rows).execute()
                except Exception as exc:
                    # 兼容老部署可能还没有表 — 仅记日志
                    logger.info("cost_tracker.supabase.insert_skipped reason=%s", exc)
            # 写聚合 (按天 bucket)
            agg_rows = [
                {
                    "tenant_id": t,
                    "provider": p,
                    "model": m,
                    "cost_usd": round(v, 6),
                    "occurred_on": d,
                }
                for (t, p, m, d), v in aggregates.items()
            ]
            if agg_rows:
                try:
                    self.supabase.table("llm_cost_daily").upsert(
                        agg_rows, on_conflict="tenant_id,provider,model,occurred_on"
                    ).execute()
                except Exception as exc:
                    logger.info("cost_tracker.supabase.upsert_skipped reason=%s", exc)
        except Exception:
            logger.exception("cost_tracker_service.writer_failed")

    # ---- query -------------------------------------------------------------
    def query_summary(
        self,
        tenant_id: Optional[str] = None,
        since_days: int = 30,
    ) -> dict[str, Any]:
        """查询汇总: total / per-provider / per-day / cache-stats."""
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
        if self.supabase:
            try:
                q = self.supabase.table("llm_cost_daily").select(
                    "tenant_id,provider,model,cost_usd,occurred_on"
                )
                if tenant_id:
                    q = q.eq("tenant_id", tenant_id)
                res = q.gte("occurred_on", since).execute()
                rows = res.data or []
            except Exception:
                rows = []
        else:
            rows = []
        # 内存聚合兜底
        if not rows:
            with self._lock:
                rows = [
                    {
                        "tenant_id": t,
                        "provider": p,
                        "model": m,
                        "cost_usd": v,
                        "occurred_on": d,
                    }
                    for (t, p, m, d), v in self._aggregate.items()
                    if d >= since and (not tenant_id or t == tenant_id)
                ]
        return _shape(rows)

    def query_by_provider(
        self,
        tenant_id: Optional[str] = None,
        since_days: int = 30,
    ) -> list[dict[str, Any]]:
        summary = self.query_summary(tenant_id, since_days)
        return summary["by_provider"]

    def query_by_tenant(self, since_days: int = 30) -> list[dict[str, Any]]:
        summary = self.query_summary(tenant_id=None, since_days=since_days)
        return summary["by_tenant"]


def _shape(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_cost = 0.0
    by_provider: dict[str, float] = defaultdict(float)
    by_tenant: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    by_provider_tenant: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        cost = float(r.get("cost_usd") or 0.0)
        provider = str(r.get("provider") or "unknown")
        tenant = str(r.get("tenant_id") or "default")
        model = str(r.get("model") or "unknown")
        day = str(r.get("occurred_on") or "")[:10]
        total_cost += cost
        by_provider[provider] += cost
        by_tenant[tenant] += cost
        by_model[f"{provider}/{model}"] += cost
        if day:
            by_day[day] += cost
        by_provider_tenant[provider][tenant] += cost
    return {
        "total_cost_usd": round(total_cost, 6),
        "by_provider": [
            {"provider": p, "cost_usd": round(v, 6)} for p, v in sorted(by_provider.items(), key=lambda x: -x[1])
        ],
        "by_tenant": [
            {"tenant_id": t, "cost_usd": round(v, 6)} for t, v in sorted(by_tenant.items(), key=lambda x: -x[1])
        ],
        "by_model": [
            {"model": m, "cost_usd": round(v, 6)} for m, v in sorted(by_model.items(), key=lambda x: -x[1])
        ],
        "daily_trend": [
            {"date": d, "cost_usd": round(v, 6)} for d, v in sorted(by_day.items())
        ],
        "provider_tenant_matrix": [
            {
                "provider": p,
                "tenants": [{"tenant_id": t, "cost_usd": round(v, 6)} for t, v in tenants.items()],
            }
            for p, tenants in by_provider_tenant.items()
        ],
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_service: CostTrackerService | None = None


def get_cost_service(supabase_client: Any | None = None) -> CostTrackerService:
    global _service
    if _service is None:
        _service = CostTrackerService(supabase_client=supabase_client)
    elif supabase_client is not None and _service.supabase is None:
        _service.set_supabase(supabase_client)
    return _service


def reset_cost_service() -> None:
    global _service
    _service = None
