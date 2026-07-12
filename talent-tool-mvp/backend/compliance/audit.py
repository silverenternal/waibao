"""增强 audit log — GDPR Art. 30 处理活动记录 + 中国 PIPL 数据处理记录.

在 v3.0 services.audit.AuditLogger 基础上,补充:
- data_categories: 处理的数据类别(姓别 / 邮箱 / 简历 / IP)
- legal_basis: 处理的法律依据 (consent / contract / legitimate_interest)
- cross_border: 是否跨境
- retention_days: 保留天数
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class AuditEntry:
    """audit 一条记录."""

    entry_id: str
    actor_id: str | None
    actor_role: str | None
    action: str  # read / write / delete / export / anonymize
    resource: str  # candidate / job / invoice / ...
    resource_id: str | None
    occurred_at: datetime
    data_categories: list[str] = field(default_factory=list)
    legal_basis: str = "consent"
    cross_border: bool = False
    retention_days: int = 365
    ip_hash: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """GDPR Art. 30 / PIPL 增强 audit logger.

    内存实现 + persist hook. 真实场景推荐 Supabase audit_log 表.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: list[AuditEntry] = []
        self._persist_cb: Any = None

    def set_persistence(self, cb: Any) -> None:
        """注入持久化 callback."""
        self._persist_cb = cb

    # ----- API -----
    def log(
        self,
        *,
        actor_id: str | None,
        action: str,
        resource: str,
        resource_id: str | None = None,
        actor_role: str | None = None,
        data_categories: list[str] | None = None,
        legal_basis: str = "consent",
        cross_border: bool = False,
        retention_days: int = 365,
        ip_hash: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=f"aud_{uuid.uuid4().hex[:16]}",
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource=resource,
            resource_id=resource_id,
            occurred_at=datetime.now(timezone.utc),
            data_categories=data_categories or [],
            legal_basis=legal_basis,
            cross_border=cross_border,
            retention_days=retention_days,
            ip_hash=ip_hash,
            request_id=request_id,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
        self._persist(entry)
        return entry

    def query(
        self,
        *,
        actor_id: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        with self._lock:
            results: list[AuditEntry] = []
            for e in reversed(self._entries):
                if actor_id and e.actor_id != actor_id:
                    continue
                if resource and e.resource != resource:
                    continue
                if resource_id and e.resource_id != resource_id:
                    continue
                if action and e.action != action:
                    continue
                if since and e.occurred_at < since:
                    continue
                results.append(e)
                if len(results) >= limit:
                    break
            return results

    def export_for_dpo(self, actor_id: str) -> list[dict[str, Any]]:
        """GDPR Art. 30 — 数据保护官审计导出."""
        entries = self.query(actor_id=actor_id, limit=10_000)
        return [
            {
                "entry_id": e.entry_id,
                "action": e.action,
                "resource": e.resource,
                "resource_id": e.resource_id,
                "occurred_at": e.occurred_at.isoformat(),
                "data_categories": e.data_categories,
                "legal_basis": e.legal_basis,
                "cross_border": e.cross_border,
                "retention_days": e.retention_days,
            }
            for e in entries
        ]

    def _persist(self, entry: AuditEntry) -> None:
        if self._persist_cb is None:
            return
        try:
            self._persist_cb(
                {
                    "entry_id": entry.entry_id,
                    "actor_id": entry.actor_id,
                    "actor_role": entry.actor_role,
                    "action": entry.action,
                    "resource": entry.resource,
                    "resource_id": entry.resource_id,
                    "occurred_at": entry.occurred_at.isoformat(),
                    "data_categories": entry.data_categories,
                    "legal_basis": entry.legal_basis,
                    "cross_border": entry.cross_border,
                    "retention_days": entry.retention_days,
                    "ip_hash": entry.ip_hash,
                    "request_id": entry.request_id,
                    "metadata": json.dumps(entry.metadata, ensure_ascii=False),
                }
            )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("audit.persist_failed")


_singleton: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _singleton
    if _singleton is None:
        _singleton = AuditLogger()
    return _singleton