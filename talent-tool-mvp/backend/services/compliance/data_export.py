"""v10.0 T5016 — Portable data export (GDPR Art. 20) with PIPL cross-border
transfer declaration.

This service produces a **machine-readable, self-describing** export bundle of
a data subject's information.  It satisfies three overlapping regimes at once:

* **GDPR Art. 20** — "received in a structured, commonly used and
  machine-readable format".  The bundle is JSON + optional JSON Lines, keyed by
  collection, with a manifest.
* **PIPL Art. 39 / Art. 53** — when the subject's home region is mainland
  China, every export is stamped with the PIPL cross-border transfer
  declaration (transferred-out notice) and the transfer is recorded in the
  export manifest so the controller can prove lawful transfer.
* **CCPA § 1798.100** — categories/sources/purpose disclosure is embedded in
  the manifest.

The service is storage-agnostic: a :class:`ExportSource` protocol returns
collections of rows.  A Supabase-backed source is wired in production; tests
inject a dict source.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from services.platform.consent import PIPL_CROSS_BORDER_DISCLOSURE

logger = logging.getLogger("waibao.compliance.data_export")

EXPORT_FORMAT_VERSION = "2.0"
DEFAULT_FORMAT = "json"          # json | jsonl


# ---------------------------------------------------------------------------
# Source protocol — decouples us from Supabase / any DB driver.
# ---------------------------------------------------------------------------

class ExportSource(Protocol):
    """Return the rows belonging to ``subject_id`` for each collection."""

    def collections(self) -> list[str]: ...
    def fetch(self, collection: str, subject_id: str) -> list[dict[str, Any]]: ...


class DictExportSource:
    """In-memory source: ``{collection: {subject_id: [row, ...]}}``."""

    def __init__(self, data: Optional[dict[str, dict[str, list[dict[str, Any]]]]] = None) -> None:
        self._data: dict[str, dict[str, list[dict[str, Any]]]] = data or {}

    def collections(self) -> list[str]:
        return list(self._data.keys())

    def fetch(self, collection: str, subject_id: str) -> list[dict[str, Any]]:
        return list(self._data.get(collection, {}).get(subject_id, []))

    def add(self, collection: str, subject_id: str, rows: list[dict[str, Any]]) -> None:
        bucket = self._data.setdefault(collection, {})
        bucket.setdefault(subject_id, []).extend(rows)


# ---------------------------------------------------------------------------
# Bundle data classes
# ---------------------------------------------------------------------------

@dataclass
class ExportBundle:
    """The fully-assembled portable bundle."""

    subject_id: str
    region: str
    format: str
    exported_at: str
    manifest: dict[str, Any]
    collections: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pipl_cross_border: Optional[dict[str, Any]] = None
    integrity_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "region": self.region,
            "format": self.format,
            "exported_at": self.exported_at,
            "format_version": EXPORT_FORMAT_VERSION,
            "manifest": self.manifest,
            "pipl_cross_border": self.pipl_cross_border,
            "integrity_sha256": self.integrity_sha256,
            "collections": self.collections,
        }

    def to_json(self) -> str:
        """Serialise deterministically (sorted keys) for reproducible hashing."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# PIPL cross-border helpers
# ---------------------------------------------------------------------------

# Regions that trigger a PIPL cross-border declaration on export.
PIPL_REGIONS: frozenset[str] = frozenset({"CN", "HK", "MO", "TW"})


def needs_pipl_declaration(region: str) -> bool:
    """True when the export leaves (or could leave) a PIPL jurisdiction."""
    return region.upper() in PIPL_REGIONS


