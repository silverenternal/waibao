"""v5.0 shim — moved to services/billing/billing.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.billing.billing directly.
"""
from __future__ import annotations

from .billing.billing import *  # noqa: F401,F403
