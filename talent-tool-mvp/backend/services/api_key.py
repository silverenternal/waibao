"""v5.0 shim — moved to services/integrations/api_key.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.api_key directly.
"""
from __future__ import annotations

from .integrations.api_key import *  # noqa: F401,F403
