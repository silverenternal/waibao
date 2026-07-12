"""v5.0 shim — moved to services/employer/corp_sync.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.corp_sync directly.
"""
from __future__ import annotations

from .employer.corp_sync import *  # noqa: F401,F403
