"""v5.0 shim — moved to services/matching/calibration.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.matching.calibration directly.
"""
from __future__ import annotations

from .matching.calibration import *  # noqa: F401,F403
