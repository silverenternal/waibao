"""Billing module entrypoint (v5.0..v10.0 backward-compat).

In v10.0 T5002 the 681-line ``billing.py`` was split into the
``services/billing/`` package (subscription / invoice / usage submodules)
backed by :mod:`._core`.  This thin module re-exports the full public surface
so legacy imports keep working::

    from services.billing.billing import BillingService, Plan, ...
    from services.billing import BillingService, Plan, ...
"""
from __future__ import annotations

from ._core import *  # noqa: F401,F403
from ._core import __all__  # noqa: F401
