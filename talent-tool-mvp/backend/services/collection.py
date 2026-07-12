"""v5.0 shim — moved to services/platform/collection.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.collection directly.
"""
from __future__ import annotations

from .platform.collection import *  # noqa: F401,F403
