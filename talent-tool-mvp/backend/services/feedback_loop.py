"""v5.0 shim — moved to services/matching/feedback_loop.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.matching.feedback_loop directly.
"""
from __future__ import annotations

from .matching.feedback_loop import *  # noqa: F401,F403
