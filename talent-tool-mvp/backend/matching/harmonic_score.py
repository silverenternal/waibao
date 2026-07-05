"""调和/几何/算术均值评分工具.

不同业务场景选用不同均值:
- harmonic: 强调短板(双方都要满意才高分) - 双向匹配
- geometric: 弱化短板但保持单调性
- arithmetic: 简单平均
"""
from __future__ import annotations


def harmonic_mean(a: float, b: float, eps: float = 1e-6) -> float:
    return 2 * a * b / (a + b + eps)


def geometric_mean(a: float, b: float, eps: float = 1e-6) -> float:
    import math
    return math.sqrt(max(0.0, a) * max(0.0, b))


def arithmetic_mean(a: float, b: float) -> float:
    return (a + b) / 2


def weighted_score(parts: dict[str, float], weights: dict[str, float]) -> float:
    """加权平均, parts 和 weights 同 key."""
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    return sum(parts.get(k, 0) * weights[k] for k in weights) / total_weight


def confidence_adjusted(score: float, confidence: float) -> float:
    """置信度调节: 高置信度得分按原值,低置信度向 0.5 收缩."""
    confidence = max(0.0, min(1.0, confidence))
    return 0.5 + (score - 0.5) * confidence