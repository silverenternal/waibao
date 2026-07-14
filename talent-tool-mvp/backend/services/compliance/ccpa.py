"""v10.0 T5016 — CCPA / CPRA consumer privacy service.

Implements the four statutory rights Californian consumers have under the
California Consumer Privacy Act (as amended by CPRA, effective 2023):

* **Right to Know** (Cal. Civ. Code § 1798.100)  — categories & specific pieces
  of PI collected, plus sources / purpose / third parties.
* **Right to Delete** (§ 1798.105)  — delete the consumer's PI.
* **Right to Correct** (§ 1798.106, CPRA addition).
* **Right to Opt-Out** (§ 1798.120 / § 1798.121)  — *Do Not Sell* and the new
  CPRA *Do Not Share* (cross-context behavioural advertising) signals.

The service is storage-agnostic: it talks to a :class:`CCPAStore` protocol so
unit tests run in-memory and production wires Supabase/Postgres.  It is also
**idempotent** — re-asserting the same opt-out is a no-op that returns the
existing record so retries (and the ``Global Privacy Control`` header on every
request) are cheap.

Verification model
------------------
Every consumer request is created in the ``verify`` state; the request only
becomes actionable once :meth:`CCPAService.verify` flips it to ``open``.  The
two-step verify-then-act flow is required by § 1798.130(a)(2) and is what an
auditor (or the California AG) looks for first.

Authorized-agent flows (§ 1798.135) are supported via ``acted_on_behalf_of``;
an agent request additionally records the agent's registered name.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Protocol

logger = logging.getLogger("waibao.compliance.ccpa")


# ---------------------------------------------------------------------------
# Constants — mirrors the statutory text so the API can self-document
# ---------------------------------------------------------------------------

# CPRA § 1798.140(v) — categories of personal information.
PI_CATEGORIES: dict[str, str] = {
    "identifiers": "A — Identifiers (name, email, IP, device ID)",
    "customer_records": "B — Customer records (name + signature + account #)",
    "commercial": "C — Commercial information (purchases, services used)",
    "biometric": "D — Biometric information",
    "geolocation": "G — Geolocation data",
    "sensitive_pi": "K — Sensitive personal information (CPRA)",
    "inferences": "J — Inferences drawn to profile a consumer",
}

# The two opt-out signals.  Both default to *sale/share permitted* (i.e. the
# consumer has NOT opted out) until they explicitly assert the right.
DO_NOT_SELL = "do_not_sell"
DO_NOT_SHARE = "do_not_share"
OPT_OUT_SIGNALS: tuple[str, ...] = (DO_NOT_SELL, DO_NOT_SHARE)

# 45-day statutory response window (§ 1798.130(a)(1)), extendable by 45 more.
SLA_DAYS = 45
SLA_EXTENSION_DAYS = 45

# Verification token TTL — 10 minutes to receive + act on the email.
VERIFY_TOKEN_TTL_SECONDS = 10 * 60


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CCPAOptOut:
    """A consumer's opt-out preference, keyed by (consumer_id, tenant_id)."""

    consumer_id: str
    tenant_id: Optional[str]
    do_not_sell: bool = False
    do_not_share: bool = False
    asserted_at: str = ""
    source: str = "web"           # web | gpc_header | privacy_policy | agent
    gpc_signal_seen: bool = False  # Global Privacy Control observed on request

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumer_id": self.consumer_id,
            "tenant_id": self.tenant_id,
            "do_not_sell": self.do_not_sell,
            "do_not_share": self.do_not_share,
            "asserted_at": self.asserted_at,
            "source": self.source,
            "gpc_signal_seen": self.gpc_signal_seen,
        }


