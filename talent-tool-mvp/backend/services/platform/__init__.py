"""v5.0 services/platform/ public API."""
from __future__ import annotations

from .ab_test import get_hash_salt, set_hash_salt, Variant, Experiment, hash_bucket, assign_variant, MetricSample, MetricStore, get_metric_store, record_metric, compute_significance, create_experiment  # noqa: F401,F403
from .backup import StorageBackend, BackupConfig, BackupRecord, verify_supabase_pitr_config, report_pitr_settings, BackupManager, BackupScheduler, compute_rto_rpo_estimate  # noqa: F401,F403
from .collection import CollectionService  # noqa: F401,F403
from .credit_code_validator import CreditCodeCheckResult, normalize, is_valid, validate, check_digit  # noqa: F401,F403
from .crypto import encrypt, decrypt, mask  # noqa: F401,F403
from .handoff import HandoffService  # noqa: F401,F403
from .i18n import I18n  # noqa: F401,F403
from .permissions import Persona, PERSONA_ACCESS, PersonaUser, get_persona_user, require_persona, require_module  # noqa: F401,F403
from .quote import SENIORITY_BASE_FEES, POOL_DISCOUNT_PERCENTAGE, QUOTE_VALIDITY_DAYS, QuoteService  # noqa: F401,F403
from .region_config import RegionConfig, get_region_config, region_for_phone, list_regions  # noqa: F401,F403
from .region_router import RouteDecision, RegionAwareRouter, get_region_aware_router, resolve_supabase_target  # noqa: F401,F403

__all__: list[str] = [
    "get_hash_salt",
    "set_hash_salt",
    "Variant",
    "Experiment",
    "hash_bucket",
    "assign_variant",
    "MetricSample",
    "MetricStore",
    "get_metric_store",
    "record_metric",
    "compute_significance",
    "create_experiment",
    "StorageBackend",
    "BackupConfig",
    "BackupRecord",
    "verify_supabase_pitr_config",
    "report_pitr_settings",
    "BackupManager",
    "BackupScheduler",
    "compute_rto_rpo_estimate",
    "CollectionService",
    "CreditCodeCheckResult",
    "normalize",
    "is_valid",
    "validate",
    "check_digit",
    "encrypt",
    "decrypt",
    "mask",
    "HandoffService",
    "I18n",
    "Persona",
    "PERSONA_ACCESS",
    "PersonaUser",
    "get_persona_user",
    "require_persona",
    "require_module",
    "SENIORITY_BASE_FEES",
    "POOL_DISCOUNT_PERCENTAGE",
    "QUOTE_VALIDITY_DAYS",
    "QuoteService",
    "RegionConfig",
    "get_region_config",
    "region_for_phone",
    "list_regions",
    "RouteDecision",
    "RegionAwareRouter",
    "get_region_aware_router",
    "resolve_supabase_target",
]
