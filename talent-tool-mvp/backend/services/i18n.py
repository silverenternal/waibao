"""v5.0 shim — moved to services/platform/i18n.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.i18n directly.
"""
from __future__ import annotations

from .platform.i18n import *  # noqa: F401,F403
