"""v5.0 shim — moved to services/integrations/transcribe.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.transcribe directly.
"""
from __future__ import annotations

from .integrations.transcribe import *  # noqa: F401,F403
from .integrations.transcribe import _init_specific  # noqa: F401  — underscored names not exported via star
