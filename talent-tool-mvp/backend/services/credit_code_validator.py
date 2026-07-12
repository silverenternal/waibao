"""v5.0 shim — moved to services/platform/credit_code_validator.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.platform.credit_code_validator directly.
"""
from __future__ import annotations

from .platform.credit_code_validator import *  # noqa: F401,F403
