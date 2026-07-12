"""v5.0 shim — moved to services/employer/channel_attribution.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.channel_attribution directly.
"""
from __future__ import annotations

from .employer.channel_attribution import *  # noqa: F401,F403
