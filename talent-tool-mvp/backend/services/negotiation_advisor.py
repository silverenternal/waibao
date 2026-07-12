"""v5.0 shim — moved to services/jobseeker/negotiation_advisor.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.negotiation_advisor directly.
"""
from __future__ import annotations

from .jobseeker.negotiation_advisor import *  # noqa: F401,F403
