"""T2604 - Intercom support adapter.

Implements the :class:`services.support.protocol.SupportClient` protocol using
the Intercom REST API. We deliberately use stdlib ``urllib`` (no vendor SDK)
to keep the dependency surface minimal and to make tests trivial.

Reference: https://developers.intercom.com/intercom-api-reference

Env:
  INTERCOM_ACCESS_TOKEN   personal access token (required)
  INTERCOM_API_URL        (optional override, default https://api.intercom.io)
  INTERCOM_DRY_RUN        1 = never call upstream, only log
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from .protocol import SupportTicket, TicketDraft

logger = logging.getLogger("recruittech.platform.support.intercom")


class IntercomError(RuntimeError):
    """Raised when an upstream call returns a non-2xx response."""


class IntercomSupportClient:
    name = "intercom"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        api_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = access_token or os.getenv("INTERCOM_ACCESS_TOKEN", "")
        self._base = (api_url or os.getenv("INTERCOM_API_URL", "https://api.intercom.io")).rstrip("/")
        self._timeout = timeout
        self._dry_run = os.getenv("INTERCOM_DRY_RUN") == "1"
        if not self._token and not self._dry_run:
            logger.warning(
                "Intercom client constructed without INTERCOM_ACCESS_TOKEN; "
                "upstream calls will fail. Set INTERCOM_DRY_RUN=1 to silence."
            )

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "Intercom-Version": "2.11",
            "User-Agent": "waibao-support/1.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            snippet = exc.read()[:512] if hasattr(exc, "read") else b""
            raise IntercomError(f"{exc.code} {exc.reason}: {snippet!r}") from exc

    @staticmethod
    def _enrich_draft(draft: TicketDraft) -> dict[str, Any]:
        """Translate ``TicketDraft`` → Intercom ``conversation`` payload.

        Intercom "Support" conversations expect a contact + admin + body; we
        attach tenant/user/error metadata as ``custom_attributes``.
        """
        if not draft.user_email:
            raise ValueError("user_email is required to create an Intercom conversation")
        attrs: dict[str, Any] = {
            "tenant_id": draft.tenant_id,
            "user_id": draft.user_id,
            "tags": draft.tags,
            "page_url": draft.page_url,
            "user_agent": draft.user_agent,
        }
        if draft.extra_context:
            for k, v in draft.extra_context.items():
                attrs[f"ctx_{k}"] = str(v)[:500]
        if draft.error_logs:
            attrs["error_logs_preview"] = draft.error_logs[:1500]
        body = draft.body
        if draft.error_logs and draft.error_logs.strip():
            body += "\n\n```\n" + draft.error_logs[-2000:] + "\n```"
        payload: dict[str, Any] = {
            "from": {"type": "user", "email": draft.user_email},
            "body": body,
        }
        if draft.user_id or draft.user_name:
            payload["from"]["external_id"] = draft.user_id or str(uuid.uuid4())
            if draft.user_name:
                payload["from"]["name"] = draft.user_name
        return {
            "display_id": None,
            "subject": draft.subject,
            "custom_attributes": attrs,
            "tags": draft.tags or [{"name": "waibao-app"}],
            "_body_payload": payload,
        }

    @staticmethod
    def _ticket_from_conversation(conv: dict[str, Any]) -> SupportTicket:
        """Map an Intercom conversation → our :class:`SupportTicket`."""
        attrs = (conv.get("custom_attributes") or {})
        user = (conv.get("source") or {}).get("author") or {}
        tags = [t.get("name", "") for t in (conv.get("tags") or {}).get("data", []) if isinstance(t, dict)]
        return SupportTicket(
            id=str(conv.get("id", "")),
            public_id=str(conv.get("id", "")),
            status=str(conv.get("status") or "open"),
            subject=str(conv.get("title") or conv.get("source") or ""),
            requester_email=user.get("email"),
            url=conv.get("url"),
            created_at=conv.get("created_at"),
            updated_at=conv.get("updated_at"),
            custom_fields={
                "tenant_id": attrs.get("tenant_id"),
                "user_id": attrs.get("user_id"),
                "tags": tags,
            },
        )

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def create_ticket(self, draft: TicketDraft) -> SupportTicket:
        enriched = self._enrich_draft(draft)
        body_payload = enriched.pop("_body_payload")
        body_payload["subject"] = draft.subject
        body_payload["custom_attributes"] = enriched["custom_attributes"]
        body_payload["tag_ids"] = enriched["tags"]
        body_payload["type"] = "conversation"
        if self._dry_run:
            fake_id = f"dryrun-{uuid.uuid4()}"
            return SupportTicket(
                id=fake_id,
                public_id=fake_id,
                status="open",
                subject=draft.subject,
                requester_email=draft.user_email,
                url="https://app.intercom.com/responses",
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                custom_fields={
                    "tenant_id": draft.tenant_id,
                    "user_id": draft.user_id,
                    "tags": draft.tags,
                },
            )
        resp = self._request("POST", "/conversations", body=body_payload)
        # Intercom wraps reply endpoints — fall back to GET to fetch full record
        tid = str(((resp.get("conversation") or {}).get("id")) or resp.get("id") or "")
        if not tid:
            raise IntercomError(f"create_ticket: no id in response: {resp}")
        return self.get_ticket(tid) or self._ticket_from_conversation(resp.get("conversation") or resp)

    def get_ticket(self, ticket_id: str) -> SupportTicket | None:
        if self._dry_run:
            return None
        try:
            resp = self._request("GET", f"/conversations/{ticket_id}")
        except IntercomError as exc:
            if "404" in str(exc):
                return None
            raise
        return self._ticket_from_conversation(resp)

    def list_tickets_for_user(self, user_id: str, *, limit: int = 25) -> list[SupportTicket]:
        if self._dry_run:
            return []
        path = (
            f"/conversations/search?limit={limit}"
            f"&query=%7B%22field%22%3A%22custom_attributes.user_id%22%2C%22operator%22%3A%22%3D%22%2C%22value%22%3A%22{user_id}%22%7D"
        )
        resp = self._request("GET", path)
        items = ((resp.get("conversations") or {}).get("data") or resp.get("data") or []) or []
        return [self._ticket_from_conversation(it) for it in items if isinstance(it, dict)]

    def reply_to_ticket(self, ticket_id: str, body: str, *, from_agent: bool = True) -> SupportTicket:
        if self._dry_run:
            current = self.get_ticket(ticket_id) or SupportTicket(
                id=ticket_id, public_id=ticket_id, status="open", subject="(dryrun)"
            )
            current.status = "pending" if from_agent else "open"
            current.updated_at = datetime.now(timezone.utc).isoformat()
            return current
        admin_id = os.getenv("INTERCOM_ADMIN_ID") or ""
        payload: dict[str, Any] = {
            "message_type": "comment" if from_agent else "note",
            "type": "admin" if from_agent else "admin",
            "body": body,
        }
        if admin_id:
            payload["admin_id"] = admin_id
        resp = self._request("POST", f"/conversations/{ticket_id}/reply", body=payload)
        return self._ticket_from_conversation(resp.get("conversation") or resp)

    def sync_status(self, ticket_id: str) -> SupportTicket | None:
        return self.get_ticket(ticket_id)


__all__ = ["IntercomSupportClient", "IntercomError"]
