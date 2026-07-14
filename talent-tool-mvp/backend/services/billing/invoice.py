"""Billing — Invoice / Webhook slice (v10.0 T5002 split).

Covers invoice materialisation from provider payloads and the idempotent
webhook entrypoint.  The orchestrating methods live on :class:`BillingService`
in :mod:`._core`; this module re-exports them so the invoice/webhook concern
is importable on its own.
"""
from __future__ import annotations

from ._core import BillingService  # noqa: F401

__all__ = ["BillingService"]