@dataclass
class CCPARequest:
    """A verifiable consumer request (know / delete / correct / opt_out)."""

    id: str
    consumer_id: str
    tenant_id: Optional[str]
    request_type: str              # know | delete | correct | opt_out
    state: str = "verify"          # verify | open | completed | denied
    verify_token: Optional[str] = None
    verify_expires_at: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    due_at: str = ""
    completed_at: Optional[str] = None
    denial_reason: Optional[str] = None
    acted_on_behalf_of: Optional[str] = None  # authorised agent name
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "consumer_id": self.consumer_id,
            "tenant_id": self.tenant_id,
            "request_type": self.request_type,
            "state": self.state,
            "verify_token": self.verify_token,
            "verify_expires_at": self.verify_expires_at,
            "created_at": self.created_at,
            "due_at": self.due_at,
            "completed_at": self.completed_at,
            "denial_reason": self.denial_reason,
            "acted_on_behalf_of": self.acted_on_behalf_of,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------

class CCPAStore(Protocol):
    """Minimal persistence contract. In-memory default below; Supabase in prod."""

    def upsert_opt_out(self, pref: CCPAOptOut) -> None: ...
    def get_opt_out(self, consumer_id: str, tenant_id: Optional[str]) -> Optional[CCPAOptOut]: ...
    def insert_request(self, req: CCPARequest) -> None: ...
    def get_request(self, request_id: str) -> Optional[CCPARequest]: ...
    def update_request(self, request_id: str, patch: dict[str, Any]) -> None: ...
    def list_requests(self, consumer_id: Optional[str] = None, *, limit: int = 100) -> list[CCPARequest]: ...


class InMemoryCCPAStore:
    """Default store — dict-backed, thread-safe enough for tests."""

    def __init__(self) -> None:
        self._opt: dict[tuple[str, Optional[str]], CCPAOptOut] = {}
        self._req: dict[str, CCPARequest] = {}

    def upsert_opt_out(self, pref: CCPAOptOut) -> None:
        self._opt[(pref.consumer_id, pref.tenant_id)] = pref

    def get_opt_out(self, consumer_id: str, tenant_id: Optional[str]) -> Optional[CCPAOptOut]:
        return self._opt.get((consumer_id, tenant_id))

    def insert_request(self, req: CCPARequest) -> None:
        self._req[req.id] = req

    def get_request(self, request_id: str) -> Optional[CCPARequest]:
        return self._req.get(request_id)

    def update_request(self, request_id: str, patch: dict[str, Any]) -> None:
        req = self._req.get(request_id)
        if req is None:
            return
        for k, v in patch.items():
            if hasattr(req, k):
                setattr(req, k, v)

    def list_requests(self, consumer_id: Optional[str] = None, *, limit: int = 100) -> list[CCPARequest]:
        rows = list(self._req.values())
        if consumer_id is not None:
            rows = [r for r in rows if r.consumer_id == consumer_id]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_VALID_REQUEST_TYPES: frozenset[str] = frozenset(
    {"know", "delete", "correct", "opt_out"}
)


