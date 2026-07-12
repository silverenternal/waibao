"""v5.0 shim — moved to services/jobseeker/profile_extractor.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.profile_extractor directly.
"""
from __future__ import annotations

from .jobseeker.profile_extractor import *  # noqa: F401,F403
