"""Service Toggle — Gate slice (v10.0 T5002 split).

Covers the multi-layer access decision (status + plan + role + per-org
override) and the ``invalidate_cache`` helper.  Logic lives in :mod:`._core`;
this module re-exports the relevant public surface.
"""
from __future__ import annotations

from ._core import ServiceToggle, invalidate_cache, service_toggle

__all__ = ["ServiceToggle", "invalidate_cache", "service_toggle"]
