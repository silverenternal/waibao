"""v5.0 shim — moved to services/integrations/job_subscription.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.job_subscription directly.
"""
from __future__ import annotations

from .integrations.job_subscription import *  # noqa: F401,F403
