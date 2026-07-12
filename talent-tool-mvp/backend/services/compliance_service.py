"""v5.0 shim — moved to services/employer/compliance_service.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.employer.compliance_service directly.
"""
from __future__ import annotations

from .employer.compliance_service import *  # noqa: F401,F403
from .employer.compliance_service import _resolve_lookup_provider  # noqa: F401  — underscored names not exported via star
