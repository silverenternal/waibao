"""v5.0 shim — moved to services/employer/recruitment_funnel.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.recruitment_funnel directly.
"""
from __future__ import annotations

from .employer.recruitment_funnel import *  # noqa: F401,F403
