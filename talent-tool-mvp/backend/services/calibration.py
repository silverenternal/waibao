"""calibration - 匹配质量校准 (T903 升级版).

- 基础 precision/recall/F1
- 按 bucket (harmonic_score 分桶) 计算转化率
- 按 segment (role_seniority / candidate_seniority) 计算
- 暴露给 dashboard 使用
"""
from __future__ import annotations

import logging
from typing import Optional

from supabase import Client

logger = logging.getLogger("recruittech.services.calibration")


# ---------------------------------------------------------------------------
# 基础指标
# ---------------------------------------------------------------------------


async def compute_metrics(supabase: Optional[Client] = None, since_days: int = 90) -> dict:
    """计算匹配模型指标 (基础 + 桶分布)."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    matches = supabase.table("two_way_matches").select("*").execute().data or []

    tp = sum(1 for m in matches if m.get("status") == "placed")
    fp = sum(
        1
        for m in matches
        if m.get("status") in ("rejected_by_candidate", "rejected_by_employer")
    )
    fn = 0
    tn = sum(1 for m in matches if m.get("status") == "pending")

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-6, precision + recall)

    return {
        "total": len(matches),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "bucket_distribution": compute_bucket_distribution(matches),
        "segment_metrics": await compute_segment_metrics(matches, supabase),
    }


# ---------------------------------------------------------------------------
# 桶分布
# ---------------------------------------------------------------------------


def compute_bucket_distribution(matches: list[dict]) -> dict[str, dict]:
    """按 harmonic_score 分桶.

    Bucket: 0.0-0.4 / 0.4-0.6 / 0.6-0.8 / 0.8-1.0
    """
    buckets = {"0.0-0.4": [], "0.4-0.6": [], "0.6-0.8": [], "0.8-1.0": []}
    for m in matches:
        score = float(m.get("harmonic_score", 0.0))
        if score < 0.4:
            key = "0.0-0.4"
        elif score < 0.6:
            key = "0.4-0.6"
        elif score < 0.8:
            key = "0.6-0.8"
        else:
            key = "0.8-1.0"
        buckets[key].append(m)

    out: dict[str, dict] = {}
    for k, items in buckets.items():
        if not items:
            out[k] = {
                "count": 0,
                "placed_rate": 0.0,
                "rejected_rate": 0.0,
                "pending_rate": 0.0,
                "avg_harmonic": 0.0,
            }
            continue
        n = len(items)
        placed = sum(1 for m in items if m.get("status") == "placed")
        rejected = sum(
            1
            for m in items
            if m.get("status") in ("rejected_by_candidate", "rejected_by_employer")
        )
        pending = sum(1 for m in items if m.get("status") == "pending")
        avg_h = sum(float(m.get("harmonic_score", 0.0)) for m in items) / n
        out[k] = {
            "count": n,
            "placed_rate": round(placed / n, 4),
            "rejected_rate": round(rejected / n, 4),
            "pending_rate": round(pending / n, 4),
            "avg_harmonic": round(avg_h, 4),
        }
    return out


# ---------------------------------------------------------------------------
# Segment 维度 (按 seniority)
# ---------------------------------------------------------------------------


async def compute_segment_metrics(
    matches: list[dict],
    supabase: Client,
) -> dict[str, dict]:
    """按 candidate_seniority + role_seniority 切片计算 precision/recall."""
    # 加载 candidate + role 摘要
    candidate_ids = list({m.get("candidate_id") for m in matches if m.get("candidate_id")})
    role_ids = list({m.get("role_id") for m in matches if m.get("role_id")})

    candidate_seniority: dict[str, str] = {}
    role_seniority: dict[str, str] = {}

    try:
        if candidate_ids:
            cand_resp = (
                supabase.table("candidates")
                .select("id, seniority")
                .in_("id", candidate_ids)
                .execute()
            )
            for c in cand_resp.data or []:
                candidate_seniority[c["id"]] = c.get("seniority") or "unknown"
    except Exception as exc:
        logger.debug(f"cand fetch failed: {exc}")

    try:
        if role_ids:
            role_resp = (
                supabase.table("roles")
                .select("id, seniority")
                .in_("id", role_ids)
                .execute()
            )
            for r in role_resp.data or []:
                role_seniority[r["id"]] = r.get("seniority") or "unknown"
    except Exception as exc:
        logger.debug(f"role fetch failed: {exc}")

    # 按 role_seniority 分组
    buckets: dict[str, list[dict]] = {}
    for m in matches:
        rs = role_seniority.get(m.get("role_id", ""), "unknown")
        buckets.setdefault(rs, []).append(m)

    out: dict[str, dict] = {}
    for segment, items in buckets.items():
        tp = sum(1 for m in items if m.get("status") == "placed")
        fp = sum(
            1
            for m in items
            if m.get("status") in ("rejected_by_candidate", "rejected_by_employer")
        )
        fn = 0
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-6, precision + recall)
        out[segment] = {
            "count": len(items),
            "tp": tp,
            "fp": fp,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return out


# ---------------------------------------------------------------------------
# 老接口:suggest_weight_adjustment (兼容 v2.0 调用方)
# ---------------------------------------------------------------------------


def suggest_weight_adjustment(metrics: dict) -> dict:
    """基于指标建议权重调整 (轻量建议,生产由 services.feedback_loop.compute_weight_adjustment 接管)."""
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