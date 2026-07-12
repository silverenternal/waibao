"""v5.0 shim — moved to services/employer/background_check_service.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.background_check_service directly.
"""
from __future__ import annotations

from .employer.background_check_service import *  # noqa: F401,F403
