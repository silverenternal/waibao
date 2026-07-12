"""v5.0 shim — moved to services/integrations/candidate_recommender.py.

This file is kept for backward compatibility (v5.0..v5.1).
New code should import from services.integrations.candidate_recommender directly.
"""
from __future__ import annotations

from .integrations.candidate_recommender import *  # noqa: F401,F403
