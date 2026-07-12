"""v5.0 shim — moved to services/integrations/realtime_router.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.realtime_router directly.
"""
from __future__ import annotations

from .integrations.realtime_router import *  # noqa: F401,F403
