"""v5.0 shim — moved to services/integrations/pii_field_encryption.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.pii_field_encryption directly.
"""
from __future__ import annotations

from .integrations.pii_field_encryption import *  # noqa: F401,F403
