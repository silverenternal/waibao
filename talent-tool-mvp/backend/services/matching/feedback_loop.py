"""T903 — 自动权重校准 + 匹配质量 dashboard.

职责:
- daily_scheduler: 每天跑一次(可被调度器/CRON 触发)
- aggregate_outcomes(since_days): 聚合 outcomes -> precision/recall/F1/bucket 分布
- compute_weight_adjustment(current_weights, metrics): 计算调整建议
- apply_adjustment(weights): 写 settings 表 + audit log
- 人工覆盖:走 admin/weights API

Audit log 写入: settings_audit 表(若存在),失败则 fallback 到 logger.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger("recruittech.services.feedback_loop")


# ---------------------------------------------------------------------------
# 默认权重
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "skill": 0.40,
    "semantic": 0.30,
    "experience": 0.20,
    "culture": 0.10,
}

# 调整约束
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.80
MAX_DELTA_PER_RUN = 0.10  # 单次调整最多 ±0.10


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass
class Metrics:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    total: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    bucket_distribution: dict[str, dict[str, float]] = field(default_factory=dict)
    drift: float = 0.0  # vs 上一次运行

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeightAdjustment:
    new_weights: dict[str, float]
    delta: dict[str, float]
    reason: str
    confidence: float = 0.0  # 0~1,基于样本量

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Supabase 辅助
# ---------------------------------------------------------------------------


def _get_supabase(client: Optional[Client] = None) -> Client:
    if client is not None:
        return client
    from api.deps import get_supabase_admin

    return get_supabase_admin()


# ---------------------------------------------------------------------------
# 1. 聚合 outcomes
# ---------------------------------------------------------------------------


async def aggregate_outcomes(
    since_days: int = 7,
    supabase: Optional[Client] = None,
) -> Metrics:
    """聚合最近 since_days 的匹配结果,计算 precision/recall/F1/bucket.

    status 映射:
        placed        -> TP
        accepted      -> TP
        rejected_*    -> FP
        pending       -> TN
        withdrawn     -> FN (候选主动退出,看做漏报)
    """
    sb = _get_supabase(supabase)
    cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat()

    try:
        result = (
            sb.table("two_way_matches")
            .select("*")
            .gte("updated_at", cutoff)
            .execute()
        )
        matches = result.data or []
    except Exception as exc:
        logger.warning(f"aggregate_outcomes query failed: {exc}")
        matches = []

    tp = fp = fn = tn = 0
    for m in matches:
        status = (m.get("status") or "").lower()
        if status in ("placed", "accepted"):
            tp += 1
        elif status in ("rejected_by_candidate", "rejected_by_employer"):
            fp += 1
        elif status == "withdrawn":
            fn += 1
        else:
            tn += 1

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = (
        2 * precision * recall / max(1e-6, precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    bucket_distribution = _bucket_distribution(matches)
    drift = _compute_drift(sb, precision, recall, f1)

    metrics = Metrics(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        total=len(matches),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        bucket_distribution=bucket_distribution,
        drift=drift,
    )
    logger.info(f"aggregate_outcomes({since_days}d) -> {metrics.to_dict()}")
    return metrics


def _bucket_distribution(matches: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """按 harmonic_score 分桶,统计每桶的转化率."""
    if not matches:
        return {}
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

    out: dict[str, dict[str, float]] = {}
    for k, items in buckets.items():
        if not items:
            out[k] = {"count": 0, "placed_rate": 0.0, "rejected_rate": 0.0}
            continue
        placed = sum(1 for m in items if (m.get("status") or "").lower() == "placed")
        rejected = sum(
            1
            for m in items
            if (m.get("status") or "").lower() in ("rejected_by_candidate", "rejected_by_employer")
        )
        out[k] = {
            "count": len(items),
            "placed_rate": round(placed / len(items), 4),
            "rejected_rate": round(rejected / len(items), 4),
        }
    return out


def _compute_drift(
    sb: Client,
    precision: float,
    recall: float,
    f1: float,
) -> float:
    """计算相对上一次 metrics 的漂移."""
    try:
        resp = (
            sb.table("matching_quality_history")
            .select("precision, recall, f1")
            .order("recorded_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        prev = resp.data
        if not prev:
            return 0.0
        prev_f1 = float(prev.get("f1", 0.0))
        return round(f1 - prev_f1, 4)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# 2. 计算权重调整建议
# ---------------------------------------------------------------------------


async def compute_weight_adjustment(
    current_weights: dict[str, float],
    metrics: Metrics | dict[str, Any],
) -> WeightAdjustment:
    """基于 metrics 给出权重调整建议.

    策略:
        - precision < 0.6 且 high-bucket placed_rate 低:
            收紧 skill 权重 / 降低 culture 权重
        - recall < 0.5:
            放宽约束,提升 semantic 权重
        - f1 稳定 / drift 接近 0:
            不调整
    """
    if isinstance(metrics, Metrics):
        m = metrics
    else:
        m = Metrics(**{k: v for k, v in metrics.items() if k in Metrics.__dataclass_fields__})

    cw = {**DEFAULT_WEIGHTS, **(current_weights or {})}
    new = dict(cw)
    delta: dict[str, float] = {k: 0.0 for k in cw}

    reason_parts: list[str] = []
    precision = m.precision
    recall = m.recall
    f1 = m.f1
    drift = m.drift

    if m.total < 30:
        reason_parts.append(
            f"样本量过少(n={m.total}),保守不调整"
        )
        confidence = 0.2
    else:
        confidence = min(1.0, m.total / 200.0)

        # precision 过低 -> 提高 skill(更严)
        if precision < 0.6:
            shift = min(MAX_DELTA_PER_RUN, (0.6 - precision) * 0.3)
            new["skill"] = _clamp(new["skill"] + shift)
            delta["skill"] = round(shift, 4)
            reason_parts.append(
                f"precision={precision:.2f}<0.6,提升 skill 权重 +{shift:.2f} 以收紧硬性要求"
            )

        # recall 过低 -> 提高 semantic(更宽松)
        if recall < 0.5:
            shift = min(MAX_DELTA_PER_RUN, (0.5 - recall) * 0.3)
            new["semantic"] = _clamp(new["semantic"] + shift)
            delta["semantic"] = round(shift, 4)
            reason_parts.append(
                f"recall={recall:.2f}<0.5,提升 semantic 权重 +{shift:.2f} 扩大召回"
            )

        # high-bucket placed_rate 异常低
        high_bucket = m.bucket_distribution.get("0.8-1.0", {}) if isinstance(
            m.bucket_distribution, dict
        ) else {}
        if isinstance(high_bucket, dict) and high_bucket.get("count", 0) >= 5:
            pr = high_bucket.get("placed_rate", 0)
            if pr < 0.2:
                shift = min(0.05, MAX_DELTA_PER_RUN)
                new["experience"] = _clamp(new["experience"] + shift)
                delta["experience"] = round(shift, 4)
                reason_parts.append(
                    f"高分桶(harmonic>0.8)转化率仅 {pr:.2f},提升 experience 权重 +{shift:.2f}"
                )

    # 归一化(权重和必须为 1)
    total = sum(new.values())
    if total > 0:
        new = {k: round(v / total, 4) for k, v in new.items()}

    if not reason_parts:
        reason_parts.append(
            f"F1={f1:.2f} drift={drift:+.3f},表现稳定,无需调整"
        )

    return WeightAdjustment(
        new_weights=new,
        delta=delta,
        reason=" | ".join(reason_parts),
        confidence=round(confidence, 3),
    )


def _clamp(v: float) -> float:
    return max(MIN_WEIGHT, min(MAX_WEIGHT, v))


# ---------------------------------------------------------------------------
# 3. 应用权重 + Audit log
# ---------------------------------------------------------------------------


async def apply_adjustment(
    weights: dict[str, float],
    *,
    actor: str = "system",
    reason: str = "",
    supabase: Optional[Client] = None,
    require_approval: bool = True,
) -> dict[str, Any]:
    """把新权重写入 settings 表 + 写 audit log.

    require_approval=True 时,默认落库 status=pending,等 admin PATCH 激活.
    """
    sb = _get_supabase(supabase)
    ts = datetime.utcnow().isoformat()
    normalized = _normalize(weights)

    # 写 settings 表
    settings_record = {
        "key": "matching_weights",
        "value": json.dumps(normalized),
        "actor": actor,
        "reason": reason,
        "status": "pending" if require_approval else "active",
        "updated_at": ts,
    }
    try:
        sb.table("settings").upsert(
            settings_record, on_conflict="key"
        ).execute()
    except Exception as exc:
        logger.warning(f"settings upsert failed: {exc}")

    # 写 audit log
    audit = {
        "actor": actor,
        "action": "weight_adjustment",
        "weights": normalized,
        "reason": reason,
        "require_approval": require_approval,
        "created_at": ts,
    }
    try:
        sb.table("settings_audit").insert(audit).execute()
    except Exception as exc:
        logger.debug(f"settings_audit insert skipped: {exc}")

    return {
        "weights": normalized,
        "status": settings_record["status"],
        "actor": actor,
        "applied_at": ts,
        "reason": reason,
    }


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """归一化权重,并裁剪到合法范围."""
    cleaned: dict[str, float] = {}
    for k in DEFAULT_WEIGHTS:
        v = float(weights.get(k, DEFAULT_WEIGHTS[k]))
        cleaned[k] = _clamp(v)
    total = sum(cleaned.values())
    if total > 0:
        cleaned = {k: round(v / total, 4) for k, v in cleaned.items()}
    return cleaned


async def get_current_weights(supabase: Optional[Client] = None) -> dict[str, float]:
    """从 settings 表读取当前权重."""
    sb = _get_supabase(supabase)
    try:
        resp = (
            sb.table("settings")
            .select("value")
            .eq("key", "matching_weights")
            .maybe_single()
            .execute()
        )
        if resp.data and resp.data.get("value"):
            data = resp.data["value"]
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                return {**DEFAULT_WEIGHTS, **data}
    except Exception as exc:
        logger.debug(f"get_current_weights fallback: {exc}")
    return dict(DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------------
# 4. daily scheduler
# ---------------------------------------------------------------------------


async def daily_scheduler(
    supabase: Optional[Client] = None,
    *,
    since_days: int = 7,
    force: bool = False,
) -> dict[str, Any]:
    """每日跑一次:aggregate -> compute -> persist recommendation.

    force=True 用于测试 / 手动触发.
    """
    sb = _get_supabase(supabase)
    metrics = await aggregate_outcomes(since_days=since_days, supabase=sb)

    # 持久化历史
    try:
        sb.table("matching_quality_history").insert(
            {
                "recorded_at": datetime.utcnow().isoformat(),
                **metrics.to_dict(),
            }
        ).execute()
    except Exception as exc:
        logger.debug(f"history insert skipped: {exc}")

    current = await get_current_weights(sb)
    adjustment = await compute_weight_adjustment(current, metrics)

    # 应用建议(需审批)
    result = await apply_adjustment(
        adjustment.new_weights,
        actor="scheduler",
        reason=adjustment.reason,
        supabase=sb,
        require_approval=True,
    )

    return {
        "metrics": metrics.to_dict(),
        "current_weights": current,
        "adjustment": adjustment.to_dict(),
        "result": result,
        "force": force,
    }


# ---------------------------------------------------------------------------
# 5. CLI 入口(供 CRON 调用)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m services.feedback_loop [--since-days N] [--force]"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = asyncio.run(
        daily_scheduler(since_days=args.since_days, force=args.force)
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()