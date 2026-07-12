"""v5.0 shim — moved to services/matching/global_search.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.matching.global_search directly.
"""
from __future__ import annotations

from .matching.global_search import *  # noqa: F401,F403
