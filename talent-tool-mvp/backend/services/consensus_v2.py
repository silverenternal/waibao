"""T3708 - 共识度算法: 3 级 + 冲突维度 + 折中方案."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("recruittech.services.consensus_v2")

STRONG_THRESHOLD = 0.8
WEAK_THRESHOLD = 0.5


@dataclass
class DimensionScore:
    dimension: str
    score: float  # 0-1
    variance: float = 0.0
    conflicting: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class ConsensusReport:
    overall: float
    level: str  # strong / weak / fuzzy
    dimensions: List[DimensionScore] = field(default_factory=list)
    conflicting_dimensions: List[str] = field(default_factory=list)
    compromise_plan: Optional[Dict[str, Any]] = None
    can_decide: bool = True

    def to_dict(self):
        d = asdict(self)
        d["dimensions"] = [asdict(d) for d in self.dimensions]
        return d


def _variance(values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def aggregate_dimension(ratings: List[float]) -> Tuple[float, bool]:
    if not ratings:
        return 0.0, False
    mean = sum(ratings) / len(ratings)
    var = _variance(ratings)
    conflicting = var > 0.08  # 方差大 = 严重不一致
    return mean, conflicting


def level_for(score: float) -> str:
    if score >= STRONG_THRESHOLD:
        return "strong"
    if score >= WEAK_THRESHOLD:
        return "weak"
    return "fuzzy"


def build_compromise(dimension: str, ratings: List[float], notes: List[str]) -> Dict[str, Any]:
    """冲突维度时给出 AI 折中方案."""
    if dimension == "salary":
        return {
            "title": f"{dimension} 折中",
            "option_a": f"按高分={max(ratings):.2f}",
            "option_b": f"按低分={min(ratings):.2f}",
            "suggested": "考虑以市场中位数为锚,叠加签字奖 / 期权平衡",
            "notes": notes,
        }
    if dimension == "timeline":
        return {
            "title": f"{dimension} 折中",
            "option_a": "急招(2周内)",
            "option_b": "理想(1个月内)",
            "suggested": "分阶段并行:先发 JD 启动面试,面试通过后预留 1 周 onboarding",
            "notes": notes,
        }
    if dimension == "level":
        return {
            "title": f"{dimension} 折中",
            "suggested": "先按 P6 offer,3 个月看表现再谈 P7",
            "notes": notes,
        }
    return {
        "title": f"{dimension} 折中",
        "suggested": "将分歧点列出,组织 30 分钟集中决策会",
        "notes": notes,
    }


def compute_consensus(dimension_ratings: Dict[str, List[float]],
                      notes_by_dim: Optional[Dict[str, List[str]]] = None) -> ConsensusReport:
    notes_by_dim = notes_by_dim or {}
    dims: List[DimensionScore] = []
    conflicting: List[str] = []

    for name, ratings in dimension_ratings.items():
        score, conf = aggregate_dimension(ratings)
        if conf:
            conflicting.append(name)
        dims.append(DimensionScore(
            dimension=name,
            score=round(score, 3),
            variance=round(_variance(ratings), 4),
            conflicting=conf,
            notes=notes_by_dim.get(name, []),
        ))

    overall = (sum(d.score for d in dims) / len(dims)) if dims else 0.0
    lvl = level_for(overall)

    plan = None
    if conflicting and lvl != "strong":
        # 选第一个冲突维度给出方案
        first = conflicting[0]
        ratings = dimension_ratings[first]
        plan = build_compromise(first, ratings, notes_by_dim.get(first, []))

    can_decide = lvl == "strong" and not conflicting

    return ConsensusReport(
        overall=round(overall, 3),
        level=lvl,
        dimensions=dims,
        conflicting_dimensions=conflicting,
        compromise_plan=plan,
        can_decide=can_decide,
    )
