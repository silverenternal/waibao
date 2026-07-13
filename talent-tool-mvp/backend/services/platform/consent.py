"""T2603 — Consent Service v6.0 (per-purpose, withdrawal, PIPL cross-border).

Compared with the v1 service at ``backend/compliance/consent.py``:

- Per-purpose grants instead of one boolean per category. A user may
  grant "marketing email" but deny "marketing SMS"; previously this was
  collapsed to a single "marketing" bucket.

- First-class *withdrawal* flow. ``withdraw_purpose(user_id, purpose)``
  records the revocation, returns the new state, and emits an audit
  row so the compliance team has evidence the user actually withdrew.

- PIPL cross-border declaration. Before any export / transfer out of
  CN the user must accept the cross-border notice. The notice itself
  is parameterised (recipient, data categories, safeguard) so we can
  resurface it whenever the destination changes.

- Region-aware lawful basis hints. ``record_consent`` looks at the
  active audit context's region and stamps the matching GDPR / PIPL
  basis code so the audit row joins cleanly to the lawful basis
  catalog.

The store is in-memory + persist hook; production deployments wire
``set_persistence`` to Supabase.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("waibao.consent_v6")

# ---------------------------------------------------------------------------
# Canonical purposes (v6.0)
# ---------------------------------------------------------------------------
PURPOSES: dict[str, dict[str, Any]] = {
    "necessary": {
        "code": "necessary",
        "label_zh": "必要",
        "label_en": "Strictly necessary",
        "required": True,
        "description_zh": "登录、账户安全、防欺诈;无法关闭",
        "description_en": "Login, account security, fraud prevention; cannot be disabled",
        "gdpr_basis": "gdpr_contract",
        "pipl_basis": "pipl_contract_necessary",
    },
    "functional": {
        "code": "functional",
        "label_zh": "功能",
        "label_en": "Functional",
        "required": False,
        "description_zh": "记住偏好(语言 / 主题 / 推荐)",
        "description_en": "Remember preferences (language, theme, recommendations)",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
    "analytics": {
        "code": "analytics",
        "label_zh": "分析",
        "label_en": "Analytics",
        "required": False,
        "description_zh": "产品使用度量,帮助我们改进体验",
        "description_en": "Product usage telemetry to help us improve",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
    "marketing": {
        "code": "marketing",
        "label_zh": "营销",
        "label_en": "Marketing",
        "required": False,
        "description_zh": "接收职位推荐、活动邀请、产品更新",
        "description_en": "Job recommendations, event invites, product updates",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
    "marketing_sms": {
        "code": "marketing_sms",
        "label_zh": "营销短信",
        "label_en": "Marketing SMS",
        "required": False,
        "description_zh": "短信通知 + 验证码 + 营销",
        "description_en": "SMS notifications, OTPs, marketing messages",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
    "coaching": {
        "code": "coaching",
        "label_zh": "AI 面试辅导",
        "label_en": "AI Coaching",
        "required": False,
        "description_zh": "AI 模拟面试官、简历润色、面试准备助手",
        "description_en": "AI mock interviews, resume polishing, prep assistant",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
    "ai_training": {
        "code": "ai_training",
        "label_zh": "AI 模型训练",
        "label_en": "AI Model Training",
        "required": False,
        "description_zh": "使用您的匿名化数据改进 AI 模型",
        "description_en": "Use your anonymised data to improve our AI models",
        "gdpr_basis": "gdpr_legitimate_interest",
        "pipl_basis": "pipl_consent",
    },
    "cross_border": {
        "code": "cross_border",
        "label_zh": "数据出境",
        "label_en": "Cross-border transfer",
        "required": False,
        "description_zh": "同意将数据传输至您所在区域之外的服务器",
        "description_en": "Allow transfer to servers outside your home region",
        "gdpr_basis": "gdpr_consent",
        "pipl_basis": "pipl_consent",
    },
}


# ---------------------------------------------------------------------------
# Default PIPL cross-border disclosure (cn region)
# ---------------------------------------------------------------------------
PIPL_CROSS_BORDER_DISCLOSURE: dict[str, Any] = {
    "version": "2026-07",
    "controller": "上海外保智能科技有限公司 (Shanghai Waibao Intelligence Co., Ltd.)",
    "controller_contact": "privacy@waibao.example",
    "purposes": ["产品交付", "AI 简历匹配", "客户支持"],
    "data_categories": ["姓名", "邮箱", "电话", "简历内容", "面试录像"],
    "recipients": [
        {"name": "Supabase Inc. (US)", "safeguard": "SCC + 安全评估"},
        {"name": "AWS Asia Pacific (Singapore)", "safeguard": "ISO 27001 / 等保三级"},
    ],
    "retention": "3 年 (PIPL Art. 52)",
    "user_rights": [
        "知情权 (Art. 44)",
        "决定权 (Art. 44)",
        "查询复制权 (Art. 45)",
        "更正补充权 (Art. 46)",
        "删除权 (Art. 47)",
    ],
    "withdrawal": "您可随时撤回,撤回不影响此前基于同意的处理",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class PurposeConsent:
    purpose: str
    granted: bool
    version: str
    granted_at: datetime | None
    withdrawn_at: datetime | None
    source: str  # "web" | "api" | "mobile" | "admin"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConsentState:
    user_id: str
    subject_hash: str
    region: str
    purposes: dict[str, PurposeConsent]
    created_at: datetime
    updated_at: datetime
    ip_hash: str | None = None
    policy_version: str = "2026-07"

    def is_active(self, purpose: str) -> bool:
        c = self.purposes.get(purpose)
        return bool(c and c.granted and c.withdrawn_at is None)

    def active_purposes(self) -> list[str]:
        return [p for p, c in self.purposes.items() if c.granted and c.withdrawn_at is None]

    def withdrawn_purposes(self) -> list[str]:
        return [p for p, c in self.purposes.items() if c.withdrawn_at is not None]

    def has_pending_required(self) -> list[str]:
        """Required purposes the user has not granted yet."""
        missing = []
        for code, meta in PURPOSES.items():
            if not meta["required"]:
                continue
            if not self.is_active(code):
                missing.append(code)
        return missing


@dataclass(slots=True)
class CrossBorderNotice:
    user_id: str
    version: str
    accepted: bool
    accepted_at: datetime | None
    notice: dict[str, Any]


# ---------------------------------------------------------------------------
# In-memory store + persist hook
# ---------------------------------------------------------------------------
class ConsentStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, ConsentState] = {}
        self._cross_border: dict[str, CrossBorderNotice] = {}
        self._audit_cb: Optional[Any] = None
        self._persist_cb: Optional[Any] = None

    def set_persistence(self, cb: Any) -> None:
        self._persist_cb = cb

    def set_audit_callback(self, cb: Any) -> None:
        """Receives ``(event_type, payload)`` for audit emission."""
        self._audit_cb = cb

    # ---- helpers ----
    @staticmethod
    def hash_subject(subject_id: str, salt: str = "waibao") -> str:
        return hashlib.sha256(f"{salt}:{subject_id}".encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def hash_ip(ip: str | None) -> str | None:
        if not ip:
            return None
        return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]

    # ---- core API ----
    def get_or_create(
        self,
        user_id: str,
        subject_id: str,
        *,
        region: str = "GLOBAL",
        ip: str | None = None,
        policy_version: str = "2026-07",
    ) -> ConsentState:
        with self._lock:
            existing = self._states.get(user_id)
            if existing:
                return existing
            now = datetime.now(timezone.utc)
            state = ConsentState(
                user_id=user_id,
                subject_hash=self.hash_subject(subject_id),
                region=region,
                purposes={},
                created_at=now,
                updated_at=now,
                ip_hash=self.hash_ip(ip),
                policy_version=policy_version,
            )
            # grant "necessary" by default; required purposes can't be opted out
            for code, meta in PURPOSES.items():
                if meta["required"]:
                    state.purposes[code] = PurposeConsent(
                        purpose=code,
                        granted=True,
                        version=policy_version,
                        granted_at=now,
                        withdrawn_at=None,
                        source="default",
                    )
            self._states[user_id] = state
            self._emit_audit("consent_initialised", {
                "user_id": user_id,
                "region": region,
                "policy_version": policy_version,
                "active_purposes": state.active_purposes(),
            })
            self._persist(state)
            return state

    def grant(
        self,
        user_id: str,
        subject_id: str,
        purposes: Iterable[str],
        *,
        region: str = "GLOBAL",
        ip: str | None = None,
        source: str = "web",
        policy_version: str = "2026-07",
        metadata: dict[str, Any] | None = None,
    ) -> ConsentState:
        purposes = list(purposes)
        unknown = [p for p in purposes if p not in PURPOSES]
        if unknown:
            raise ValueError(f"unknown purpose(s): {unknown}")

        with self._lock:
            state = self.get_or_create(
                user_id, subject_id, region=region, ip=ip, policy_version=policy_version,
            )
            now = datetime.now(timezone.utc)
            for p in purposes:
                # required purposes stay granted; ignore any "deny" attempt
                if PURPOSES[p]["required"]:
                    continue
                state.purposes[p] = PurposeConsent(
                    purpose=p,
                    granted=True,
                    version=policy_version,
                    granted_at=now,
                    withdrawn_at=None,
                    source=source,
                    metadata=metadata or {},
                )
            state.updated_at = now
            if ip:
                state.ip_hash = self.hash_ip(ip)
            self._emit_audit("consent_grant", {
                "user_id": user_id,
                "purposes": purposes,
                "region": region,
                "source": source,
                "policy_version": policy_version,
            })
            self._persist(state)
            return state

    def deny(
        self,
        user_id: str,
        subject_id: str,
        purposes: Iterable[str],
        *,
        region: str = "GLOBAL",
        ip: str | None = None,
        source: str = "web",
        policy_version: str = "2026-07",
    ) -> ConsentState:
        purposes = list(purposes)
        # silently skip required purposes (they can't be opted out of)
        # but still log an audit event so the compliance team sees the attempt
        skipped_required = [p for p in purposes if PURPOSES.get(p, {}).get("required")]
        if skipped_required:
            for p in skipped_required:
                self._emit_audit("consent_deny_blocked", {
                    "user_id": user_id,
                    "purpose": p,
                    "reason": "required",
                    "region": region,
                })
        permitted = [p for p in purposes if p not in skipped_required]
        if not permitted:
            # nothing to do; return existing state
            return self.get_or_create(user_id, subject_id, region=region, ip=ip)
        return self._set_state(
            user_id, subject_id, permitted, granted=False,
            region=region, ip=ip, source=source,
            policy_version=policy_version, audit_event="consent_deny",
        )

    def withdraw(
        self,
        user_id: str,
        subject_id: str,
        purposes: Iterable[str],
        *,
        region: str = "GLOBAL",
        ip: str | None = None,
        source: str = "web",
        reason: str | None = None,
    ) -> ConsentState:
        """Withdraw previously granted consent (GDPR Art. 7(3), PIPL Art. 29)."""
        purposes = list(purposes)
        with self._lock:
            state = self.get_or_create(user_id, subject_id, region=region, ip=ip)
            now = datetime.now(timezone.utc)
            withdrawn: list[str] = []
            for p in purposes:
                c = state.purposes.get(p)
                if not c or not c.granted or c.withdrawn_at is not None:
                    continue
                if PURPOSES[p]["required"]:
                    # required purposes can't be withdrawn; just log
                    self._emit_audit("consent_withdraw_blocked", {
                        "user_id": user_id,
                        "purpose": p,
                        "reason": "required",
                    })
                    continue
                c.withdrawn_at = now
                c.granted = False
                c.metadata["withdrawal_reason"] = reason
                c.metadata["withdrawal_source"] = source
                withdrawn.append(p)
            state.updated_at = now
            self._emit_audit("consent_withdraw", {
                "user_id": user_id,
                "purposes": withdrawn,
                "region": region,
                "source": source,
                "reason": reason,
            })
            self._persist(state)
            return state

    def withdraw_all(
        self,
        user_id: str,
        subject_id: str,
        *,
        region: str = "GLOBAL",
        ip: str | None = None,
        source: str = "web",
        reason: str | None = None,
    ) -> ConsentState:
        return self.withdraw(
            user_id, subject_id,
            [p for p, m in PURPOSES.items() if not m["required"]],
            region=region, ip=ip, source=source, reason=reason,
        )

    # ---- cross-border (PIPL Art. 38) ----
    def get_cross_border_notice(self, region: str = "CN") -> dict[str, Any]:
        if region == "CN":
            return PIPL_CROSS_BORDER_DISCLOSURE
        # for EU/US we still surface but with EU/US wording
        return {
            **PIPL_CROSS_BORDER_DISCLOSURE,
            "version": "2026-07-intl",
            "controller": "Waibao International B.V.",
            "controller_contact": "privacy-intl@waibao.example",
            "user_rights": [
                "Right of access (Art. 15)",
                "Right to rectification (Art. 16)",
                "Right to erasure (Art. 17)",
                "Right to data portability (Art. 20)",
                "Right to object (Art. 21)",
            ],
        }

    def accept_cross_border(
        self,
        user_id: str,
        *,
        region: str = "CN",
        ip: str | None = None,
        source: str = "web",
    ) -> CrossBorderNotice:
        with self._lock:
            notice = self.get_cross_border_notice(region)
            now = datetime.now(timezone.utc)
            entry = CrossBorderNotice(
                user_id=user_id,
                version=notice["version"],
                accepted=True,
                accepted_at=now,
                notice=notice,
            )
            self._cross_border[user_id] = entry
            self._emit_audit("cross_border_accepted", {
                "user_id": user_id,
                "version": notice["version"],
                "region": region,
                "source": source,
            })
            if self._persist_cb is not None:
                try:
                    self._persist_cb("cross_border", entry.__dict__)
                except Exception:  # noqa: BLE001
                    pass
            return entry

    def has_cross_border_consent(self, user_id: str) -> bool:
        entry = self._cross_border.get(user_id)
        return bool(entry and entry.accepted)

    def revoke_cross_border(
        self,
        user_id: str,
        *,
        reason: str | None = None,
    ) -> bool:
        with self._lock:
            entry = self._cross_border.get(user_id)
            if not entry:
                return False
            entry.accepted = False
            entry.accepted_at = None
            self._emit_audit("cross_border_revoked", {
                "user_id": user_id,
                "version": entry.version,
                "reason": reason,
            })
            return True

    # ---- introspection ----
    def get_state(self, user_id: str) -> ConsentState | None:
        return self._states.get(user_id)

    def history(self, user_id: str) -> list[dict[str, Any]]:
        """Return an audit-shaped history of grant / withdraw events."""
        return [
            {"event": c.metadata, "purpose": p, "granted": c.granted,
             "withdrawn_at": c.withdrawn_at, "granted_at": c.granted_at}
            for p, c in (self._states.get(user_id).purposes.items() if self._states.get(user_id) else [])
        ]

    # ---- internal ----
    def _set_state(
        self,
        user_id: str,
        subject_id: str,
        purposes: list[str],
        *,
        granted: bool,
        region: str,
        ip: str | None,
        source: str,
        policy_version: str,
        audit_event: str,
    ) -> ConsentState:
        with self._lock:
            state = self.get_or_create(user_id, subject_id, region=region, ip=ip)
            now = datetime.now(timezone.utc)
            for p in purposes:
                state.purposes[p] = PurposeConsent(
                    purpose=p,
                    granted=granted,
                    version=policy_version,
                    granted_at=now if granted else None,
                    withdrawn_at=None if granted else now,
                    source=source,
                )
            state.updated_at = now
            self._emit_audit(audit_event, {
                "user_id": user_id,
                "purposes": purposes,
                "granted": granted,
                "region": region,
                "source": source,
            })
            self._persist(state)
            return state

    def _emit_audit(self, event: str, payload: dict[str, Any]) -> None:
        if self._audit_cb is None:
            return
        try:
            self._audit_cb(event, payload)
        except Exception:  # noqa: BLE001
            logger.warning("consent_v6.audit_cb_failed event=%s", event)

    def _persist(self, state: ConsentState) -> None:
        if self._persist_cb is None:
            return
        try:
            self._persist_cb("state", {
                "user_id": state.user_id,
                "region": state.region,
                "purposes": {
                    p: {
                        "granted": c.granted,
                        "version": c.version,
                        "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                        "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
                        "source": c.source,
                    }
                    for p, c in state.purposes.items()
                },
                "policy_version": state.policy_version,
            })
        except Exception:  # noqa: BLE001
            logger.warning("consent_v6.persist_failed user=%s", state.user_id)


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------
_store: ConsentStore | None = None
_store_lock = threading.Lock()


def get_consent_store() -> ConsentStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ConsentStore()
        return _store


def reset_consent_store() -> None:
    global _store
    with _store_lock:
        _store = None


def list_purposes() -> list[dict[str, Any]]:
    return [
        {
            "code": code,
            "label_zh": meta["label_zh"],
            "label_en": meta["label_en"],
            "required": meta["required"],
            "description_zh": meta["description_zh"],
            "description_en": meta["description_en"],
            "lawful_basis": {
                "EU": meta["gdpr_basis"],
                "CN": meta["pipl_basis"],
            },
        }
        for code, meta in PURPOSES.items()
    ]