def stamp_pipl_declaration(region: str) -> Optional[dict[str, Any]]:
    """Return the PIPL transfer declaration when the region warrants one."""
    if not needs_pipl_declaration(region):
        return None
    return {
        "applies": True,
        "law": "PIPL (Personal Information Protection Law of the PRC) Art. 38–42",
        "declaration": PIPL_CROSS_BORDER_DISCLOSURE,
        "declared_at": datetime.now(tz=timezone.utc).isoformat(),
        "note": (
            "本数据包包含个人信息出境处理声明。接收方须在数据出境安全评估、"
            "标准合同或认证的范围内使用本数据。"
            "This bundle contains a PIPL cross-border transfer declaration."
        ),
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

# Per-collection disclosure metadata (CCPA categories + GDPR lawful basis).
# Keys are the collection names the ExportSource exposes.
DEFAULT_COLLECTION_META: dict[str, dict[str, Any]] = {
    "users": {
        "ccpa_category": "identifiers",
        "gdpr_basis": "gdpr_contract",
        "purpose": "账户身份与认证",
    },
    "journal_entries": {
        "ccpa_category": "inferences",
        "gdpr_basis": "gdpr_consent",
        "purpose": "求职日志与AI规划",
    },
    "messages": {
        "ccpa_category": "commercial",
        "gdpr_basis": "gdpr_contract",
        "purpose": "站内沟通",
    },
    "interview_sessions": {
        "ccpa_category": "biometric",
        "gdpr_basis": "gdpr_consent",
        "purpose": "AI 面试录像与评估",
    },
    "consent_records": {
        "ccpa_category": "customer_records",
        "gdpr_basis": "gdpr_legal_obligation",
        "purpose": "同意与偏好留痕",
    },
}


class DataExportService:
    """Builds portable export bundles.

    Parameters
    ----------
    source
        The :class:`ExportSource` to read rows from.
    collection_meta
        Optional override of :data:`DEFAULT_COLLECTION_META`.
    pii_redactor
        Optional ``row -> row`` callable applied to every row of *every*
        collection (e.g. mask phone / bank card).  Defaults to no-op; the
        gateway's PII policy is the canonical place for masking, but export
        time is a sensible belt-and-braces extra.
    """

    def __init__(
        self,
        source: ExportSource,
        *,
        collection_meta: Optional[dict[str, dict[str, Any]]] = None,
        pii_redactor: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        self.source = source
        self.collection_meta = {**DEFAULT_COLLECTION_META, **(collection_meta or {})}
        self.pii_redactor = pii_redactor

    def export(
        self,
        subject_id: str,
        *,
        region: str = "EU",
        fmt: str = DEFAULT_FORMAT,
        include_audit: bool = False,
        collections: Optional[list[str]] = None,
    ) -> ExportBundle:
        if fmt not in {"json", "jsonl"}:
            raise ValueError(f"unsupported export format: {fmt}")
        now = datetime.now(tz=timezone.utc)
        wanted = collections or self.source.collections()

        bundle_collections: dict[str, list[dict[str, Any]]] = {}
        collection_counts: dict[str, int] = {}
        categories_seen: set[str] = set()

        for name in wanted:
            rows = self.source.fetch(name, subject_id)
            if self.pii_redactor is not None:
                rows = [self.pii_redactor(r) for r in rows]
            bundle_collections[name] = rows
            collection_counts[name] = len(rows)
            meta = self.collection_meta.get(name, {})
            if meta.get("ccpa_category"):
                categories_seen.add(meta["ccpa_category"])

        manifest = {
            "subject_id": subject_id,
            "region": region,
            "exported_at": now.isoformat(),
            "format_version": EXPORT_FORMAT_VERSION,
            "format": fmt,
            "collections": collection_counts,
            "categories_of_pi_disclosed": sorted(categories_seen),
            "collection_meta": {
                name: self.collection_meta.get(name, {}) for name in wanted
            },
            "rights_notice": (
                "GDPR Art. 20 portability / Art. 15 access. CCPA § 1798.100 right to know. "
                "PIPL Art. 45 query & copy."
            ),
            "include_audit": include_audit,
        }

        bundle = ExportBundle(
            subject_id=subject_id,
            region=region,
            format=fmt,
            exported_at=now.isoformat(),
            manifest=manifest,
            collections=bundle_collections,
            pipl_cross_border=stamp_pipl_declaration(region),
        )
        bundle.integrity_sha256 = hashlib.sha256(bundle.to_json().encode("utf-8")).hexdigest()
        logger.info(
            "data_export.completed subject=%s region=%s collections=%d sha=%s",
            subject_id, region, len(bundle_collections), bundle.integrity_sha256[:12],
        )
        return bundle

    def export_jsonl(self, subject_id: str, *, region: str = "EU") -> str:
        """Convenience: emit JSON Lines (one record per line) — useful for
        downstream ingestion pipelines that prefer streaming."""
        bundle = self.export(subject_id, region=region, fmt="jsonl")
        lines: list[str] = []
        lines.append(json.dumps({"_manifest": bundle.manifest}, ensure_ascii=False, default=str))
        for name, rows in bundle.collections.items():
            for row in rows:
                lines.append(json.dumps({"_collection": name, **row}, ensure_ascii=False, default=str))
        if bundle.pipl_cross_border:
            lines.append(json.dumps({"_pipl_cross_border": bundle.pipl_cross_border}, ensure_ascii=False, default=str))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: Optional[DataExportService] = None


def get_data_export_service() -> DataExportService:
    """Return the process singleton.  Production should call
    :func:`configure_data_export_service` at boot with a Supabase-backed source."""
    global _service
    if _service is None:
        _service = DataExportService(DictExportSource())
    return _service


def configure_data_export_service(service: DataExportService) -> None:
    """Boot hook — swap in a Supabase-backed service."""
    global _service
    _service = service


def reset_data_export_service() -> None:
    global _service
    _service = None


__all__ = [
    "EXPORT_FORMAT_VERSION",
    "DEFAULT_FORMAT",
    "PIPL_REGIONS",
    "ExportSource",
    "DictExportSource",
    "ExportBundle",
    "needs_pipl_declaration",
    "stamp_pipl_declaration",
    "DataExportService",
    "get_data_export_service",
    "configure_data_export_service",
    "reset_data_export_service",
]
