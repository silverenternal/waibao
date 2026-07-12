"""v5.0 shim — moved to services/platform/handoff.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.handoff directly.
"""
from __future__ import annotations

from .platform.handoff import *  # noqa: F401,F403
