"""用户同意记录 + Cookie banner 服务.

T1201 GDPR — 用户对 cookies / 数据处理 / 跨境传输的明确同意.
T1202 中国合规 — PIPL 要求"知情同意",可单独撤回.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ConsentDecision:
    """一次同意决策."""

    category: str  # necessary / functional / analytics / marketing / cross_border
    granted: bool
    version: str = "v1"
    purpose: str | None = None  # 具体用途说明


@dataclass(slots=True)
class ConsentRecord:
    """用户同意状态(累计)."""

    user_id: str
    subject_id_hash: str  # 不可逆哈希,避免存明文邮箱
    decisions: list[ConsentDecision] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    withdrawn_at: datetime | None = None
    ip_hash: str | None = None  # 留 IP 哈希,不当存明文
    source: str = "web"  # web / api / mobile / admin


@dataclass(slots=True)
class ConsentBanner:
    """Cookie banner 内容(给前端使用)."""

    title: str
    description: str
    categories: list[dict[str, Any]]  # [{code, name, required, default}]
    policy_version: str
    locale: str = "en"
    privacy_url: str | None = None


class ConsentService:
    """同意记录管理.

    内存实现 + 抽象 persist hook,生产应替换为 Supabase / 独立合规 DB.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, ConsentRecord] = {}
        self._persist_cb: Any = None

    def set_persistence(self, cb: Any) -> None:
        """注入持久化 callback;失败由 callback 内部捕获."""
        self._persist_cb = cb

    # ----- subject id 哈希 -----
    @staticmethod
    def hash_subject(subject_id: str, salt: str = "waibao") -> str:
        """不可逆哈希 subject_id,GDPR 下不应明文存储."""
        return hashlib.sha256(f"{salt}:{subject_id}".encode("utf-8")).hexdigest()[:32]

    # ----- 业务 API -----
    def record_consent(
        self,
        user_id: str,
        subject_id: str,
        decisions: list[ConsentDecision],
        *,
        ip: str | None = None,
        source: str = "web",
    ) -> ConsentRecord:
        if not decisions:
            raise ValueError("decisions must not be empty")
        now = datetime.now(timezone.utc)
        with self._lock:
            record = self._records.get(user_id)
            subject_hash = self.hash_subject(subject_id)
            ip_hash = (
                hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32] if ip else None
            )
            if record is None:
                record = ConsentRecord(
                    user_id=user_id,
                    subject_id_hash=subject_hash,
                    decisions=list(decisions),
                    created_at=now,
                    updated_at=now,
                    ip_hash=ip_hash,
                    source=source,
                )
                self._records[user_id] = record
            else:
                # 合并:同一 category 取最新决策
                merged = {d.category: d for d in record.decisions}
                for d in decisions:
                    merged[d.category] = d
                record.decisions = list(merged.values())
                record.updated_at = now
                if ip_hash:
                    record.ip_hash = ip_hash
            self._persist(record)
            # 写入 audit log
            try:
                from .audit import get_audit_logger

                audit = get_audit_logger()
                audit.log(
                    actor_id=user_id,
                    actor_role="user",
                    action="consent_recorded",
                    resource="consent",
                    resource_id=user_id,
                    data_categories=["consent"],
                    legal_basis="consent",
                    ip_hash=ip_hash,
                    metadata={
                        "categories": [d.category for d in decisions],
                        "source": source,
                    },
                )
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).exception("consent.audit_failed")
            return record

    def record_consent_simple(
        self,
        user_id: str,
        consent_type: str,
        granted: bool,
        ip: str | None = None,
        user_agent: str | None = None,
        *,
        version: str = "v1",
    ) -> ConsentRecord:
        """便捷接口:T1201 签名 record_consent(user_id, type, granted, ip, ua).

        自动写入 subject_id = user_id(同一用户的代理身份).
        """
        decision = ConsentDecision(
            category=consent_type,
            granted=granted,
            version=version,
            purpose=f"user_{consent_type}_{'grant' if granted else 'deny'}",
        )
        ua_source = "web" if user_agent else "api"
        return self.record_consent(
            user_id=user_id,
            subject_id=user_id,
            decisions=[decision],
            ip=ip,
            source=ua_source,
        )

    def get_consent_status(self, user_id: str) -> dict[str, Any]:
        """便捷接口:T1201 签名 get_consent_status(user_id)."""
        record = self.get_record(user_id)
        if record is None:
            return {
                "user_id": user_id,
                "has_record": False,
                "decisions": {},
                "withdrawn_at": None,
                "created_at": None,
                "updated_at": None,
            }
        decisions_map = {d.category: d.granted for d in record.decisions}
        return {
            "user_id": user_id,
            "has_record": True,
            "decisions": decisions_map,
            "withdrawn_at": record.withdrawn_at.isoformat() if record.withdrawn_at else None,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "source": record.source,
        }

    def withdraw_consent(
        self,
        user_id: str,
        consent_type: str | None = None,
    ) -> ConsentRecord | None:
        """便捷接口:T1201 签名 withdraw_consent(user_id, consent_type).

        consent_type=None 表示撤回所有同意.
        """
        return self.withdraw(user_id, category=consent_type)

    def withdraw(self, user_id: str, *, category: str | None = None) -> ConsentRecord | None:
        """撤回同意. category=None 表示全部撤回."""
        with self._lock:
            record = self._records.get(user_id)
            if record is None:
                return None
            now = datetime.now(timezone.utc)
            if category is None:
                record.withdrawn_at = now
                record.decisions = []
            else:
                record.decisions = [
                    d for d in record.decisions if d.category != category
                ]
            record.updated_at = now
            self._persist(record)
            # 写入 audit log
            try:
                from .audit import get_audit_logger

                audit = get_audit_logger()
                audit.log(
                    actor_id=user_id,
                    actor_role="user",
                    action="consent_withdrawn",
                    resource="consent",
                    resource_id=user_id,
                    data_categories=["consent"],
                    legal_basis="consent",
                    metadata={"category": category, "scope": "all" if category is None else "single"},
                )
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).exception("consent.withdraw_audit_failed")
            return record

    def has_consent(self, user_id: str, category: str) -> bool:
        with self._lock:
            record = self._records.get(user_id)
        if record is None or record.withdrawn_at is not None:
            return False
        return any(d.category == category and d.granted for d in record.decisions)

    def get_record(self, user_id: str) -> ConsentRecord | None:
        with self._lock:
            return self._records.get(user_id)

    def build_banner(
        self,
        locale: str = "en",
        *,
        policy_version: str = "v1",
        privacy_url: str | None = "/legal/privacy",
    ) -> ConsentBanner:
        """构造前端 cookie banner 内容."""
        title = {
            "en": "We value your privacy",
            "zh": "我们重视您的隐私",
        }.get(locale, "We value your privacy")
        description = {
            "en": "Choose which cookies and processing you allow.",
            "zh": "请选择您允许的 Cookie 与数据处理范围。",
        }.get(locale, "Choose which cookies and processing you allow.")
        categories = [
            {"code": "necessary", "name": "Necessary", "required": True, "default": True},
            {"code": "functional", "name": "Functional", "required": False, "default": False},
            {"code": "analytics", "name": "Analytics", "required": False, "default": False},
            {"code": "marketing", "name": "Marketing", "required": False, "default": False},
            {"code": "cross_border", "name": "Cross-border transfer", "required": False, "default": False},
        ]
        return ConsentBanner(
            title=title,
            description=description,
            categories=categories,
            policy_version=policy_version,
            locale=locale,
            privacy_url=privacy_url,
        )

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Art. 15 — 数据可携权:导出用户全部 consent 记录."""
        record = self.get_record(user_id)
        if record is None:
            return {"user_id": user_id, "found": False}
        return {
            "user_id": record.user_id,
            "subject_id_hash": record.subject_id_hash,
            "decisions": [asdict(d) for d in record.decisions],
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "withdrawn_at": record.withdrawn_at.isoformat() if record.withdrawn_at else None,
            "source": record.source,
            "found": True,
        }

    def _persist(self, record: ConsentRecord) -> None:
        if self._persist_cb is None:
            return
        try:
            self._persist_cb(self.export_user_data(record.user_id))
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("consent.persist_failed")


_singleton: ConsentService | None = None


def get_consent_service() -> ConsentService:
    global _singleton
    if _singleton is None:
        _singleton = ConsentService()
    return _singleton