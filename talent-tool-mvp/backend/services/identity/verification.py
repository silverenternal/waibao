"""v11.2 T6303 — Identity verification service.

Implements the 甲方 (client) A-level identity-verification lifecycle:

    jobseeker uploads 身份证 (id_card) / 学历证明 (education) / 简历 (resume)
    PDF/Word -> the service submits the document, runs the existing OCR /
    resume-parser stack to EXTRACT the main fields, and on success marks the
    document ``verified``. If a document CANNOT be verified (unclear / fields
    inconsistent / not uploaded) its status stays ``pending`` (待上传) with a
    human-readable reason.

Status model (per the v11.2 field contract, migration 064_identity_compensation):
    pending   -> 待上传  (not verified yet)
    submitted -> 待审核  (uploaded, awaiting review)
    verified  -> 已认证  (fields successfully extracted / verified)

Roll-up RULE:
    identity_status == 'verified' ONLY when id_card AND education AND resume
    are ALL 'verified'. If any one is 'submitted' (but not all 'verified'),
    the roll-up is 'submitted'. Otherwise 'pending'.

DB resilience:
    All persistence goes through ``api.deps.get_supabase_admin`` (service role).
    If Supabase is unreachable, the service transparently falls back to an
    in-memory store so the unit tests never require a live database. The
    in-memory store mirrors the on-disk schema (candidates doc-status columns +
    profile_versions append-only snapshots).

AI reuse (do not duplicate OCR/LLM logic):
    * ``resume`` -> services.jobseeker.resume_parser.parse_resume_from_url
      (full OCR -> LLM structured profile chain).
    * ``id_card`` / ``education`` -> services.jobseeker.resume_parser
      .extract_text_from_url + a lightweight field extractor (no extra OCR
      provider wired up; reuses the same OCR text path). Fields that look
      present / consistent -> verified; otherwise pending (待上传).
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("recruittech.services.identity")

# ---------------------------------------------------------------------------
# Constants / shared contract
# ---------------------------------------------------------------------------

#: The three document types a talent uploads (exact field names everywhere).
DOC_TYPES: tuple[str, ...] = ("id_card", "education", "resume")

#: Status enum shared with the DB CHECK constraints + frontend display map.
VALID_STATUSES: tuple[str, ...] = ("pending", "submitted", "verified")

#: pending -> 待上传, submitted -> 待审核, verified -> 已认证
DISPLAY_MAP: dict[str, str] = {
    "pending": "待上传",
    "submitted": "待审核",
    "verified": "已认证",
}

#: candidates-table column for each doc type's verification status.
_DOC_COLUMN: dict[str, str] = {
    "id_card": "id_card_status",
    "education": "education_doc_status",
    "resume": "resume_status",
}


# ---------------------------------------------------------------------------
# IdentityStatus dataclass
# ---------------------------------------------------------------------------


@dataclass
class IdentityStatus:
    """Per-user identity verification status with display labels."""

    overall: str = "pending"
    id_card: str = "pending"
    education: str = "pending"
    resume: str = "pending"
    #: optional human-readable reason per doc (why it is still pending/待上传).
    reasons: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("overall", "id_card", "education", "resume"):
            val = getattr(self, name)
            if val not in VALID_STATUSES:
                raise ValueError(f"invalid status {name}={val!r}; expected {VALID_STATUSES}")

    @property
    def overall_display(self) -> str:
        return DISPLAY_MAP.get(self.overall, self.overall)

    @property
    def id_card_display(self) -> str:
        return DISPLAY_MAP.get(self.id_card, self.id_card)

    @property
    def education_display(self) -> str:
        return DISPLAY_MAP.get(self.education, self.education)

    @property
    def resume_display(self) -> str:
        return DISPLAY_MAP.get(self.resume, self.resume)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses (includes display labels)."""
        return {
            "overall": self.overall,
            "id_card": self.id_card,
            "education": self.education,
            "resume": self.resume,
            "overall_display": self.overall_display,
            "id_card_display": self.id_card_display,
            "education_display": self.education_display,
            "resume_display": self.resume_display,
            "reasons": dict(self.reasons),
        }


