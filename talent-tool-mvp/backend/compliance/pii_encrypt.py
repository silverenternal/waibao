"""T5015 — Field-level PII encryption registry, KMS-backed.

This is the single source of truth for **which columns in which tables**
must be encrypted at rest. It wraps :class:`compliance.encryption.PIIEncryptor`
(which now pulls its DEK from :mod:`compliance.kms`) and exposes a
table-aware API so data-access layers can transparently encrypt on write
and decrypt on read.

Coverage (T5015):
  users           — email, phone, id_card
  candidates      — name, email, phone, cv_text
  journal         — content
  chat_messages   — content
  resumes         — raw_text, parsed_text
  applications    — cover_letter
  interviews      — transcript, notes
  offers          — salary, offer_letter
  consent_records — metadata (free-text may carry PII)

Each ciphertext carries a versioned envelope so future rotations /
algorithm changes can be detected: ``v1:<key_id>:<fernet-token>``.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from compliance.encryption import PIIEncryptor, get_pii_encryptor
from compliance.kms import KMSManager, get_kms

logger = logging.getLogger("waibao.pii_encrypt")

ENVELOPE_VERSION = "v1"
_ENVELOPE_PREFIX = f"{ENVELOPE_VERSION}:"


# ---------------------------------------------------------------------------
# Registry: table -> encrypted column list
# ---------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class TablePIISpec:
    table: str
    fields: tuple[str, ...]


# T5015 全字段 PII 加密注册表
PII_TABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "users": ("email", "phone", "id_card"),
    "candidates": ("name", "email", "phone", "cv_text"),
    "journal": ("content",),
    "chat_messages": ("content",),
    "resumes": ("raw_text", "parsed_text"),
    "applications": ("cover_letter",),
    "interviews": ("transcript", "notes"),
    "offers": ("salary", "offer_letter"),
    "consent_records": ("metadata",),
    # additional PII-bearing tables surfaced by the v10.0 security audit
    "profiles": ("full_name", "email", "phone", "address", "bio"),
    "daily_journal": ("content",),
    "offers_v2": ("salary", "offer_letter_text"),
    "ats_candidates": ("email", "phone"),
}


def list_pii_tables() -> list[str]:
    return sorted(PII_TABLE_FIELDS)


def fields_for(table: str) -> tuple[str, ...]:
    return PII_TABLE_FIELDS.get(table, ())


# ---------------------------------------------------------------------------
# PIIEncryptService — table-aware encrypt/decrypt
# ---------------------------------------------------------------------------
class PIIEncryptService:
    """Encrypt/decrypt PII fields, KMS-backed, with versioned envelopes."""

    def __init__(
        self,
        encryptor: Optional[PIIEncryptor] = None,
        kms: Optional[KMSManager] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._kms = kms or get_kms()
        self._enc = encryptor or PIIEncryptor(kms=self._kms)

    @property
    def backend(self) -> str:
        return self._enc.backend

    # -- envelope helpers ----------------------------------------------
    def _key_id(self) -> str:
        try:
            dek = self._kms.current_dek()
            return dek.key_id
        except Exception:  # noqa: BLE001
            return "unknown"

    def encrypt_value(self, plaintext: str) -> str:
        if plaintext is None:
            return plaintext  # type: ignore[return-value]
        if not isinstance(plaintext, str):
            raise TypeError(f"plaintext must be str, got {type(plaintext).__name__}")
        if not plaintext:
            return plaintext
        token = self._enc.encrypt(plaintext)
        return f"{_ENVELOPE_PREFIX}{self._key_id()}:{token}"

    def decrypt_value(self, ciphertext: str) -> str:
        if ciphertext is None or not isinstance(ciphertext, str) or not ciphertext:
            return ciphertext  # type: ignore[return-value]
        if ciphertext.startswith(_ENVELOPE_PREFIX):
            # envelope form: v1:<key_id>:<token>
            rest = ciphertext[len(_ENVELOPE_PREFIX):]
            _key_id, _, token = rest.partition(":")
            return self._enc.decrypt(token)
        # legacy raw Fernet token (pre-T5015) — best-effort decrypt
        return self._enc.decrypt(ciphertext)

    # -- table-aware dict helpers --------------------------------------
    def encrypt_row(
        self,
        table: str,
        row: dict[str, Any],
        fields: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        target = tuple(fields) if fields is not None else PII_TABLE_FIELDS.get(table, ())
        out = dict(row)
        with self._lock:
            for f in target:
                v = out.get(f)
                if isinstance(v, str) and v and not self._is_ciphertext(v):
                    out[f] = self.encrypt_value(v)
        return out

    def decrypt_row(
        self,
        table: str,
        row: dict[str, Any],
        fields: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        target = tuple(fields) if fields is not None else PII_TABLE_FIELDS.get(table, ())
        out = dict(row)
        with self._lock:
            for f in target:
                v = out.get(f)
                if isinstance(v, str) and v and self._is_ciphertext(v):
                    try:
                        out[f] = self.decrypt_value(v)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("pii_decrypt_failed table=%s field=%s: %s", table, f, exc)
        return out

    def encrypt_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        fields: Optional[Iterable[str]] = None,
    ) -> list[dict[str, Any]]:
        return [self.encrypt_row(table, r, fields) for r in rows]

    def decrypt_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        fields: Optional[Iterable[str]] = None,
    ) -> list[dict[str, Any]]:
        return [self.decrypt_row(table, r, fields) for r in rows]

    @staticmethod
    def _is_ciphertext(value: str) -> bool:
        """Heuristic: is this value already encrypted?"""
        return value.startswith(_ENVELOPE_PREFIX) or value.startswith("gAAAAA") or value.startswith("gAAAAE")

    # -- coverage report -----------------------------------------------
    def coverage_report(self) -> dict[str, Any]:
        total_tables = len(PII_TABLE_FIELDS)
        total_fields = sum(len(fs) for fs in PII_TABLE_FIELDS.values())
        return {
            "provider": self._kms.provider,
            "backend": self.backend,
            "envelope_version": ENVELOPE_VERSION,
            "tables_covered": total_tables,
            "fields_covered": total_fields,
            "tables": {t: list(fs) for t, fs in PII_TABLE_FIELDS.items()},
            "dek": self._kms.status(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[PIIEncryptService] = None
_singleton_lock = threading.Lock()


def get_pii_service() -> PIIEncryptService:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = PIIEncryptService()
        return _singleton


def reset_pii_service() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None


__all__ = [
    "ENVELOPE_VERSION",
    "PII_TABLE_FIELDS",
    "TablePIISpec",
    "PIIEncryptService",
    "get_pii_service",
    "reset_pii_service",
    "list_pii_tables",
    "fields_for",
]
