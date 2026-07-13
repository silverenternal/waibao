"""T3710 - 双向匹配命中率 + HR 反馈循环."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("recruittech.services.matching_feedback")

FUNNEL_STAGES = ["recommended", "contacted", "interview", "offer", "hired"]


@dataclass
class HitRateReport:
    by_role: Dict[str, Dict[str, int]] = field(default_factory=dict)
    totals: Dict[str, int] = field(default_factory=dict)
    conversion_rates: Dict[str, float] = field(default_factory=dict)
    weak_stages: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def compute_hit_rate(
    events: Iterable[Dict[str, Any]],
    group_by_role: bool = True,
) -> HitRateReport:
    """events: [{role_id, candidate_id, stage}]"""
    by_role: Dict[str, Dict[str, int]] = defaultdict(lambda: {s: 0 for s in FUNNEL_STAGES})
    totals = {s: 0 for s in FUNNEL_STAGES}

    for e in events:
        if not e or not e.get("stage") or e["stage"] not in FUNNEL_STAGES:
            continue
        stage = e["stage"]
        if group_by_role and e.get("role_id"):
            by_role[e["role_id"]][stage] += 1
        totals[stage] += 1

    # 转化率
    rates: Dict[str, float] = {}
    weak: List[str] = []
    for prev, curr in zip(FUNNEL_STAGES, FUNNEL_STAGES[1:]):
        prev_n = totals[prev] or 0
        curr_n = totals[curr] or 0
        rate = round(curr_n / prev_n, 3) if prev_n else 0.0
        rates[f"{prev}->{curr}"] = rate
        if rate and rate < 0.15:
            weak.append(f"{prev}->{curr}")

    insights: List[str] = []
    if weak:
        insights.append("弱环节: " + ", ".join(weak) + " 建议强化曝光 / 面试安排")
    if rates.get("offer->hired", 0) and rates["offer->hired"] > 0.8:
        insights.append("offer→hired 转化健康")

    return HitRateReport(
        by_role=dict(by_role),
        totals=totals,
        conversion_rates=rates,
        weak_stages=weak,
        insights=insights,
    )


# --------- HR 反馈循环 ---------

@dataclass
class FeedbackEntry:
    candidate_id: str
    role_id: str
    label: str  # suitable / unsuitable
    rating: int  # 1-5
    note: str = ""
    feedback_by: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def aggregate_feedback(entries: List[FeedbackEntry]) -> Dict[str, Any]:
    by_label = defaultdict(int)
    rating_sum = 0
    rating_count = 0
    by_role: Dict[str, List[int]] = defaultdict(list)
    for e in entries:
        by_label[e.label] += 1
        if e.rating:
            rating_sum += e.rating
            rating_count += 1
            by_role[e.role_id].append(e.rating)
    avg_rating = round(rating_sum / rating_count, 2) if rating_count else 0

    # 模型权重调整建议
    weight_adjustments: Dict[str, float] = {}
    if by_label.get("unsuitable", 0) > by_label.get("suitable", 0):
        weight_adjustments["skill_match"] = 0.05
        weight_adjustments["experience"] = -0.05
    return {
        "totals": dict(by_label),
        "average_rating": avg_rating,
        "by_role_avg_rating": {r: round(sum(v) / len(v), 2) for r, v in by_role.items() if v},
        "weight_adjustments": weight_adjustments,
    }


def collect_feedback(
    candidate_id: str, role_id: str,
    label: str, rating: int,
    note: str = "", feedback_by: Optional[str] = None,
    now_iso: Optional[str] = None,
) -> FeedbackEntry:
    if label not in {"suitable", "unsuitable"}:
        raise ValueError("label must be suitable / unsuitable")
    if not 1 <= rating <= 5:
        raise ValueError("rating must be 1-5")
    return FeedbackEntry(
        candidate_id=candidate_id,
        role_id=role_id,
        label=label,
        rating=rating,
        note=note,
        feedback_by=feedback_by,
        created_at=now_iso,
    )
