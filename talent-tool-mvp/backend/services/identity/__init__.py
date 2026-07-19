"""v11.2 — Identity verification service package.

甲方 (client) A-level requirement:
    jobseeker uploads 身份证 (id_card) / 学历证明 (education) / 简历 (resume)
    PDF/Word. AI extracts the main fields. If a document CANNOT be verified
    (unclear / fields inconsistent / not uploaded) its status shows 待上传
    (pending). Generate a clear, EDITABLE structured profile; save VERSIONS
    and iterate. AI never eliminates — only builds/updates the profile (增量).

Public surface:
    IdentityStatus           — dataclass with the per-doc status + display map.
    IdentityVerificationService — submit / compute_overall / get_status +
                               profile versioning (DB-resilient, in-memory
                               fallback when Supabase is unreachable).

Display map (shared contract):
    pending   -> 待上传
    submitted -> 待审核
    verified  -> 已认证
"""
from __future__ import annotations

from .verification import (
    DISPLAY_MAP,
    DOC_TYPES,
    IdentityStatus,
    IdentityVerificationService,
    get_identity_service,
)

__all__ = [
    "DISPLAY_MAP",
    "DOC_TYPES",
    "IdentityStatus",
    "IdentityVerificationService",
    "get_identity_service",
]
