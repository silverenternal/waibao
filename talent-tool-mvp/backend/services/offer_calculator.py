"""v5.0 shim — moved to services/jobseeker/offer_calculator.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.offer_calculator directly.
"""
from __future__ import annotations

from .jobseeker.offer_calculator import *  # noqa: F401,F403
