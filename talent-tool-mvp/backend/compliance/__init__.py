"""合规框架统一入口.

T1201 GDPR + T1202 中国合规:
    consent         — 用户同意记录 + cookie banner 服务
    audit           — 增强 v3.0 的 audit_log (GDPR Art. 30 处理活动记录)
    data_residency  — 数据驻留策略 (中国境内 / 海外)
    encryption      — PII 字段级加密 (fernet)
    policies        — ToS / Privacy / DPA 模板生成器
"""
from __future__ import annotations

from .audit import AuditLogger, get_audit_logger
from .consent import (
    ConsentBanner,
    ConsentDecision,
    ConsentRecord,
    ConsentService,
    get_consent_service,
)
from .data_residency import (
    Region,
    ResidencyPolicy,
    ResidencyRouter,
    audit_residency_decision,
    ensure_data_in_region,
    get_region_for_user,
    get_residency_router,
    set_user_region,
)
from .encryption import (
    PIIEncryptor,
    get_pii_encryptor,
    reset_pii_encryptor,
    assert_cryptography_available,
    CryptographyUnavailableError,
)
from .policies import (
    PolicyBundle,
    PolicyGenerator,
    get_policy_generator,
)

__all__ = [
    "AuditLogger",
    "ConsentBanner",
    "ConsentDecision",
    "ConsentRecord",
    "ConsentService",
    "PIIEncryptor",
    "PolicyBundle",
    "PolicyGenerator",
    "Region",
    "ResidencyPolicy",
    "ResidencyRouter",
    "audit_residency_decision",
    "ensure_data_in_region",
    "get_audit_logger",
    "get_consent_service",
    "get_pii_encryptor",
    "get_policy_generator",
    "get_region_for_user",
    "get_residency_router",
    "set_user_region",
]