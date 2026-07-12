"""v5.0 services/matching/ public API."""
from __future__ import annotations

from .calibration import compute_metrics, compute_bucket_distribution, compute_segment_metrics, suggest_weight_adjustment  # noqa: F401,F403
from .feedback_loop import MIN_WEIGHT, MAX_WEIGHT, MAX_DELTA_PER_RUN, Metrics, WeightAdjustment, aggregate_outcomes, compute_weight_adjustment, apply_adjustment, get_current_weights, daily_scheduler, main  # noqa: F401,F403
from .global_search import SearchResult, ScoredCandidate, rank_candidates, score_one, ts_query_sql, trigram_sql, semantic_sql, build_snippet  # noqa: F401,F403

__all__: list[str] = [
    "compute_metrics",
    "compute_bucket_distribution",
    "compute_segment_metrics",
    "suggest_weight_adjustment",
    "MIN_WEIGHT",
    "MAX_WEIGHT",
    "MAX_DELTA_PER_RUN",
    "Metrics",
    "WeightAdjustment",
    "aggregate_outcomes",
    "compute_weight_adjustment",
    "apply_adjustment",
    "get_current_weights",
    "daily_scheduler",
    "main",
    "SearchResult",
    "ScoredCandidate",
    "rank_candidates",
    "score_one",
    "ts_query_sql",
    "trigram_sql",
    "semantic_sql",
    "build_snippet",
]
