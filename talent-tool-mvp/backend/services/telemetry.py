"""v5.0 shim — moved to services/observability/telemetry.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.observability.telemetry directly.
"""
from __future__ import annotations

from .observability.telemetry import *  # noqa: F401,F403
