"""calibration - 匹配质量校准.

根据 outcomes 调整评分模型:
- 计算 precision/recall/F1
- 输出校准建议(调整 harmonic 权重)
"""
from __future__ import annotations

import logging
from typing import Optional

from supabase import Client

logger = logging.getLogger("recruittech.services.calibration")


async def compute_metrics(supabase: Optional[Client] = None, since_days: int = 90) -> dict:
    """计算匹配模型指标."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    matches = supabase.table("two_way_matches").select("*").execute().data or []

    tp = sum(1 for m in matches if m.get("status") == "placed")
    fp = sum(1 for m in matches if m.get("status") in ("rejected_by_candidate", "rejected_by_employer"))
    fn = 0  # 漏报,需要业务埋点补充
    tn = sum(1 for m in matches if m.get("status") == "pending")

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-6, precision + recall)

    return {
        "total": len(matches),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def suggest_weight_adjustment(metrics: dict) -> dict:
    """基于指标建议权重调整."""
    if metrics.get("precision", 0) < 0.6:
        return {
            "action": "tighten_hard_requirements",
            "rationale": "precision<0.6,硬性要求门槛需要提高",
        }
    if metrics.get("recall", 0) < 0.5:
        return {
            "action": "loosen_constraints",
            "rationale": "recall<0.5,放宽部分约束以扩大召回",
        }
    return {"action": "no_change", "rationale": "当前表现稳定"}