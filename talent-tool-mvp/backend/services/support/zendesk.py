"""T2604 - Zendesk support adapter (Phase-1 alternate)."""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .protocol import SupportTicket, TicketDraft

logger = logging.getLogger("recruittech.platform.support.zendesk")


class ZendeskError(RuntimeError):
    """Raised on non-2xx Zendesk response."""


class ZendeskSupportClient:
    name = "zendesk"

    def __init__(
        self,
        *,
        api_token: str | None = None,
        subdomain: str | None = None,
        user_email: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = api_token or os.getenv("ZENDESK_API_TOKEN", "")
        self._sub = subdomain or os.getenv("ZENDESK_SUBDOMAIN", "")
        self._user_email = user_email or os.getenv("ZENDESK_USER_EMAIL", "")
        self._timeout = timeout
        self._dry_run = os.getenv("ZENDESK_DRY_RUN") == "1"
        self._base = f"https://{self._sub}.zendesk.com/api/v2" if self._sub else ""

    def _auth_header(self) -> str:
        cred = f"{self._user_email}/token:{self._token}".encode("utf-8")
        return "Basic " + base64.b64encode(cred).decode("ascii")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._base:
            raise ZendeskError("Zendesk client not configured (missing subdomain/token)")
        url = f"{self._base}{path}"
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header(),
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
            raise ZendeskError(f"{exc.code} {exc.reason}: {snippet!r}") from exc

    @staticmethod
    def _enrich_draft(draft: TicketDraft) -> dict[str, Any]:
        body = draft.body
        if draft.error_logs:
            body += "\n\n<details><summary>Error log</summary>\n\n```\n" + draft.error_logs[-2000:] + "\n```\n</details>"
        ticket: dict[str, Any] = {
            "subject": draft.subject,
            "comment": {"body": body},
            "tags": draft.tags or ["waibao-app"],
        }
        if draft.user_email:
            ticket["requester"] = {"email": draft.user_email, "name": draft.user_name or draft.user_email}
        cf: list[dict[str, Any]] = []
        if draft.tenant_id:
            cf.append({"id": 0, "value": draft.tenant_id})
        if draft.user_id:
            cf.append({"id": 0, "value": draft.user_id})
        if cf:
            ticket["custom_fields"] = cf
        if draft.page_url:
            ticket["via"] = {"channel": "api"}
            ticket["comment"]["public"] = True
        return ticket

    @staticmethod
    def _ticket_from_zd(t: dict[str, Any]) -> SupportTicket:
        cf = {f.get("value"): None for f in (t.get("custom_fields") or [])}
        return SupportTicket(
            id=str(t.get("id", "")),
            public_id=str(t.get("id", "")),
            status=str(t.get("status", "open")),
            subject=str(t.get("subject") or ""),
            requester_email=(t.get("requester_id") and None) or None,  # Zendesk separates requester; we don't expand
            url=f"https://{t.get('url', '').split('//')[-1]}",
            created_at=str(t.get("created_at") or ""),
            updated_at=str(t.get("updated_at") or ""),
            custom_fields={"raw": cf},
        )

    def create_ticket(self, draft: TicketDraft) -> SupportTicket:
        payload = {"ticket": self._enrich_draft(draft)}
        if self._dry_run:
            return SupportTicket(
                id="dryrun-1", public_id="1", status="new", subject=draft.subject,
                requester_email=draft.user_email, created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                custom_fields={"tenant_id": draft.tenant_id, "user_id": draft.user_id},
            )
        resp = self._request("POST", "/tickets.json", body=payload)
        return self._ticket_from_zd(resp.get("ticket") or {})

    def get_ticket(self, ticket_id: str) -> SupportTicket | None:
        if self._dry_run:
            return None
        try:
            resp = self._request("GET", f"/tickets/{ticket_id}.json")
        except ZendeskError as exc:
            if "404" in str(exc):
                return None
            raise
        return self._ticket_from_zd(resp.get("ticket") or {})

    def list_tickets_for_user(self, user_id: str, *, limit: int = 25) -> list[SupportTicket]:
        if self._dry_run:
            return []
        # Zendesk has no clean user_id lookup without external_id mapping;
        # we keep this as a soft listing.
        resp = self._request("GET", f"/search.json?query=type:ticket custom_field_id:0 value:{user_id}&per_page={limit}")
        items = resp.get("results") or []
        return [self._ticket_from_zd(it) for it in items if it.get("result_type") == "ticket"]

    def reply_to_ticket(self, ticket_id: str, body: str, *, from_agent: bool = True) -> SupportTicket:
        payload = {"ticket": {"comment": {"body": body, "public": from_agent}}}
        resp = self._request("PUT", f"/tickets/{ticket_id}.json", body=payload)
        return self._ticket_from_zd(resp.get("ticket") or {})

    def sync_status(self, ticket_id: str) -> SupportTicket | None:
        return self.get_ticket(ticket_id)


__all__ = ["ZendeskSupportClient", "ZendeskError"]
