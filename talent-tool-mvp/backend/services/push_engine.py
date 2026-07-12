"""v5.0 shim — moved to services/integrations/push_engine.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.push_engine directly.
"""
from __future__ import annotations

from .integrations.push_engine import *  # noqa: F401,F403
