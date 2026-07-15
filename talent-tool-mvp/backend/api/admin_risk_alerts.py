"""v11.0 T6110 — Admin/HR risk-alert dashboard.

GET /api/admin/risk-alerts
    List redacted risk alerts.  Admins/HR see ONLY ``risk_level`` + ``reason``
    (+ the matched-keyword *category* hint and ticket id) — never the user's
    raw private conversation.  The ``risk_alerts`` table is populated by
    :mod:`services.platform.escalation` and is RLS-gated to ``hr`` / ``admin``.

POST /api/admin/risk-alerts/check
    Preview-screen a snippet for mandatory-escalation triggers WITHOUT
    persisting or notifying — used by the AI gateway to decide whether a hand
    off is needed before responding.  Returns the redacted hits.

Privacy contract: this endpoint never returns verbatim user text.  The check
endpoint echoes back only rule/risk_level/reason.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_admin
from api.deps import get_supabase_admin
from agents.governance import EscalationRules
from services.platform.escalation import list_risk_alerts

logger = logging.getLogger("recruittech.api.admin_risk_alerts")
router = APIRouter(dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CheckRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待检测文本(不会持久化)")


class RiskAlertOut(BaseModel):
    """Redacted risk-alert row — no raw conversation, ever."""

    id: str
    user_id: str
    organisation_id: Optional[str] = None
    rule: str
    risk_level: str
    reason: str
    matched_keywords: list[str] = []
    message: str = ""
    ticket_id: Optional[str] = None
    notified: bool = False
    created_at: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=list[RiskAlertOut])
async def get_risk_alerts(
    risk_level: Optional[str] = None,
    organisation_id: Optional[str] = None,
    limit: int = 100,
):
    """List redacted risk alerts (admin/HR only)."""
    sb = get_supabase_admin()
    return list_risk_alerts(
        sb,
        organisation_id=organisation_id,
        risk_level=risk_level,
        limit=limit,
    )


@router.post("/check")
async def check_escalation(body: CheckRequest):
    """Screen text for mandatory-escalation triggers (no side effects).

    Returns the redacted hits so the gateway can decide whether to hand off
    before the AI responds.  Nothing is persisted; ``raw_text`` is dropped.
    """
    rules = EscalationRules()
    hits = rules.scan(body.text)  # no LLM here — deterministic, fast preview
    return {
        "must_escalate": bool(hits),
        "hits": [
            {
                "rule": h.rule,
                "risk_level": h.risk_level,
                "reason": h.reason,
                "message": h.message,
                "matched_keywords": list(h.matched_keywords),
            }
            for h in hits
        ],
    }
