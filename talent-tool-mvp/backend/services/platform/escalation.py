"""v11.0 T6110 — Mandatory human-escalation service.

Wraps :class:`agents.governance.EscalationRules` with the *side effects* a
detection must trigger:

* **self-harm** (``risk_level="critical"``) → insert a ``risk_alerts`` row
  flagged critical, fire the ``emotion.crisis`` webhook, page HR *immediately*
  via the notify dispatcher.  The user sees a warm popup with the national
  psychological-aid hotline (400-161-9995).
* **labour dispute** (``risk_level="high"``) → insert a ``risk_alerts`` row
  flagged high, fire ``policy.legal_risk``, and open an HR/legal ticket.

Privacy contract (甲方要求)
--------------------------
Original private conversation is **never** persisted on the escalation
record, and admins/HR only ever see ``risk_level`` + ``reason`` (+ an opaque
keyword/evidence count) — never the verbatim message.  The ``raw_text`` is
accepted by :func:`escalate` purely for detection and then discarded.  The
``risk_alerts`` table is also protected by RLS so only ``hr`` / ``admin``
roles can read the (already-redacted) summary; the underlying chat rows live
behind their own user-scoped RLS.

The AI never eliminates a candidate here — this module only produces a
recommendation + a handoff; the human owns the outcome.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from agents.governance import (
    EscalationRuleHit,
    EscalationRules,
    SELF_HARM_HOTLINE,
)

logger = logging.getLogger("recruittech.platform.escalation")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class EscalationRecord:
    """The redacted, human-visible record of one escalation.

    Deliberately carries **no** verbatim conversation text — only
    ``risk_level`` + ``reason`` + opaque counts.  ``ticket_id`` is set when a
    ticket was opened (labour-dispute / self-harm with a queue).
    """

    id: str
    user_id: str
    organisation_id: Optional[str]
    rule: str                  # self_harm | labour_dispute
    risk_level: str            # critical | high
    reason: str                # human-readable, PII-free
    matched_keywords: list[str]
    message: str               # warm copy shown to the user
    ticket_id: Optional[str] = None
    notified: bool = False
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organisation_id": self.organisation_id,
            "rule": self.rule,
            "risk_level": self.risk_level,
            "reason": self.reason,
            # Keywords are a *category* hint, not the user's words — safe to
            # surface so HR knows what triaged the alert.
            "matched_keywords": self.matched_keywords,
            "message": self.message,
            "ticket_id": self.ticket_id,
            "notified": self.notified,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_alert(supabase: Any, rec: EscalationRecord) -> None:
    """Insert a redacted row into ``risk_alerts`` (no raw text)."""
    try:
        supabase.table("risk_alerts").insert({
            "id": rec.id,
            "user_id": rec.user_id,
            "organisation_id": rec.organisation_id,
            "rule": rec.rule,
            "risk_level": rec.risk_level,
            "reason": rec.reason,
            "matched_keywords": rec.matched_keywords,
            "message": rec.message,
            "ticket_id": rec.ticket_id,
            "notified": rec.notified,
            "created_at": rec.created_at,
        }).execute()
    except Exception as exc:  # noqa: BLE001 — persistence is best-effort
        logger.warning("risk_alerts insert failed: %s", exc)


def _open_ticket(
    supabase: Any,
    *,
    user_id: str,
    organisation_id: Optional[str],
    rule: str,
    risk_level: str,
    reason: str,
    assignee_id: Optional[str] = None,
) -> Optional[str]:
    """Open an HR/legal ticket for an escalation. Returns ticket id or None.

    The ticket title/description use only the *category* + reason — never the
    user's verbatim message — so the queue stays private.
    """
    try:
        from services.employer.ticket_service import create_ticket

        category = "hr" if rule == "self_harm" else "policy"
        priority = "urgent" if risk_level == "critical" else "high"
        title = "[自动转人工] " + reason
        ticket = create_ticket(
            supabase,
            user_id=user_id,
            title=title,
            description=reason,  # category reason, not the raw conversation
            priority=priority,
            category=category,
            organisation_id=organisation_id,
            assignee_id=assignee_id,
            auto_create=True,
            metadata={
                "source": "governance_escalation",
                "rule": rule,
                "risk_level": risk_level,
                "raw_text_stored": False,  # privacy marker
            },
            tags=["escalated", "auto", f"rule:{rule}", f"risk:{risk_level}"],
        )
        return ticket.id if hasattr(ticket, "id") else ticket.get("id")
    except Exception as exc:  # noqa: BLE001
        logger.warning("escalation ticket create failed: %s", exc)
        return None


async def _notify_hr(
    *,
    organisation_id: Optional[str],
    user_id: str,
    rule: str,
    risk_level: str,
    reason: str,
) -> bool:
    """Page HR with a redacted alert (no conversation content)."""
    try:
        from services.notify import push

        title = "紧急: 用户风险提醒" if risk_level == "critical" else "风险提醒: 劳动争议"
        content = (
            f"用户 {user_id[:8]}… 触发 {rule} 提醒 ({risk_level})。{reason}。"
            "请在风险提醒面板查看详情(出于隐私保护,原文不展示)。"
        )
        await push(
            channel="dingtalk",
            user_id="hr_team",
            title=title,
            content=content,
            payload={
                "organisation_id": organisation_id,
                "rule": rule,
                "risk_level": risk_level,
                "reason": reason,
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("escalation HR notify failed: %s", exc)
        return False


def _fire_webhook(rule: str, risk_level: str, payload: dict[str, Any]) -> None:
    """Fire the matching domain webhook (best-effort, fire-and-forget)."""
    try:
        import asyncio

        from services.webhook import WebhookEvent, fire_webhook

        event = (
            WebhookEvent.EMOTION_CRISIS
            if rule == "self_harm"
            else WebhookEvent.POLICY_LEGAL_RISK
        )
        asyncio.create_task(fire_webhook(event, payload.get("organisation_id", ""), payload))
    except Exception as exc:  # noqa: BLE001
        logger.debug("escalation webhook fire failed: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def escalate(
    *,
    user_id: str,
    reason: str,
    risk_level: str,
    metadata: Optional[dict[str, Any]] = None,
    supabase: Any = None,
    llm: Any = None,
) -> EscalationRecord:
    """Escalate a single (already-detected) signal to a human.

    Parameters
    ----------
    user_id:
        The user the alert is about.
    reason:
        PII-free human description (e.g. from :class:`EscalationRuleHit`).
    risk_level:
        ``critical`` (self-harm → immediate notify) or ``high`` (labour
        dispute → open ticket).  Any other value is coerced to ``high``.
    metadata:
        Carries ``rule``, ``matched_keywords``, ``organisation_id``,
        ``message`` and optionally the throwaway ``raw_text`` used for an LLM
        re-check (never persisted).
    """
    md = dict(metadata or {})
    rule = md.get("rule") or (
        "self_harm" if risk_level == "critical" else "labour_dispute"
    )
    if risk_level not in ("critical", "high"):
        risk_level = "high"

    rec = EscalationRecord(
        id=str(uuid4()),
        user_id=user_id,
        organisation_id=md.get("organisation_id"),
        rule=rule,
        risk_level=risk_level,
        reason=reason,
        matched_keywords=list(md.get("matched_keywords") or []),
        message=md.get("message") or "",
        created_at=_now(),
    )

    sb = supabase
    if sb is None:
        try:
            from api.deps import get_supabase_admin
            sb = get_supabase_admin()
        except Exception:  # noqa: BLE001 — allow headless use in tests
            sb = None

    # 1) Persist the redacted alert.
    if sb is not None:
        _persist_alert(sb, rec)

    # 2) Open a ticket (labour-dispute always; self-harm also gets a queue).
    ticket_id: Optional[str] = None
    if sb is not None:
        ticket_id = _open_ticket(
            sb,
            user_id=user_id,
            organisation_id=rec.organisation_id,
            rule=rule,
            risk_level=risk_level,
            reason=reason,
            assignee_id=md.get("assignee_id"),
        )
    rec.ticket_id = ticket_id

    # 3) Self-harm → page HR immediately; labour-dispute → notify too.
    rec.notified = await _notify_hr(
        organisation_id=rec.organisation_id,
        user_id=user_id,
        rule=rule,
        risk_level=risk_level,
        reason=reason,
    )

    # 4) Webhook fan-out (redacted payload — no raw_text).
    _fire_webhook(rule, risk_level, {
        "organisation_id": rec.organisation_id,
        "user_id": user_id,
        "rule": rule,
        "risk_level": risk_level,
        "reason": reason,
        "ticket_id": ticket_id,
        "hotline": SELF_HARM_HOTLINE if rule == "self_harm" else None,
    })

    return rec


async def escalate_from_text(
    text: str,
    *,
    user_id: str,
    organisation_id: Optional[str] = None,
    supabase: Any = None,
    llm: Any = None,
    rules: Optional[EscalationRules] = None,
) -> list[EscalationRecord]:
    """Detect mandatory-escalation signals in ``text`` and escalate each.

    Returns one :class:`EscalationRecord` per hit (empty list when clean).
    The ``raw_text`` is used only for detection and is **never** persisted.

    This is the convenience entry point agents call right after they receive a
    user message — it both screens and performs the handoff.
    """
    rules = rules or EscalationRules()
    hits = rules.scan(text, llm=llm)
    if not hits:
        return []

    out: list[EscalationRecord] = []
    for hit in hits:
        rec = await escalate(
            user_id=user_id,
            reason=hit.reason,
            risk_level=hit.risk_level,
            metadata={
                "rule": hit.rule,
                "matched_keywords": list(hit.matched_keywords),
                "organisation_id": organisation_id,
                "message": hit.message,
            },
            supabase=supabase,
            llm=llm,
        )
        out.append(rec)
    return out


def list_risk_alerts(
    supabase: Any,
    *,
    organisation_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return redacted risk alerts for the admin/HR dashboard.

    Only ``risk_level`` + ``reason`` (+ keywords/ticket) are returned — the
    raw conversation is never in this table, and the API layer additionally
    drops any stray sensitive columns before serialization.
    """
    q = supabase.table("risk_alerts").select(
        "id, user_id, organisation_id, rule, risk_level, reason, "
        "matched_keywords, message, ticket_id, notified, created_at"
    )
    if organisation_id:
        q = q.eq("organisation_id", organisation_id)
    if risk_level:
        q = q.eq("risk_level", risk_level)
    res = q.order("created_at", desc=True).limit(limit).execute()
    return list(res.data or [])


__all__ = [
    "EscalationRecord",
    "escalate",
    "escalate_from_text",
    "list_risk_alerts",
]
