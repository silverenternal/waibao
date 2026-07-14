"""Predictive Analytics (T2803 / v10.0 T5002 split package).

The single 846-line module was split in v10.0 T5002 into three cohesive
submodules while keeping the public surface 100 % backward compatible:

    model        — AttritionModel + HireSuccessModel (LightGBM) + loaders
    forecast     — ProphetModel time-series forecasting
    calibration  — ``train_all_synthetic`` / ``celery_beat_task`` auto-train

All logic lives in :mod:`._core`; the submodules re-export the relevant slice.
``from services.platform.predictive import AttritionModel, …`` and friends keep
working unchanged.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    AttritionFeatures,
    AttritionModel,
    AttritionRisk,
    ForecastPoint,
    ForecastResult,
    HireSuccessModel,
    HireSuccessScore,
    ProphetModel,
    celery_beat_task,
    get_attrition_model,
    get_hire_success_model,
    train_all_synthetic,
)
from .calibration import *  # noqa: F401,F403
from .forecast import *  # noqa: F401,F403
from .model import *  # noqa: F401,F403

__all__ = [
    "AttritionFeatures",
    "AttritionModel",
    "AttritionRisk",
    "ForecastPoint",
    "ForecastResult",
    "HireSuccessModel",
    "HireSuccessScore",
    "ProphetModel",
    "celery_beat_task",
    "get_attrition_model",
    "get_hire_success_model",
    "train_all_synthetic",
]
