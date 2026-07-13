"""T2604 - Customer support API.

Authenticated users can create tickets from the in-app widget and view their
own ticket history. Each ticket automatically attaches tenant_id, user_id,
optional error logs, and a snapshot of the user's session context.

Endpoints:
  POST /api/support/tickets                  — create new ticket
  GET  /api/support/tickets                  — list current user tickets
  GET  /api/support/tickets/{id}             — fetch one ticket (mirror status)
  POST /api/support/tickets/{id}/replies     — user reply
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_role
from contracts.shared import UserRole
from services.support import TicketDraft, get_default_client

logger = logging.getLogger("recruittech.api.support")

router = APIRouter(prefix="/api/support", tags=["support"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateTicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=8000)
    tags: list[str] = Field(default_factory=list)
    extra_context: dict[str, Any] = Field(default_factory=dict)
    error_logs: Optional[str] = Field(default=None, max_length=8192)


class CreateTicketOut(BaseModel):
    id: str
    public_id: str
    status: str
    subject: str
    url: Optional[str] = None


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _draft_from_request(req: CreateTicketIn, user: CurrentUser, request: Request) -> TicketDraft:
    return TicketDraft(
        subject=req.subject,
        body=req.body,
        tenant_id=user.tenant_id,
        user_id=user.id,
        user_email=user.email,
        user_name=user.name,
        tags=req.tags + ["waibao-app", f"tenant:{user.tenant_id or 'none'}"],
        extra_context=req.extra_context,
        error_logs=req.error_logs,
        page_url=str(request.headers.get("referer") or request.url),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/tickets", response_model=CreateTicketOut)
async def create_ticket(
    body: CreateTicketIn,
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.client, UserRole.admin)),
    request: Request = None,  # type: ignore[assignment]
):
    """Authenticated tenant user creates a ticket.

    Tenant id, user id, and any error logs are attached automatically — the
    SDK caller only has to provide ``subject`` + ``body`` (+ optional context).
    """
    if not user.email:
        raise HTTPException(status_code=400, detail="missing email on session")
    draft = _draft_from_request(body, user, request)
    client = get_default_client()
    ticket = client.create_ticket(draft)
    return CreateTicketOut(
        id=ticket.id,
        public_id=ticket.public_id,
        status=ticket.status,
        subject=ticket.subject,
        url=ticket.url,
    )


@router.get("/tickets")
async def list_tickets(
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.client, UserRole.admin)),
    limit: int = Query(default=25, ge=1, le=100),
):
    """List the current user's tickets (vendor-side mirror)."""
    client = get_default_client()
    tickets = client.list_tickets_for_user(user.id, limit=limit)
    return {
        "tickets": [
            {
                "id": t.id,
                "public_id": t.public_id,
                "subject": t.subject,
                "status": t.status,
                "url": t.url,
                "updated_at": t.updated_at,
            }
            for t in tickets
        ]
    }


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.client, UserRole.admin)),
):
    """Mirror the current vendor-side status for a known ticket."""
    client = get_default_client()
    ticket = client.sync_status(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {
        "id": ticket.id,
        "public_id": ticket.public_id,
        "subject": ticket.subject,
        "status": ticket.status,
        "url": ticket.url,
        "updated_at": ticket.updated_at,
    }


@router.post("/tickets/{ticket_id}/replies", response_model=CreateTicketOut)
async def reply_to_ticket(
    ticket_id: str,
    body: ReplyIn,
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.client, UserRole.admin)),
):
    """User reply — vendor's bi-directional sync updates status accordingly."""
    client = get_default_client()
    ticket = client.reply_to_ticket(ticket_id, body.body, from_agent=False)
    return CreateTicketOut(
        id=ticket.id,
        public_id=ticket.public_id,
        status=ticket.status,
        subject=ticket.subject,
        url=ticket.url,
    )


__all__ = ["router"]
