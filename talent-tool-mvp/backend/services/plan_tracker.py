"""v5.0 shim — moved to services/jobseeker/plan_tracker.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.plan_tracker directly.
"""
from __future__ import annotations

from .jobseeker.plan_tracker import *  # noqa: F401,F403
