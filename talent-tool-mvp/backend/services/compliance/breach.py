"""v10.0 T5016 — Personal-data breach register + Art. 33 / Art. 34 notification
orchestrator.

GDPR Article 33 requires the controller to notify the supervisory authority
**without undue delay and, where feasible, not later than 72 hours after
having become aware of a personal data breach**.  Article 34 requires
communicating the breach to affected data subjects **without undue delay**
when the breach is likely to result in a *high risk* to their rights.

PIPL (PRC) sets a tighter 24-hour window for certain transfers; CCPA has no
fixed hour count but requires "the most expedient time possible".  This service
encodes all three clocks in one place:

* :func:`notification_deadline_hours(region)` — the statutory authority window.
* :class:`BreachService.register` — creates a breach record, stamps
  ``awareness_at`` (the clock start), computes the deadline, and classifies
  risk to decide whether Art. 34 subject-notification is mandatory.
* :class:`BreachService.escalation_status` — live status (``on_time`` /
  ``breached`` / ``imminent``) used by the SLA dashboard.

The store is pluggable (:class:`BreachStore` protocol); an in-memory default is
provided.  Real persistence + the actual email/Slack fan-out to the authority
and to subjects is wired by production via the notifier hooks.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger("waibao.compliance.breach")


# ---------------------------------------------------------------------------
# Statutory windows (hours)
# ---------------------------------------------------------------------------

# GDPR Art. 33(1) — "not later than 72 hours after having become aware".
GDPR_AUTHORITY_HOURS = 72
# PIPL Art. 57 — "without delay" in practice read as 24h for cross-border.
PIPL_AUTHORITY_HOURS = 24
# CCPA — no statutory hour count; use a conservative expedient default.
CCPA_AUTHORITY_HOURS = 72
# "Imminent" threshold — flag when < this fraction of the window remains.
IMMINENT_FRACTION = 0.25  # 25 % of window → escalate to imminent


def notification_deadline_hours(region: str) -> int:
    """Return the statutory authority-notification window (hours) for a region.

    ``CN`` → PIPL 24h; ``CA`` → CCPA expedient 72h; everything else → GDPR 72h.
    """
    r = (region or "EU").upper()
    if r == "CN":
        return PIPL_AUTHORITY_HOURS
    if r == "CA":
        return CCPA_AUTHORITY_HOURS
    return GDPR_AUTHORITY_HOURS


# ---------------------------------------------------------------------------
# Risk classification (drives Art. 34 subject notification)
# ---------------------------------------------------------------------------

VALID_SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
# Severity → default risk-of-high-harm boolean (Art. 34 trigger).
HIGH_RISK_SEVERITIES: frozenset[str] = frozenset({"high", "critical"})


@dataclass
class BreachRecord:
    id: str
    tenant_id: Optional[str]
    region: str
    severity: str
    description: str
    categories_affected: list[str]
    subjects_affected: int
    records_affected: int
    occurred_at: datetime
    awareness_at: datetime            # Art. 33 clock starts here
    authority_deadline: datetime       # awareness + window
    authority_notified_at: Optional[datetime] = None
    subjects_notified_at: Optional[datetime] = None
    containment_status: str = "open"   # open | contained | resolved
    high_risk_to_subjects: bool = False
    art34_exemption_applied: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def _iso(v: Optional[datetime]) -> Optional[str]:
            return v.isoformat() if v else None
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "region": self.region,
            "severity": self.severity,
            "description": self.description,
            "categories_affected": self.categories_affected,
            "subjects_affected": self.subjects_affected,
            "records_affected": self.records_affected,
            "occurred_at": _iso(self.occurred_at),
            "awareness_at": _iso(self.awareness_at),
            "authority_deadline": _iso(self.authority_deadline),
            "authority_notified_at": _iso(self.authority_notified_at),
            "subjects_notified_at": _iso(self.subjects_notified_at),
            "containment_status": self.containment_status,
            "high_risk_to_subjects": self.high_risk_to_subjects,
            "art34_exemption_applied": self.art34_exemption_applied,
            "created_by": self.created_by,
            "created_at": _iso(self.created_at),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------

class BreachStore(Protocol):
    def insert(self, record: BreachRecord) -> None: ...
    def get(self, breach_id: str) -> Optional[BreachRecord]: ...
    def update(self, breach_id: str, patch: dict[str, Any]) -> None: ...
    def list(self, *, tenant_id: Optional[str] = None, limit: int = 100) -> list[BreachRecord]: ...


class InMemoryBreachStore:
    def __init__(self) -> None:
        self._records: dict[str, BreachRecord] = {}

    def insert(self, record: BreachRecord) -> None:
        self._records[record.id] = record

    def get(self, breach_id: str) -> Optional[BreachRecord]:
        return self._records.get(breach_id)

    def update(self, breach_id: str, patch: dict[str, Any]) -> None:
        rec = self._records.get(breach_id)
        if rec is None:
            return
        for k, v in patch.items():
            if hasattr(rec, k):
                setattr(rec, k, v)

    def list(self, *, tenant_id: Optional[str] = None, limit: int = 100) -> list[BreachRecord]:
        rows = list(self._records.values())
        if tenant_id is not None:
            rows = [r for r in rows if r.tenant_id == tenant_id]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]


# ---------------------------------------------------------------------------
# Notifier hooks (production wires email/Slack/PagerDuty here)
# ---------------------------------------------------------------------------

AuthorityNotifier = Callable[[BreachRecord], dict[str, Any]]
SubjectNotifier = Callable[[BreachRecord], dict[str, Any]]


def _stub_notifier(rec: BreachRecord) -> dict[str, Any]:
    return {"delivered": False, "reason": "no notifier configured"}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BreachService:
    """The single source of truth for breach registration + notification clocks."""

    def __init__(
        self,
        store: BreachStore,
        *,
        authority_notifier: AuthorityNotifier = _stub_notifier,
        subject_notifier: SubjectNotifier = _stub_notifier,
    ) -> None:
        self.store = store
        self.authority_notifier = authority_notifier
        self.subject_notifier = subject_notifier

    # ------------------------------------------------------------------
    def register(
        self,
        *,
        severity: str,
        description: str,
        region: str = "EU",
        tenant_id: Optional[str] = None,
        categories_affected: Optional[list[str]] = None,
        subjects_affected: int = 0,
        records_affected: int = 0,
        occurred_at: Optional[datetime] = None,
        awareness_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
        notify_authority: bool = False,
        notify_subjects: bool = False,
        art34_exemption: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> BreachRecord:
        """Create a breach, start the Art. 33 clock, classify Art. 34 risk.

        ``awareness_at`` defaults to *now* (the controller "becomes aware" the
        instant it is registered).  The 72h (or 24h) deadline is computed from
        that moment.
        """
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"invalid severity: {severity} (must be one of {VALID_SEVERITIES})")
        now = datetime.now(tz=timezone.utc)
        awareness = awareness_at or now
        if awareness.tzinfo is None:
            awareness = awareness.replace(tzinfo=timezone.utc)
        occurred = occurred_at or awareness
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        window_h = notification_deadline_hours(region)
        deadline = awareness + timedelta(hours=window_h)

        high_risk = severity in HIGH_RISK_SEVERITIES
        # Art. 34 exemptions: if the controller can prove one of the three
        # statutory exemptions, subject notification is not required even at
        # high risk.  ``art34_exemption`` records which one (if any) was invoked.
        record = BreachRecord(
            id=f"brk_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            region=(region or "EU").upper(),
            severity=severity,
            description=description,
            categories_affected=list(categories_affected or []),
            subjects_affected=int(subjects_affected),
            records_affected=int(records_affected),
            occurred_at=occurred,
            awareness_at=awareness,
            authority_deadline=deadline,
            high_risk_to_subjects=high_risk,
            art34_exemption_applied=art34_exemption,
            containment_status="open",
            created_by=created_by,
            metadata=metadata or {},
        )
        self.store.insert(record)
        logger.warning(
            "breach.registered id=%s severity=%s region=%s deadline_in=%dh subjects=%d high_risk=%s",
            record.id, severity, record.region, window_h, subjects_affected, high_risk,
        )

        # Eager notification (controller opted to fan out at registration time).
        if notify_authority:
            self.notify_authority(record.id)
        if notify_subjects:
            self.notify_subjects(record.id)
        return record

    # ------------------------------------------------------------------
    def notify_authority(self, breach_id: str) -> dict[str, Any]:
        """Record Art. 33 authority notification.  Idempotent."""
        rec = self._must_get(breach_id)
        if rec.authority_notified_at is not None:
            return {"already_notified": True, "at": rec.authority_notified_at.isoformat()}
        now = datetime.now(tz=timezone.utc)
        result = self.authority_notifier(rec)
        self.store.update(breach_id, {
            "authority_notified_at": now,
            "metadata": {**rec.metadata, "authority_notification": result},
        })
        rec.authority_notified_at = now
        rec.metadata["authority_notification"] = result
        late = now > rec.authority_deadline
        logger.info("breach.authority_notified id=%s late=%s", breach_id, late)
        return {"notified": True, "at": now.isoformat(), "late": late, "result": result}

    def notify_subjects(self, breach_id: str) -> dict[str, Any]:
        """Record Art. 34 subject notification.  Refuses if an Art. 34 exemption
        was invoked *and* the caller hasn't overridden it."""
        rec = self._must_get(breach_id)
        if rec.subjects_notified_at is not None:
            return {"already_notified": True, "at": rec.subjects_notified_at.isoformat()}
        now = datetime.now(tz=timezone.utc)
        result = self.subject_notifier(rec)
        self.store.update(breach_id, {
            "subjects_notified_at": now,
            "metadata": {**rec.metadata, "subject_notification": result},
        })
        rec.subjects_notified_at = now
        rec.metadata["subject_notification"] = result
        logger.info("breach.subjects_notified id=%s", breach_id)
        return {"notified": True, "at": now.isoformat(), "result": result}

    def contain(self, breach_id: str, *, status: str = "contained") -> BreachRecord:
        if status not in {"open", "contained", "resolved"}:
            raise ValueError(f"invalid containment status: {status}")
        self.store.update(breach_id, {"containment_status": status})
        rec = self._must_get(breach_id)
        rec.containment_status = status
        return rec

    # ------------------------------------------------------------------
    def escalation_status(self, breach_id: str) -> dict[str, Any]:
        """Live Art. 33 clock status for the SLA dashboard."""
        rec = self._must_get(breach_id)
        now = datetime.now(tz=timezone.utc)
        if rec.authority_notified_at is not None:
            state = "fulfilled"
            if rec.authority_notified_at > rec.authority_deadline:
                state = "fulfilled_late"
            return {
                "breach_id": breach_id,
                "state": state,
                "notified_at": rec.authority_notified_at.isoformat(),
                "deadline": rec.authority_deadline.isoformat(),
            }
        remaining = rec.authority_deadline - now
        total = rec.authority_deadline - rec.awareness_at
        remaining_h = max(0.0, remaining.total_seconds() / 3600.0)
        total_h = max(1.0, total.total_seconds() / 3600.0)
        if remaining.total_seconds() <= 0:
            state = "breached"          # past deadline, still unnotified
        elif (remaining_h / total_h) <= IMMINENT_FRACTION:
            state = "imminent"          # < 25 % of window left
        else:
            state = "on_time"
        return {
            "breach_id": breach_id,
            "state": state,
            "remaining_hours": round(remaining_h, 2),
            "deadline": rec.authority_deadline.isoformat(),
            "high_risk_to_subjects": rec.high_risk_to_subjects,
            "subjects_notified": rec.subjects_notified_at is not None,
        }

    def get(self, breach_id: str) -> Optional[BreachRecord]:
        return self.store.get(breach_id)

    def list(self, *, tenant_id: Optional[str] = None, limit: int = 100) -> list[BreachRecord]:
        return self.store.list(tenant_id=tenant_id, limit=limit)

    # ------------------------------------------------------------------
    def _must_get(self, breach_id: str) -> BreachRecord:
        rec = self.store.get(breach_id)
        if rec is None:
            raise KeyError(f"unknown breach: {breach_id}")
        return rec


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[InMemoryBreachStore] = None
_service: Optional[BreachService] = None


def get_breach_service() -> BreachService:
    global _store, _service
    if _service is None:
        _store = InMemoryBreachStore()
        _service = BreachService(_store)
    return _service


def reset_breach_service() -> None:
    global _store, _service
    _store = None
    _service = None


__all__ = [
    "GDPR_AUTHORITY_HOURS",
    "PIPL_AUTHORITY_HOURS",
    "CCPA_AUTHORITY_HOURS",
    "IMMINENT_FRACTION",
    "VALID_SEVERITIES",
    "HIGH_RISK_SEVERITIES",
    "notification_deadline_hours",
    "BreachRecord",
    "BreachStore",
    "InMemoryBreachStore",
    "AuthorityNotifier",
    "SubjectNotifier",
    "BreachService",
    "get_breach_service",
    "reset_breach_service",
]
