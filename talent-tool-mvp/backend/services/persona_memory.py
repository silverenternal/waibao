"""v5.0 shim — moved to services/integrations/persona_memory.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.persona_memory directly.
"""
from __future__ import annotations

from .integrations.persona_memory import *  # noqa: F401,F403
