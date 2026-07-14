"""Predictive — Forecast slice (v10.0 T5002 split).

Covers Prophet time-series forecasting: ``ProphetModel``, ``ForecastPoint``
and ``ForecastResult``.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    ForecastPoint,
    ForecastResult,
    ProphetModel,
)

__all__ = [
    "ForecastPoint",
    "ForecastResult",
    "ProphetModel",
]
