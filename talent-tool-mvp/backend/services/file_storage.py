"""v5.0 shim — moved to services/integrations/file_storage.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.file_storage directly.
"""
from __future__ import annotations

from .integrations.file_storage import *  # noqa: F401,F403
from .integrations.file_storage import DEFAULT_BUCKET, reset_file_storage  # module-level constants must be re-exported explicitly
