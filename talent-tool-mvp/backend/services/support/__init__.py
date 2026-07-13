"""T2604 - Customer support integration (Intercom / Zendesk).

This package keeps vendor-specific adapters behind a thin uniform protocol so
the rest of the codebase can talk to "the support desk" without binding to a
single tool.

Modules:
  - ``protocol``  — vendor-neutral ``SupportClient`` Protocol + adapters
  - ``intercom``  — Intercom REST adapter
  - ``zendesk``   — Zendesk Support API adapter
"""
from __future__ import annotations

from .protocol import (
    SupportTicket,
    TicketDraft,
    SupportClient,
    get_default_client,
    reset_default_client_for_tests,
)

__all__ = [
    "SupportTicket",
    "TicketDraft",
    "SupportClient",
    "get_default_client",
    "reset_default_client_for_tests",
]


# Lazy adapter class exporters — both pull env vars on import.
def _lazy_intercom():
    try:
        from .intercom import IntercomSupportClient
        return IntercomSupportClient
    except Exception:
        return None


def _lazy_zendesk():
    try:
        from .zendesk import ZendeskSupportClient
        return ZendeskSupportClient
    except Exception:
        return None


INTERCOM_CLIENT_CLS = _lazy_intercom()
ZENDESK_CLIENT_CLS = _lazy_zendesk()
