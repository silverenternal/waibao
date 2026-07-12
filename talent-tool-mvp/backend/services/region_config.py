"""v5.0 shim — moved to services/platform/region_config.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.region_config directly.
"""
from __future__ import annotations

from .platform.region_config import *  # noqa: F401,F403
