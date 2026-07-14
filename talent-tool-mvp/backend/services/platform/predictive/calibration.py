"""Predictive — Calibration / auto-train slice (v10.0 T5002 split).

Covers the synthetic-data training entrypoints and the celery-beat auto-train
hook: ``train_all_synthetic`` and ``celery_beat_task``.  Logic lives in
:mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    celery_beat_task,
    train_all_synthetic,
)

__all__ = [
    "train_all_synthetic",
    "celery_beat_task",
]
