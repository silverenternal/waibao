"""v5.0 shim — moved to services/jobseeker/resume_parser.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.jobseeker.resume_parser directly.
"""
from __future__ import annotations

from .jobseeker.resume_parser import *  # noqa: F401,F403
from .jobseeker.resume_parser import (  # noqa: F401  — underscored names not exported via star
    _fetch_bytes,
    _is_probably_text,
    _ocr_via_registry,
    _vision_fallback,
    _post_process,
)