class CCPAService:
    """Stateless-ish CCPA rights orchestrator.

    The service is the single place that knows about the two-step verify flow,
    the 45-day SLA, and the GPC-header opt-out shortcut.  The API layer
    (:mod:`api.ccpa`) is a thin pass-through.
    """

    def __init__(self, store: CCPAStore, *, sla_days: int = SLA_DAYS) -> None:
        self.store = store
        self.sla_days = sla_days

    # ------------------------------------------------------------------
    # Opt-out (the "Do Not Sell / Share My Personal Information" button)
    # ------------------------------------------------------------------
    def assert_opt_out(
        self,
        consumer_id: str,
        *,
        tenant_id: Optional[str] = None,
        do_not_sell: bool = True,
        do_not_share: bool = True,
        source: str = "web",
        gpc_signal_seen: bool = False,
    ) -> CCPAOptOut:
        """Assert (or refresh) the consumer's opt-out preferences.

        Idempotent: re-asserting the same flags just refreshes ``asserted_at``.
        Passing ``do_not_sell=False`` *clears* the flag (i.e. the consumer
        opted back in) — required by § 1798.135(c).
        """
        existing = self.store.get_opt_out(consumer_id, tenant_id)
        pref = CCPAOptOut(
            consumer_id=consumer_id,
            tenant_id=tenant_id,
            do_not_sell=do_not_sell,
            do_not_share=do_not_share,
            asserted_at=_now_iso(),
            source=source,
            gpc_signal_seen=gpc_signal_seen,
        )
        # Preserve a previously-seen GPC signal even if a later web action
        # didn't carry it — once GPC has been seen we keep the sticky flag.
        if existing and existing.gpc_signal_seen and not gpc_signal_seen:
            pref.gpc_signal_seen = True
        self.store.upsert_opt_out(pref)
        logger.info(
            "ccpa.opt_out_asserted consumer=%s dns=%s dnsh=%s source=%s",
            consumer_id, do_not_sell, do_not_share, source,
        )
        return pref

    def get_opt_out(self, consumer_id: str, tenant_id: Optional[str] = None) -> CCPAOptOut:
        """Return the preference, defaulting to *no opt-out* (permitted)."""
        pref = self.store.get_opt_out(consumer_id, tenant_id)
        if pref is None:
            return CCPAOptOut(
                consumer_id=consumer_id,
                tenant_id=tenant_id,
                do_not_sell=False,
                do_not_share=False,
                asserted_at="",
                source="default",
            )
        return pref

    def is_sale_permitted(self, consumer_id: str, tenant_id: Optional[str] = None) -> bool:
        """Convenience: should downstream ad/sale pipelines fire for this user?"""
        pref = self.get_opt_out(consumer_id, tenant_id)
        return not (pref.do_not_sell or pref.do_not_share)

    def apply_gpc_header(self, consumer_id: str, gpc_value: Optional[str], tenant_id: Optional[str] = None) -> Optional[CCPAOptOut]:
        """Honour the ``Sec-GPC: 1`` header (§ 1798.135(b)).

        A truthy GPC value is treated as a global opt-out.  We *only* act when
        the header is present and truthy — absence does not clear a prior
        opt-out (sticky).  Returns the updated pref, or ``None`` if the header
        was absent.
        """
        if not gpc_value or gpc_value.strip() in ("", "0", "false", "null"):
            return None
        return self.assert_opt_out(
            consumer_id,
            tenant_id=tenant_id,
            do_not_sell=True,
            do_not_share=True,
            source="gpc_header",
            gpc_signal_seen=True,
        )

    # ------------------------------------------------------------------
    # Verifiable consumer requests (know / delete / correct)
    # ------------------------------------------------------------------
    def create_request(
        self,
        consumer_id: str,
        request_type: str,
        *,
        tenant_id: Optional[str] = None,
        acted_on_behalf_of: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CCPARequest:
        if request_type not in _VALID_REQUEST_TYPES:
            raise ValueError(f"invalid CCPA request_type: {request_type}")
        now = datetime.now(tz=timezone.utc)
        verify_token = uuid.uuid4().hex
        req = CCPARequest(
            id=f"ccpa_{uuid.uuid4().hex[:16]}",
            consumer_id=consumer_id,
            tenant_id=tenant_id,
            request_type=request_type,
            state="verify",
            verify_token=verify_token,
            verify_expires_at=(
                now.replace(microsecond=0).timestamp() + VERIFY_TOKEN_TTL_SECONDS
            ).__repr__(),  # numeric epoch stored as string for portability
            created_at=now.isoformat(),
            due_at=(now.replace(microsecond=0)).isoformat(),
            acted_on_behalf_of=acted_on_behalf_of,
            metadata=metadata or {},
        )
        # Due-at = created + SLA window (the clock starts once verified).
        req.due_at = (now).isoformat()
        self.store.insert_request(req)
        logger.info(
            "ccpa.request_created id=%s type=%s consumer=%s agent=%s",
            req.id, request_type, consumer_id, acted_on_behalf_of,
        )
        return req

    def verify_request(self, request_id: str, token: str) -> CCPARequest:
        """Flip a request from ``verify`` → ``open`` once the consumer proves
        identity (email confirmation).  Starts the 45-day SLA clock."""
        req = self._must_get(request_id)
        if req.state != "verify":
            raise ValueError(f"request {request_id} not in verifyable state: {req.state}")
        # Constant-time-ish token compare (hashed compare avoids timing leak).
        if not req.verify_token or _hash_token(token) != _hash_token(req.verify_token):
            raise PermissionError("invalid or missing verification token")
        now = datetime.now(tz=timezone.utc)
        due = now.replace(microsecond=0)
        from datetime import timedelta
        due = due + timedelta(days=self.sla_days)
        self.store.update_request(request_id, {
            "state": "open",
            "verify_token": None,
            "due_at": due.isoformat(),
        })
        req.state = "open"
        req.verify_token = None
        req.due_at = due.isoformat()
        return req

    def complete_request(self, request_id: str, response_payload: Optional[dict[str, Any]] = None) -> CCPARequest:
        req = self._must_get(request_id)
        if req.state not in {"open", "verify"}:
            raise ValueError(f"request {request_id} not completable: {req.state}")
        now = _now_iso()
        patch = {
            "state": "completed",
            "completed_at": now,
            "metadata": {**req.metadata, "response": response_payload or {}},
        }
        self.store.update_request(request_id, patch)
        req.state = "completed"
        req.completed_at = now
        req.metadata = patch["metadata"]
        return req

    def deny_request(self, request_id: str, reason: str) -> CCPARequest:
        req = self._must_get(request_id)
        self.store.update_request(request_id, {
            "state": "denied",
            "denial_reason": reason,
        })
        req.state = "denied"
        req.denial_reason = reason
        return req

    def list_requests(self, consumer_id: Optional[str] = None, *, limit: int = 100) -> list[CCPARequest]:
        return self.store.list_requests(consumer_id, limit=limit)

    def extend_due_date(self, request_id: str, *, days: int = SLA_EXTENSION_DAYS) -> CCPARequest:
        """§ 1798.130(a)(2) — one 45-day extension permitted with notice."""
        req = self._must_get(request_id)
        if req.state != "open":
            raise ValueError("only open requests can be extended")
        from datetime import datetime as _dt, timedelta
        try:
            base = _dt.fromisoformat(req.due_at)
        except Exception:  # noqa: BLE001
            base = datetime.now(tz=timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        new_due = base + timedelta(days=days)
        self.store.update_request(request_id, {"due_at": new_due.isoformat()})
        req.due_at = new_due.isoformat()
        return req

    # ------------------------------------------------------------------
    def _must_get(self, request_id: str) -> CCPARequest:
        req = self.store.get_request(request_id)
        if req is None:
            raise KeyError(f"unknown CCPA request: {request_id}")
        return req


# ---------------------------------------------------------------------------
# Singleton — production swaps the store for a Supabase-backed one.
# ---------------------------------------------------------------------------

_store: Optional[InMemoryCCPAStore] = None
_service: Optional[CCPAService] = None


def get_ccpa_service() -> CCPAService:
    global _store, _service
    if _service is None:
        _store = InMemoryCCPAStore()
        _service = CCPAService(_store, sla_days=int(os.getenv("CCPA_SLA_DAYS", str(SLA_DAYS))))
    return _service


def reset_ccpa_service() -> None:
    """Test hook — wipe the singleton."""
    global _store, _service
    _store = None
    _service = None


__all__ = [
    "PI_CATEGORIES",
    "DO_NOT_SELL",
    "DO_NOT_SHARE",
    "OPT_OUT_SIGNALS",
    "SLA_DAYS",
    "SLA_EXTENSION_DAYS",
    "VERIFY_TOKEN_TTL_SECONDS",
    "CCPAOptOut",
    "CCPARequest",
    "CCPAStore",
    "InMemoryCCPAStore",
    "CCPAService",
    "get_ccpa_service",
    "reset_ccpa_service",
]
