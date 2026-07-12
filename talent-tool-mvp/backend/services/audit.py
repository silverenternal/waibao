"""v5.0 shim — moved to services/observability/audit.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.observability.audit directly.
"""
from __future__ import annotations

from .observability.audit import *  # noqa: F401,F403
from .observability.audit import _supabase_admin  # noqa: F401  — underscored names not exported via star
