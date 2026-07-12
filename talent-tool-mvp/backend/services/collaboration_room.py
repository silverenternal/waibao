"""v5.0 shim — moved to services/integrations/collaboration_room.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.collaboration_room directly.
"""
from __future__ import annotations

from .integrations.collaboration_room import *  # noqa: F401,F403