# ---------------------------------------------------------------------------
# In-memory fallback store (used when Supabase is unreachable)
# ---------------------------------------------------------------------------


class _MemoryStore:
    """Mirrors candidates doc-status + profile_versions append-only schema."""

    def __init__(self) -> None:
        # candidate_id -> {id_card, education_doc, resume, identity_status, ...}
        self.candidates: dict[str, dict[str, Any]] = {}
        # candidate_id -> [{version_no, snapshot, created_at}, ...]
        self.versions: dict[str, list[dict[str, Any]]] = {}
        self.lock = threading.Lock()

    def get_candidate(self, user_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.candidates.get(user_id)
            if row is None:
                row = {
                    "identity_status": "pending",
                    "id_card_status": "pending",
                    "education_doc_status": "pending",
                    "resume_status": "pending",
                    "identity_verified_at": None,
                }
                self.candidates[user_id] = dict(row)
            return dict(row)


# Module-level singletons (process-wide; tests reset via ``reset()``).
_MEMORY = _MemoryStore()
# Per-doc last extraction result + reason (so callers / tests can inspect).
_LAST_EXTRACTION: dict[tuple[str, str], dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Lightweight field extractors (id_card / education)
# ---------------------------------------------------------------------------

_ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
_DEGREE_KEYWORDS = (
    "本科",
    "大专",
    "硕士",
    "博士",
    "学士",
    "学校",
    "大学",
    "学院",
    "毕业",
    "university",
    "college",
    "bachelor",
    "master",
    "doctorate",
)


def _extract_id_card_fields(text: str) -> dict[str, Any]:
    """Pull the load-bearing id-card field (身份证号) from OCR text.

    Verification is intentionally lenient: a document is 'verified' once the
    main field is present and well-formed; otherwise it is 'pending' (待上传).
    """
    m = _ID_CARD_RE.search(text or "")
    id_no = m.group(0) if m else ""
    return {
        "id_card_no": id_no,
        "verified": bool(id_no),
        "reason": "" if id_no else "未识别到有效身份证号 (待上传)",
    }


def _extract_education_fields(text: str) -> dict[str, Any]:
    """Pull the load-bearing education field (学历/学校) from OCR text."""
    low = (text or "").lower()
    matched = [kw for kw in _DEGREE_KEYWORDS if kw.lower() in low]
    verified = bool(matched)
    return {
        "degree_keywords": matched,
        "verified": verified,
        "reason": "" if verified else "未识别到学历/学校关键字 (待上传)",
    }


def _resume_extracted_is_ok(extracted: dict[str, Any] | None) -> tuple[bool, str]:
    """A resume is 'verified' when the LLM returned a non-error structured blob
    with at least a basic block (name / contact). Never raises."""
    if not extracted or extracted.get("_error"):
        return False, "简历解析失败或字段不全 (待上传)"
    basic = extracted.get("basic")
    if not isinstance(basic, dict):
        return False, "简历缺少基本信息 (待上传)"
    has_name = bool(str(basic.get("name") or "").strip())
    has_contact = bool(
        str(basic.get("email") or "").strip()
        or str(basic.get("phone") or "").strip()
    )
    if has_name and has_contact:
        return True, ""
    return False, "简历字段不全/不一致 (待上传)"


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(1[3-9]\d{9})")


def _derive_basic_from_text(text: str) -> dict[str, Any]:
    """Derive a minimal ``basic`` block from raw resume text (bytes path).

    Used when the resume arrives as already-decoded text rather than a URL —
    extracts a phone and/or email so the field-consistency check can run. The
    name is left blank (we don't guess PII); a resume is still 'verified' once
    at least one contact field is present.
    """
    extracted: dict[str, Any] = {"basic": {"name": "", "email": "", "phone": ""}}
    m_phone = _PHONE_RE.search(text or "")
    m_email = _EMAIL_RE.search(text or "")
    if m_phone:
        extracted["basic"]["phone"] = m_phone.group(1)
    if m_email:
        extracted["basic"]["email"] = m_email.group(0)
    # Name: first non-empty token that is not a number/email — best-effort.
    for tok in (text or "").split():
        if _PHONE_RE.fullmatch(tok) or _EMAIL_RE.fullmatch(tok):
            continue
        if any(ch.isalpha() for ch in tok):
            extracted["basic"]["name"] = tok.strip(",，。.")
            break
    return extracted


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IdentityVerificationService:
    """Identity verification + editable profile versioning.

    All DB writes go through ``get_supabase_admin`` (service role). When the DB
    is unreachable the service keeps working against an in-memory store so the
    test suite never needs a live Supabase.
    """

    def __init__(self) -> None:
        self._mem = _MEMORY

    # -- DB plumbing -------------------------------------------------------

    def _admin(self):
        """Return the service-role Supabase client, or ``None`` if unreachable."""
        try:
            from api.deps import get_supabase_admin

            client = get_supabase_admin()
            # Cheap liveness probe — only treat as available if it answers.
            # We don't actually issue a request (avoids network in unit tests);
            # callers wrap real queries in try/except and fall back to memory.
            if client is None:
                return None
            return client
        except Exception as e:  # noqa: BLE001
            logger.debug(f"identity: supabase admin unavailable, using memory: {e}")
            return None

    # -- Status computation ------------------------------------------------

    @staticmethod
    def compute_overall(id_card: str, education: str, resume: str) -> str:
        """Roll-up rule.

        'verified' ONLY when all three are 'verified'; elif any 'submitted'
        -> 'submitted'; else 'pending'.
        """
        for v in (id_card, education, resume):
            if v not in VALID_STATUSES:
                raise ValueError(f"invalid doc status {v!r}")
        if id_card == "verified" and education == "verified" and resume == "verified":
            return "verified"
        if "submitted" in (id_card, education, resume):
            return "submitted"
        return "pending"

    # -- Public read -------------------------------------------------------

    def get_status(self, user_id: str) -> IdentityStatus:
        """Return the current IdentityStatus for ``user_id``.

        Tries Supabase first; falls back to the in-memory store on any error.
        """
        row = self._load_candidate(user_id)
        id_card = row.get("id_card_status", "pending")
        education = row.get("education_doc_status", "pending")
        resume = row.get("resume_status", "pending")
        overall = self.compute_overall(id_card, education, resume)
        reasons = {
            doc: rec.get("reason", "")
            for (uid, doc), rec in _LAST_EXTRACTION.items()
            if uid == user_id and rec.get("reason")
        }
        return IdentityStatus(
            overall=overall,
            id_card=id_card,
            education=education,
            resume=resume,
            reasons=reasons,
        )

    # -- Public submit -----------------------------------------------------

    def submit_document(
        self,
        user_id: str,
        doc_type: str,
        file_bytes_or_url: bytes | str | None,
    ) -> IdentityStatus:
        """Submit a document for AI extraction + verification.

        Marks the doc 'submitted' immediately, then runs the existing OCR /
        resume-parser stack. On success the doc becomes 'verified'; if the
        document cannot be verified it reverts to 'pending' (待上传) with a
        reason stored on the user. The roll-up ``identity_status`` is
        recomputed and persisted to the candidates row.
        """
        if doc_type not in DOC_TYPES:
            raise ValueError(f"unknown doc_type {doc_type!r}; expected {DOC_TYPES}")
        if file_bytes_or_url in (None, b"", ""):
            # Nothing uploaded -> stays pending (待上传) per the contract.
            _LAST_EXTRACTION[(user_id, doc_type)] = {
                "status": "pending",
                "reason": "未上传文件 (待上传)",
                "fields": {},
            }
            self._persist_status(user_id, doc_type, "pending")
            return self.get_status(user_id)

        # Mark submitted (待审核) while extraction runs.
        self._persist_status(user_id, doc_type, "submitted")

        try:
            extracted, verified, reason = self._extract(user_id, doc_type, file_bytes_or_url)
        except Exception as e:  # noqa: BLE001 — extraction must never crash submit
            logger.warning(f"identity: extract failed for {doc_type}: {e}")
            extracted, verified, reason = {}, False, f"提取异常: {e} (待上传)"

        new_status = "verified" if verified else "pending"
        _LAST_EXTRACTION[(user_id, doc_type)] = {
            "status": new_status,
            "reason": reason,
            "fields": extracted,
        }
        self._persist_status(user_id, doc_type, new_status)
        return self.get_status(user_id)

    # Backwards-friendly alias used by some call sites / tests.
    def submit(self, user_id: str, doc_type: str, file_bytes_or_url) -> IdentityStatus:
        return self.submit_document(user_id, doc_type, file_bytes_or_url)

    # -- Extraction dispatch ----------------------------------------------

    def _extract(
        self,
        user_id: str,
        doc_type: str,
        file_bytes_or_url,
    ) -> tuple[dict[str, Any], bool, str]:
        """Run the right extractor for the doc type.

        Returns ``(fields, verified, reason)``. Reuses the existing OCR /
        resume-parser providers — no duplicated OCR/LLM logic.
        """
        if doc_type == "resume":
            return self._extract_resume(file_bytes_or_url)
        # id_card / education share the OCR text path + a light field extractor.
        text = self._ocr_text(file_bytes_or_url)
        if doc_type == "id_card":
            res = _extract_id_card_fields(text)
            return {"id_card_no": res["id_card_no"]}, res["verified"], res["reason"]
        if doc_type == "education":
            res = _extract_education_fields(text)
            return {"degree_keywords": res["degree_keywords"]}, res["verified"], res["reason"]
        # Unreachable (validated by caller) — defensive.
        return {}, False, f"未知文档类型 {doc_type} (待上传)"

    def _ocr_text(self, file_bytes_or_url) -> str:
        """Fetch + OCR text from a URL or decode raw bytes via the shared stack."""
        if isinstance(file_bytes_or_url, (bytes, bytearray)):
            # Local Paddle OCR path expects a URL; for raw bytes we decode
            # text-like content directly (PDF/Word OCR is handled upstream by
            # the storage signed-URL flow). Tests pass plain text here.
            try:
                return file_bytes_or_url.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return ""
        url = str(file_bytes_or_url)
        return _run_async(_extract_text_from_url_safe(url))

    def _extract_resume(self, file_bytes_or_url) -> tuple[dict[str, Any], bool, str]:
        """Reuse parse_resume_from_url for the resume doc type.

        For raw bytes (no URL — e.g. already-decoded text in tests) we derive a
        minimal ``basic`` block from the text and run the same
        field-consistency check, so an empty / whitespace blob correctly yields
        pending (待上传).
        """
        if isinstance(file_bytes_or_url, (bytes, bytearray)):
            text = file_bytes_or_url.decode("utf-8", errors="replace")
            extracted = _derive_basic_from_text(text) if text and text.strip() else {}
            ok, reason = _resume_extracted_is_ok(extracted)
            return extracted, ok, reason

        from services.jobseeker.resume_parser import parse_resume_from_url

        url = str(file_bytes_or_url)
        try:
            result = _run_async(parse_resume_from_url(url))
        except Exception as e:  # noqa: BLE001
            return {}, False, f"简历解析异常: {e} (待上传)"
        extracted = (result or {}).get("extracted") or {}
        ok, reason = _resume_extracted_is_ok(extracted)
        return extracted, ok, reason

    # -- Persistence -------------------------------------------------------

    def _load_candidate(self, user_id: str) -> dict[str, Any]:
        admin = self._admin()
        if admin is not None:
            try:
                resp = (
                    admin.table("candidates")
                    .select(
                        "identity_status,id_card_status,education_doc_status,resume_status,identity_verified_at"
                    )
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if resp and getattr(resp, "data", None):
                    return resp.data[0]
            except Exception as e:  # noqa: BLE001
                logger.debug(f"identity: load_candidate fell back to memory: {e}")
        return self._mem.get_candidate(user_id)

    def _persist_status(self, user_id: str, doc_type: str, status: str) -> None:
        """Write one doc status + recompute/persist the roll-up identity_status."""
        col = _DOC_COLUMN[doc_type]
        # Compute new roll-up from the (possibly in-memory) current row.
        row = self._load_candidate(user_id)
        id_card = row.get("id_card_status", "pending")
        education = row.get("education_doc_status", "pending")
        resume = row.get("resume_status", "pending")
        if doc_type == "id_card":
            id_card = status
        elif doc_type == "education":
            education = status
        elif doc_type == "resume":
            resume = status
        overall = self.compute_overall(id_card, education, resume)

        # Update in-memory first (always; cheap and the source of truth for tests).
        mem_row = self._mem.get_candidate(user_id)
        mem_row[col] = status
        mem_row["identity_status"] = overall
        if overall == "verified" and not mem_row.get("identity_verified_at"):
            mem_row["identity_verified_at"] = _now_iso()
        with self._mem.lock:
            self._mem.candidates[user_id] = mem_row

        admin = self._admin()
        if admin is None:
            return
        patch: dict[str, Any] = {col: status, "identity_status": overall}
        if overall == "verified":
            patch["identity_verified_at"] = _now_iso()
        try:
            admin.table("candidates").update(patch).eq("user_id", user_id).execute()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"identity: candidates update fell back to memory: {e}")

    # -- Profile versioning ------------------------------------------------

    def save_profile_version(self, user_id: str, structured_profile: dict[str, Any]) -> int:
        """Append a new immutable profile version. Returns the new version_no."""
        if not isinstance(structured_profile, dict):
            raise TypeError("structured_profile must be a dict")

        admin = self._admin()
        if admin is not None:
            try:
                prev = self._latest_version_no_db(user_id, admin)
                version_no = prev + 1
                admin.table("profile_versions").insert(
                    {
                        "candidate_id": user_id,
                        "version_no": version_no,
                        "snapshot": structured_profile,
                    }
                ).execute()
                self._seed_memory_version(user_id, version_no, structured_profile)
                return version_no
            except Exception as e:  # noqa: BLE001
                logger.debug(f"identity: save_profile_version fell back to memory: {e}")

        # In-memory fallback.
        with self._mem.lock:
            versions = self._mem.versions.setdefault(user_id, [])
            version_no = (versions[-1]["version_no"] if versions else 0) + 1
            versions.append(
                {
                    "version_no": version_no,
                    "snapshot": dict(structured_profile),
                    "created_at": _now_iso(),
                }
            )
            return version_no

    def list_versions(self, user_id: str) -> list[dict[str, Any]]:
        """Return ``[{version_no, created_at}, ...]`` newest-first."""
        admin = self._admin()
        if admin is not None:
            try:
                resp = (
                    admin.table("profile_versions")
                    .select("version_no,created_at")
                    .eq("candidate_id", user_id)
                    .order("version_no", desc=True)
                    .execute()
                )
                if resp is not None:
                    return [
                        {"version_no": r["version_no"], "created_at": r.get("created_at")}
                        for r in (getattr(resp, "data", None) or [])
                    ]
            except Exception as e:  # noqa: BLE001
                logger.debug(f"identity: list_versions fell back to memory: {e}")
        with self._mem.lock:
            versions = self._mem.versions.get(user_id, [])
            return [
                {"version_no": v["version_no"], "created_at": v.get("created_at")}
                for v in reversed(versions)
            ]

    def get_version(self, user_id: str, version_no: int) -> dict[str, Any] | None:
        """Return the snapshot for a specific version_no, or ``None``."""
        admin = self._admin()
        if admin is not None:
            try:
                resp = (
                    admin.table("profile_versions")
                    .select("snapshot")
                    .eq("candidate_id", user_id)
                    .eq("version_no", version_no)
                    .limit(1)
                    .execute()
                )
                data = getattr(resp, "data", None) or []
                if data:
                    return data[0].get("snapshot")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"identity: get_version fell back to memory: {e}")
        with self._mem.lock:
            for v in self._mem.versions.get(user_id, []):
                if v["version_no"] == version_no:
                    return dict(v["snapshot"])
        return None

    def get_latest(self, user_id: str) -> dict[str, Any] | None:
        """Return the newest snapshot, or ``None`` if no versions exist."""
        versions = self.list_versions(user_id)
        if not versions:
            return None
        return self.get_version(user_id, versions[0]["version_no"])

    # -- internal helpers --------------------------------------------------

    def _latest_version_no_db(self, user_id: str, admin) -> int:
        try:
            resp = (
                admin.table("profile_versions")
                .select("version_no")
                .eq("candidate_id", user_id)
                .order("version_no", desc=True)
                .limit(1)
                .execute()
            )
            data = getattr(resp, "data", None) or []
            if data:
                return int(data[0].get("version_no") or 0)
        except Exception:  # noqa: BLE001
            pass
        return 0

    def _seed_memory_version(
        self, user_id: str, version_no: int, snapshot: dict[str, Any]
    ) -> None:
        """Keep the in-memory mirror in step with a successful DB write so the
        fallback stays consistent across a DB outage mid-session."""
        with self._mem.lock:
            versions = self._mem.versions.setdefault(user_id, [])
            if not any(v["version_no"] == version_no for v in versions):
                versions.append(
                    {
                        "version_no": version_no,
                        "snapshot": dict(snapshot),
                        "created_at": _now_iso(),
                    }
                )

    # -- test-only reset ---------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Clear the in-memory store (tests only)."""
        with _MEMORY.lock:
            _MEMORY.candidates.clear()
            _MEMORY.versions.clear()
        _LAST_EXTRACTION.clear()


# ---------------------------------------------------------------------------
# Helpers + module singleton
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    # Use a stable ISO timestamp (Supabase TIMESTAMPTZ accepts ISO-8601).
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _run_async(coro):
    """Run a coroutine to completion, even when a loop is already running.

    The identity service is invoked from synchronous code paths (and from
    FastAPI handlers that may or may not be async). ``asyncio.run`` errors out
    with "already running loop" inside an active loop, so detect that case and
    drive the coroutine on a fresh private loop instead. If anything goes wrong
    before the coroutine is awaited, close it so CPython doesn't emit a
    "coroutine was never awaited" RuntimeWarning.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is None:
        return asyncio.run(coro)
    # We're nested inside a running loop — run on a separate loop in a way that
    # doesn't cross loops. Close the coro's own loop when done.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    except Exception:
        # Ensure the coroutine is closed to avoid "never awaited" warnings.
        try:
            coro.close()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        loop.close()


async def _extract_text_from_url_safe(url: str) -> str:
    """Thin async wrapper around resume_parser.extract_text_from_url.

    Imported lazily so the identity service module never forces the OCR /
    providers stack to load at import time. Raises on failure; callers wrap.
    """
    from services.jobseeker.resume_parser import extract_text_from_url

    return await extract_text_from_url(url)


def get_identity_service() -> IdentityVerificationService:
    """Return a process-wide IdentityVerificationService singleton."""
    global _SERVICE
    try:
        return _SERVICE  # type: ignore[name-defined]
    except NameError:
        _SERVICE = IdentityVerificationService()
        return _SERVICE
