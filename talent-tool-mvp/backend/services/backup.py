"""v5.0 shim — moved to services/platform/backup.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.backup directly.
"""
from __future__ import annotations

from .platform.backup import *  # noqa: F401,F403
