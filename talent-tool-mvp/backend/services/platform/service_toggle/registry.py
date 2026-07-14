"""Service Toggle — Registry slice (v10.0 T5002 split).

Covers: registration / deregistration of services and the catalog read paths
(``get_service`` / ``get_catalog``).  Logic lives in :mod:`._core`; this module
re-exports the relevant public surface so callers can import from a named
concern if they prefer.
"""
from __future__ import annotations

from ._core import ServiceToggle, service_toggle

__all__ = ["ServiceToggle", "service_toggle"]
