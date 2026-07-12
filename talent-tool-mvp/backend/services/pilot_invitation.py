"""v5.0 shim — moved to services/integrations/pilot_invitation.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.pilot_invitation directly.
"""
from __future__ import annotations

from .integrations.pilot_invitation import *  # noqa: F401,F403
