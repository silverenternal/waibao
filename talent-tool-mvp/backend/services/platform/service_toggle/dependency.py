"""Service Toggle — Dependency slice (v10.0 T5002 split).

Covers the cross-service dependency graph: ``DependencyError`` (raised when
disabling a service that active services depend on) and the rollback path.
Logic lives in :mod:`._core`; this module re-exports the relevant public
surface.
"""
from __future__ import annotations

from ._core import DependencyError, ServiceToggle, service_toggle

__all__ = ["DependencyError", "ServiceToggle", "service_toggle"]
