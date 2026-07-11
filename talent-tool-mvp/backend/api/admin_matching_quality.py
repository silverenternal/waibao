"""T903 — Admin: 匹配质量 dashboard API.

GET /api/admin/matching-quality?since_days=7
  -> {
      summary: {precision, recall, f1, drift, total},
      bucket_distribution: {...},
      segment_metrics: {...},
      history: [{recorded_at, precision, recall, f1}, ...]
    }
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.calibration import compute_metrics

logger = logging.getLogger("recruittech.api.admin_matching_quality")
router = APIRouter()


@router.get("")
async def get_matching_quality(
    since_days: int = Query(default=7, ge=1, le=365),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    metrics = await compute_metrics(supabase=supabase, since_days=since_days)

    summary = {
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "total": metrics["total"],
        "tp": metrics["tp"],
        "fp": metrics["fp"],
        "fn": metrics["fn"],
        "tn": metrics["tn"],
        "drift": 0.0,
    }

    # drift = 最近 vs 上一次
    try:
        history_resp = (
            supabase.table("matching_quality_history")
            .select("recorded_at, precision, recall, f1")
            .order("recorded_at", desc=True)
            .limit(2)
            .execute()
        )
        rows = history_resp.data or []
        if len(rows) >= 2:
            summary["drift"] = round(rows[0]["f1"] - rows[1]["f1"], 4)
    except Exception as exc:
        logger.debug(f"drift fetch failed: {exc}")

    history: list[dict[str, Any]] = []
    try:
        resp = (
            supabase.table("matching_quality_history")
            .select("recorded_at, precision, recall, f1, total")
            .order("recorded_at", desc=True)
            .limit(60)
            .execute()
        )
        for row in resp.data or []:
            history.append(
                {
                    "recorded_at": row.get("recorded_at"),
                    "precision": row.get("precision"),
                    "recall": row.get("recall"),
                    "f1": row.get("f1"),
                    "total": row.get("total"),
                }
            )
        history.reverse()
    except Exception as exc:
        logger.debug(f"history fetch failed: {exc}")

    return {
        "summary": summary,
        "bucket_distribution": metrics["bucket_distribution"],
        "segment_metrics": metrics["segment_metrics"],
        "history": history,
        "since_days": since_days,
        "generated_at": datetime.utcnow().isoformat(),
    }