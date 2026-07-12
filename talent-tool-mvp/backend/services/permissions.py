"""v5.0 shim — moved to services/platform/permissions.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.permissions directly.
"""
from __future__ import annotations

from .platform.permissions import *  # noqa: F401,F403
