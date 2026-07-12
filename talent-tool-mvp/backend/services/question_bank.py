"""v5.0 shim — moved to services/jobseeker/question_bank.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.question_bank directly.
"""
from __future__ import annotations

from .jobseeker.question_bank import *  # noqa: F401,F403
