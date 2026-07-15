"""T6109 — Recruitment flow service (contact logs + interview schedule).

Tracks the downstream recruitment lifecycle after a talent↔role
recommendation (T6104) has been pushed to an employer:

* ``contact_logs``       — every outreach attempt (phone / email / wechat /
  video …) against a candidate, with method, outcome status and notes;
* ``interview_schedule`` — a booked interview slot (date / time / location /
  format) for a candidate↔role, moving scheduled → completed | cancelled |
  no_show | rescheduled.

Both stores are org-scoped. The service degrades gracefully to an in-memory
store when Supabase is unreachable (dev without a running DB) and seeds a
small demo funnel so the kanban UI is never blank.

Usage:
    from services.matching.recruitment_flow import (
        ContactLog,
        InterviewSlot,
        RecruitmentFlowService,
        get_service,
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("recruittech.services.recruitment_flow")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _as_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {**obj.__dict__}
    return dict(obj)


# ---------------------------------------------------------------------------
# data models
# ---------------------------------------------------------------------------

@dataclass
class ContactLog:
    """One outreach attempt to a candidate."""

    id: str
    candidate_id: str
    role_id: str = ""
    org_id: str = ""
    hr_id: str = ""
    contact_method: str = "phone"
    contact_date: str = ""
    status: str = "reached"
    notes: str = ""
    candidate_name: str = ""
    role_title: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterviewSlot:
    """A booked interview slot for a candidate↔role."""

    id: str
    candidate_id: str
    role_id: str = ""
    org_id: str = ""
    hr_id: str = ""
    date: str = ""
    time: str = ""
    location: str = ""
    format: str = "onsite"
    status: str = "scheduled"
    candidate_name: str = ""
    role_title: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# row coercion (Supabase → dataclass)
# ---------------------------------------------------------------------------

_CONTACT_COLUMNS = (
    "id,candidate_id,role_id,org_id,hr_id,contact_method,contact_date,"
    "status,notes,candidate_name,role_title,created_at,updated_at"
)
_INTERVIEW_COLUMNS = (
    "id,candidate_id,role_id,org_id,hr_id,date,time,location,format,"
    "status,candidate_name,role_title,created_at,updated_at"
)


def _row_to_contact(row: dict[str, Any]) -> ContactLog:
    return ContactLog(
        id=str(row.get("id")),
        candidate_id=str(row.get("candidate_id") or ""),
        role_id=str(row.get("role_id") or ""),
        org_id=str(row.get("org_id") or ""),
        hr_id=str(row.get("hr_id") or ""),
        contact_method=row.get("contact_method") or "phone",
        contact_date=str(row.get("contact_date") or _today()),
        status=row.get("status") or "reached",
        notes=row.get("notes") or "",
        candidate_name=row.get("candidate_name") or "",
        role_title=row.get("role_title") or "",
        created_at=str(row.get("created_at") or _now_iso()),
        updated_at=str(row.get("updated_at") or _now_iso()),
    )


def _row_to_interview(row: dict[str, Any]) -> InterviewSlot:
    return InterviewSlot(
        id=str(row.get("id")),
        candidate_id=str(row.get("candidate_id") or ""),
        role_id=str(row.get("role_id") or ""),
        org_id=str(row.get("org_id") or ""),
        hr_id=str(row.get("hr_id") or ""),
        date=str(row.get("date") or _today()),
        time=str(row.get("time") or "10:00"),
        location=row.get("location") or "",
        format=row.get("format") or "onsite",
        status=row.get("status") or "scheduled",
        candidate_name=row.get("candidate_name") or "",
        role_title=row.get("role_title") or "",
        created_at=str(row.get("created_at") or _now_iso()),
        updated_at=str(row.get("updated_at") or _now_iso()),
    )


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------

class RecruitmentFlowService:
    """CRUD over ``contact_logs`` + ``interview_schedule``."""

    CONTACT_TABLE = "contact_logs"
    INTERVIEW_TABLE = "interview_schedule"

    def __init__(self, supabase: Any = None) -> None:
        # supabase admin client is optional — injected for tests, lazily
        # resolved from api.deps in production. A client that fails its first
        # round-trip is cached as None so the service degrades to an in-memory
        # store for the rest of its life (dev without a running DB).
        self._supabase = supabase
        self._probed = supabase is not None
        # in-memory fallback stores keyed by id (dev/test only)
        self._contacts: dict[str, ContactLog] = {}
        self._interviews: dict[str, InterviewSlot] = {}
        self._seq = 0
        self._seeded_orgs: set[str] = set()

    # -- client resolution -------------------------------------------------

    def _sb(self):
        if self._probed:
            return self._supabase
        self._probed = True
        try:
            from api.deps import get_supabase_admin

            client = get_supabase_admin()
            client.table(self.CONTACT_TABLE).select("id").limit(1).execute()
            self._supabase = client
        except Exception as exc:  # pragma: no cover - dev fallback
            logger.info("recruitment_flow: Supabase unavailable, using memory store: %s", exc)
            self._supabase = None
        return self._supabase

    def _next_id(self) -> str:
        self._seq += 1
        return str(self._seq)

    # ===================================================================
    # contact logs
    # ===================================================================

    async def add_contact(self, payload: dict[str, Any]) -> ContactLog:
        payload = {**payload}
        now = _now_iso()
        # coalesce None → defaults (API may pass contact_date=None etc.)
        if not payload.get("contact_date"):
            payload["contact_date"] = _today()
        if not payload.get("status"):
            payload["status"] = "reached"
        if not payload.get("contact_method"):
            payload["contact_method"] = "phone"
        payload.setdefault("notes", "")
        if payload.get("notes") is None:
            payload["notes"] = ""
        sb = self._sb()
        if sb is not None:
            try:
                res = (
                    sb.table(self.CONTACT_TABLE)
                    .insert(payload)
                    .execute()
                )
                if res.data:
                    return _row_to_contact(res.data[0])
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: contact insert failed, memory: %s", exc)
        return self._add_contact_memory(payload, now)

    def _add_contact_memory(self, payload: dict[str, Any], now: str) -> ContactLog:
        log = ContactLog(
            id=self._next_id(),
            candidate_id=payload["candidate_id"],
            role_id=payload.get("role_id", ""),
            org_id=payload.get("org_id", ""),
            hr_id=payload.get("hr_id", ""),
            contact_method=payload.get("contact_method", "phone"),
            contact_date=payload.get("contact_date", _today()),
            status=payload.get("status", "reached"),
            notes=payload.get("notes", ""),
            candidate_name=payload.get("candidate_name", ""),
            role_title=payload.get("role_title", ""),
            created_at=now,
            updated_at=now,
        )
        self._contacts[log.id] = log
        return log

    async def list_contacts(
        self,
        *,
        org_id: str,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContactLog]:
        sb = self._sb()
        if sb is not None:
            try:
                q = (
                    sb.table(self.CONTACT_TABLE)
                    .select(_CONTACT_COLUMNS)
                    .eq("org_id", org_id)
                )
                if candidate_id:
                    q = q.eq("candidate_id", candidate_id)
                if status:
                    q = q.eq("status", status)
                res = (
                    q.order("contact_date", desc=True)
                    .order("created_at", desc=True)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                if res.data is not None:
                    return [_row_to_contact(r) for r in res.data]
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: contact list failed, memory: %s", exc)
        return self._list_contacts_memory(org_id, candidate_id, status, limit, offset)

    def _list_contacts_memory(
        self,
        org_id: str,
        candidate_id: Optional[str],
        status: Optional[str],
        limit: int,
        offset: int,
    ) -> list[ContactLog]:
        self._seed_if_empty(org_id)
        rows = [c for c in self._contacts.values() if c.org_id == org_id]
        if candidate_id:
            rows = [c for c in rows if c.candidate_id == candidate_id]
        if status:
            rows = [c for c in rows if c.status == status]
        rows.sort(key=lambda c: (c.contact_date, c.created_at), reverse=True)
        return rows[offset : offset + limit]

    # ===================================================================
    # interview schedule
    # ===================================================================

    async def schedule_interview(self, payload: dict[str, Any]) -> InterviewSlot:
        payload = {**payload}
        now = _now_iso()
        payload.setdefault("date", _today())
        payload.setdefault("time", "10:00")
        payload.setdefault("location", "")
        payload.setdefault("format", "onsite")
        payload.setdefault("status", "scheduled")
        sb = self._sb()
        if sb is not None:
            try:
                res = (
                    sb.table(self.INTERVIEW_TABLE)
                    .insert(payload)
                    .execute()
                )
                if res.data:
                    return _row_to_interview(res.data[0])
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: interview insert failed, memory: %s", exc)
        return self._schedule_interview_memory(payload, now)

    def _schedule_interview_memory(self, payload: dict[str, Any], now: str) -> InterviewSlot:
        slot = InterviewSlot(
            id=self._next_id(),
            candidate_id=payload["candidate_id"],
            role_id=payload.get("role_id", ""),
            org_id=payload.get("org_id", ""),
            hr_id=payload.get("hr_id", ""),
            date=payload.get("date", _today()),
            time=payload.get("time", "10:00"),
            location=payload.get("location", ""),
            format=payload.get("format", "onsite"),
            status=payload.get("status", "scheduled"),
            candidate_name=payload.get("candidate_name", ""),
            role_title=payload.get("role_title", ""),
            created_at=now,
            updated_at=now,
        )
        self._interviews[slot.id] = slot
        return slot

    async def list_interviews(
        self,
        *,
        org_id: str,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InterviewSlot]:
        sb = self._sb()
        if sb is not None:
            try:
                q = (
                    sb.table(self.INTERVIEW_TABLE)
                    .select(_INTERVIEW_COLUMNS)
                    .eq("org_id", org_id)
                )
                if candidate_id:
                    q = q.eq("candidate_id", candidate_id)
                if status:
                    q = q.eq("status", status)
                res = (
                    q.order("date", desc=True)
                    .order("time", desc=False)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                if res.data is not None:
                    return [_row_to_interview(r) for r in res.data]
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: interview list failed, memory: %s", exc)
        return self._list_interviews_memory(org_id, candidate_id, status, limit, offset)

    def _list_interviews_memory(
        self,
        org_id: str,
        candidate_id: Optional[str],
        status: Optional[str],
        limit: int,
        offset: int,
    ) -> list[InterviewSlot]:
        self._seed_if_empty(org_id)
        rows = [s for s in self._interviews.values() if s.org_id == org_id]
        if candidate_id:
            rows = [s for s in rows if s.candidate_id == candidate_id]
        if status:
            rows = [s for s in rows if s.status == status]
        rows.sort(key=lambda s: (s.date, s.time), reverse=True)
        return rows[offset : offset + limit]

    async def update_interview_status(
        self, interview_id: str, status: str
    ) -> Optional[InterviewSlot]:
        if not status:
            raise ValueError("status is required")
        sb = self._sb()
        if sb is not None:
            try:
                res = (
                    sb.table(self.INTERVIEW_TABLE)
                    .update({"status": status, "updated_at": _now_iso()})
                    .eq("id", interview_id)
                    .execute()
                )
                if res.data:
                    return _row_to_interview(res.data[0])
                return None
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: interview update failed, memory: %s", exc)
        slot = self._interviews.get(str(interview_id))
        if slot is None:
            return None
        slot.status = status
        slot.updated_at = _now_iso()
        return slot

    async def get_interview(self, interview_id: str) -> Optional[InterviewSlot]:
        sb = self._sb()
        if sb is not None:
            try:
                res = (
                    sb.table(self.INTERVIEW_TABLE)
                    .select(_INTERVIEW_COLUMNS)
                    .eq("id", interview_id)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return _row_to_interview(res.data[0])
                return None
            except Exception as exc:  # pragma: no cover - dev fallback
                logger.warning("recruitment_flow: interview get failed, memory: %s", exc)
        return self._interviews.get(str(interview_id))

    # ===================================================================
    # kanban: merge contacts + interviews into a per-candidate funnel
    # ===================================================================

    async def kanban(self, *, org_id: str) -> dict[str, Any]:
        """Aggregate contacts + interviews into a candidate-centric funnel.

        Each candidate appears once with their latest contact status and
        interview status so the kanban can place the card in the right
        column: contacted → interviewing → result.
        """
        contacts = await self.list_contacts(org_id=org_id, limit=200)
        interviews = await self.list_interviews(org_id=org_id, limit=200)

        candidates: dict[str, dict[str, Any]] = {}
        for c in contacts:
            entry = candidates.setdefault(
                c.candidate_id,
                {
                    "candidate_id": c.candidate_id,
                    "candidate_name": c.candidate_name,
                    "role_id": c.role_id,
                    "role_title": c.role_title,
                    "contact_status": None,
                    "last_contact_date": None,
                    "interview_status": None,
                    "next_interview": None,
                    "contacts": [],
                    "interviews": [],
                },
            )
            entry["candidate_name"] = entry["candidate_name"] or c.candidate_name
            entry["role_title"] = entry["role_title"] or c.role_title
            entry["role_id"] = entry["role_id"] or c.role_id
            entry["contacts"].append(c.to_dict())
            if (
                entry["last_contact_date"] is None
                or c.contact_date > entry["last_contact_date"]
            ):
                entry["last_contact_date"] = c.contact_date
                entry["contact_status"] = c.status

        for s in interviews:
            entry = candidates.setdefault(
                s.candidate_id,
                {
                    "candidate_id": s.candidate_id,
                    "candidate_name": s.candidate_name,
                    "role_id": s.role_id,
                    "role_title": s.role_title,
                    "contact_status": None,
                    "last_contact_date": None,
                    "interview_status": None,
                    "next_interview": None,
                    "contacts": [],
                    "interviews": [],
                },
            )
            entry["candidate_name"] = entry["candidate_name"] or s.candidate_name
            entry["role_title"] = entry["role_title"] or s.role_title
            entry["role_id"] = entry["role_id"] or s.role_id
            entry["interviews"].append(s.to_dict())
            # the most recent interview drives the interview_status; the
            # nearest upcoming scheduled slot drives next_interview.
            if (
                entry["interview_status"] is None
                or s.date > entry.get("_iv_date", "")
            ):
                entry["interview_status"] = s.status
                entry["_iv_date"] = s.date
            if s.status == "scheduled" and (
                entry["next_interview"] is None
                or f"{s.date} {s.time}" < entry["next_interview"]
            ):
                entry["next_interview"] = f"{s.date} {s.time}"

        for entry in candidates.values():
            entry.pop("_iv_date", None)
            # derive a kanban column from the funnel stage
            entry["stage"] = self._derive_stage(entry)

        return {
            "org_id": org_id,
            "candidates": list(candidates.values()),
            "totals": {
                "contacted": sum(1 for e in candidates.values() if e["contact_status"]),
                "interviewing": sum(
                    1 for e in candidates.values() if e["interview_status"]
                ),
                "completed": sum(
                    1
                    for e in candidates.values()
                    if e["interview_status"] in ("completed", "no_show")
                ),
            },
        }

    @staticmethod
    def _derive_stage(entry: dict[str, Any]) -> str:
        iv = entry.get("interview_status")
        if iv in ("completed", "no_show"):
            return "result"
        if iv in ("scheduled", "rescheduled"):
            return "interview"
        return "contact"

    # ===================================================================
    # demo seeding (memory fallback only)
    # ===================================================================

    def _seed_if_empty(self, org_id: str) -> None:
        if org_id in self._seeded_orgs:
            return
        if self._contacts or self._interviews:
            self._seeded_orgs.add(org_id)
            return
        now = _now_iso()
        today = _today()
        demo = [
            ("c-101", "张*", "后端工程师", "phone", "interested", "scheduled", "10:00"),
            ("c-102", "李*", "产品经理", "wechat", "reached", None, None),
            ("c-103", "王*", "前端工程师", "email", "no_answer", None, None),
        ]
        for cid, name, role, method, cstatus, istatus, itime in demo:
            self._seq += 1
            self._contacts[str(self._seq)] = ContactLog(
                id=str(self._seq),
                candidate_id=cid,
                org_id=org_id,
                candidate_name=name,
                role_title=role,
                contact_method=method,
                contact_date=today,
                status=cstatus,
                notes="",
                created_at=now,
                updated_at=now,
            )
            if istatus:
                self._seq += 1
                self._interviews[str(self._seq)] = InterviewSlot(
                    id=str(self._seq),
                    candidate_id=cid,
                    org_id=org_id,
                    candidate_name=name,
                    role_title=role,
                    date=today,
                    time=itime or "10:00",
                    location="线上会议室",
                    format="video" if cid == "c-101" else "onsite",
                    status=istatus,
                    created_at=now,
                    updated_at=now,
                )
        self._seeded_orgs.add(org_id)


# ---------------------------------------------------------------------------
# singleton
# ---------------------------------------------------------------------------

_service: Optional[RecruitmentFlowService] = None


def get_service() -> RecruitmentFlowService:
    global _service
    if _service is None:
        _service = RecruitmentFlowService()
    return _service


def reset_service(supabase: Any = None) -> RecruitmentFlowService:
    """Test helper: replace the singleton with a fresh instance."""
    global _service
    _service = RecruitmentFlowService(supabase=supabase)
    return _service
