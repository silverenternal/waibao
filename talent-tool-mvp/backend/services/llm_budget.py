"""v5.0 shim — moved to services/observability/llm_budget.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.observability.llm_budget directly.
"""
from __future__ import annotations

from .observability.llm_budget import *  # noqa: F401,F403
