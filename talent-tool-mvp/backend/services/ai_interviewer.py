"""v5.0 shim — moved to services/jobseeker/ai_interviewer.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.ai_interviewer directly.
"""
from __future__ import annotations

from .jobseeker.ai_interviewer import *  # noqa: F401,F403
