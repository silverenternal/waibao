"""v5.0 shim — moved to services/employer/feishu_sync.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.feishu_sync directly.
"""
from __future__ import annotations

from .employer.feishu_sync import *  # noqa: F401,F403
