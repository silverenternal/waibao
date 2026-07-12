"""v5.0 shim — moved to services/jobseeker/video_processing.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.video_processing directly.
"""
from __future__ import annotations

from .jobseeker.video_processing import *  # noqa: F401,F403
