"""v5.0 shim — moved to services/jobseeker/learning_resources.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.learning_resources directly.
"""
from __future__ import annotations

from .jobseeker.learning_resources import *  # noqa: F401,F403
from .jobseeker.learning_resources import _fallback_for_skill  # noqa: F401  — underscored names not exported via star
