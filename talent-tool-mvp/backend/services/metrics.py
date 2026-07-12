"""v5.0 shim — moved to services/observability/metrics.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.observability.metrics directly.
"""
from __future__ import annotations

from .observability.metrics import *  # noqa: F401,F403
