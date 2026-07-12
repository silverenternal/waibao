"""v5.0 shim — moved to services/employer/ats_sync.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.ats_sync directly.
"""
from __future__ import annotations

from .employer.ats_sync import *  # noqa: F401,F403
