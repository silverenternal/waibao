"""Predictive — Model slice (v10.0 T5002 split).

Covers the two LightGBM classification models and their lazy singletons:
``AttritionModel``, ``HireSuccessModel``, ``get_attrition_model`` and
``get_hire_success_model``.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    AttritionFeatures,
    AttritionModel,
    AttritionRisk,
    HireSuccessModel,
    HireSuccessScore,
    get_attrition_model,
    get_hire_success_model,
)

__all__ = [
    "AttritionFeatures",
    "AttritionModel",
    "AttritionRisk",
    "HireSuccessModel",
    "HireSuccessScore",
    "get_attrition_model",
    "get_hire_success_model",
]
