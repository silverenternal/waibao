"""v5.0 shim — moved to services/observability/llm_cache.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.observability.llm_cache directly.
"""
from __future__ import annotations

from .observability.llm_cache import *  # noqa: F401,F403
