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
from .nodes import (  # noqa: E402,F401,F403  — v6.0 workflow nodes
    ActionNode, AgentNode, ConditionNode, DelayNode, HumanNode, NodeContext,
    TriggerNode, WorkflowNode, get_node, list_node_types,
)
from .workflow_engine import (  # noqa: E402,F401,F403  — v6.0 workflow engine
    Edge, InMemoryWorkflowStore, Node, RunStatus,
    WorkflowDefinition, WorkflowEngine, WorkflowResult,
)
from .workflow_store import (  # noqa: E402,F401,F403  — v6.0 workflow persistence
    SupabaseWorkflowStore, WorkflowRunner,
    get_workflow_runner, get_workflow_store, reset_workflow_runner,
    validate_definition,
)
from .workflow_templates import (  # noqa: E402,F401,F403
    BUILTIN_TEMPLATES, ONBOARDING_TEMPLATE, INTERVIEW_TEMPLATE,
    RESUME_SCORING_TEMPLATE, BIAS_REVIEW_TEMPLATE, SLA_TEMPLATE,
    get_template, list_templates,
)

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
    # v6.0 workflow surface
    "ActionNode", "AgentNode", "ConditionNode", "DelayNode", "HumanNode",
    "NodeContext", "TriggerNode", "WorkflowNode",
    "get_node", "list_node_types",
    "Edge", "InMemoryWorkflowStore", "Node", "RunStatus",
    "WorkflowDefinition", "WorkflowEngine", "WorkflowResult",
    # v6.0 workflow persistence + templates
    "SupabaseWorkflowStore", "WorkflowRunner",
    "get_workflow_runner", "get_workflow_store",
    "reset_workflow_runner", "validate_definition",
    "BUILTIN_TEMPLATES", "ONBOARDING_TEMPLATE", "INTERVIEW_TEMPLATE",
    "RESUME_SCORING_TEMPLATE", "BIAS_REVIEW_TEMPLATE", "SLA_TEMPLATE",
    "get_template", "list_templates",
]
