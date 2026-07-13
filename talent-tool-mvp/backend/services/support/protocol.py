"""T2604 - Support integration protocol.

Vendor-neutral data model + a small ``SupportClient`` Protocol. Concrete
adapters (``intercom.IntercomSupportClient``, ``zendesk.ZendeskSupportClient``)
implement this protocol; ``get_default_client`` returns the appropriate
client based on environment configuration.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol
from uuid import uuid4

logger = logging.getLogger("recruittech.platform.support")


@dataclass
class TicketDraft:
    """User-submitted support request.

    Tenant + user context are joined in by the API layer (which knows the
    authenticated session) before passing to the vendor adapter.
    """

    subject: str
    body: str
    tenant_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    user_name: str | None = None
    tags: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    extra_context: dict[str, Any] = field(default_factory=dict)
    error_logs: str | None = None
    page_url: str | None = None
    user_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SupportTicket:
    """A ticket in our internal representation, synced from the vendor."""

    id: str                       # vendor-side id
    public_id: str                # human-facing number (e.g. WAI-1234)
    status: str                   # open / pending / solved / closed
    subject: str
    requester_email: str | None
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    custom_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupportTicket":
        return cls(
            id=str(data.get("id", uuid4())),
            public_id=str(data.get("public_id", "")),
            status=str(data.get("status", "open")),
            subject=str(data.get("subject", "")),
            requester_email=data.get("requester_email"),
            url=data.get("url"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            custom_fields=dict(data.get("custom_fields") or {}),
        )


class SupportClient(Protocol):
    """Protocol implemented by every vendor adapter."""

    name: str

    def create_ticket(self, draft: TicketDraft) -> SupportTicket: ...
    def get_ticket(self, ticket_id: str) -> SupportTicket | None: ...
    def list_tickets_for_user(self, user_id: str, *, limit: int = 25) -> list[SupportTicket]: ...
    def reply_to_ticket(self, ticket_id: str, body: str, *, from_agent: bool = True) -> SupportTicket: ...
    def sync_status(self, ticket_id: str) -> SupportTicket | None: ...


# ---------------------------------------------------------------------------
# Stub fallback (no vendor creds → still useful for E2E / dev)
# ---------------------------------------------------------------------------

class _StubSupportClient:
    name = "stub"

    def __init__(self) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}

    def _reset(self) -> None:
        self._tickets.clear()

    def create_ticket(self, draft: TicketDraft) -> SupportTicket:
        if not draft.user_email:
            raise ValueError("user_email is required to create a ticket")
        tid = str(uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        public_id = f"WAI-{1000 + len(self._tickets)}"
        record = {
            "id": tid,
            "public_id": public_id,
            "status": "open",
            "subject": draft.subject,
            "requester_email": draft.user_email,
            "url": f"https://support.waibao.cn/tickets/{public_id}",
            "created_at": ts,
            "updated_at": ts,
            "custom_fields": {
                "tenant_id": draft.tenant_id,
                "user_id": draft.user_id,
                "tags": draft.tags,
                "extra": draft.extra_context,
                "error_logs": (draft.error_logs or "")[:2048],
            },
            "_replies": [],
        }
        self._tickets[tid] = record
        return SupportTicket.from_dict(record)

    def get_ticket(self, ticket_id: str) -> SupportTicket | None:
        rec = self._tickets.get(ticket_id)
        return SupportTicket.from_dict(rec) if rec else None

    def list_tickets_for_user(self, user_id: str, *, limit: int = 25) -> list[SupportTicket]:
        out: list[SupportTicket] = []
        for rec in self._tickets.values():
            cf = rec.get("custom_fields") or {}
            if cf.get("user_id") == user_id:
                out.append(SupportTicket.from_dict(rec))
                if len(out) >= limit:
                    break
        return out

    def reply_to_ticket(self, ticket_id: str, body: str, *, from_agent: bool = True) -> SupportTicket:
        rec = self._tickets.get(ticket_id)
        if not rec:
            raise KeyError(ticket_id)
        rec["_replies"].append({"body": body, "from_agent": from_agent, "at": datetime.now(timezone.utc).isoformat()})
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        if from_agent:
            rec["status"] = "pending"
        else:
            rec["status"] = "open"
        return SupportTicket.from_dict(rec)

    def sync_status(self, ticket_id: str) -> SupportTicket | None:
        return self.get_ticket(ticket_id)


# ---------------------------------------------------------------------------
# Default client picker
# ---------------------------------------------------------------------------

_client_singleton: SupportClient | None = None


def _build_default_client() -> SupportClient:
    """Choose adapter by env. Falls back to stub."""
    # Lazy import to keep startup fast & avoid pulling vendor SDKs in tests.
    intercom_token = os.getenv("INTERCOM_ACCESS_TOKEN")
    if intercom_token:
        try:
            from .intercom import IntercomSupportClient
            return IntercomSupportClient(access_token=intercom_token)
        except Exception as exc:  # pragma: no cover
            logger.warning("Intercom adapter failed to construct: %s", exc)
    zendesk_token = os.getenv("ZENDESK_API_TOKEN")
    zendesk_subdomain = os.getenv("ZENDESK_SUBDOMAIN")
    if zendesk_token and zendesk_subdomain:
        try:
            from .zendesk import ZendeskSupportClient
            return ZendeskSupportClient(api_token=zendesk_token, subdomain=zendesk_subdomain)
        except Exception as exc:  # pragma: no cover
            logger.warning("Zendesk adapter failed to construct: %s", exc)
    return _StubSupportClient()


def get_default_client() -> SupportClient:
    """Return a process-singleton adapter (memoised)."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = _build_default_client()
    return _client_singleton


def reset_default_client_for_tests() -> None:
    """Test helper: forget memoised adapter."""
    global _client_singleton
    _client_singleton = None


__all__ = [
    "TicketDraft",
    "SupportTicket",
    "SupportClient",
    "get_default_client",
    "reset_default_client_for_tests",
]
