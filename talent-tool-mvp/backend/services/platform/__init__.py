"""v5.0 services/platform/ public API."""
from __future__ import annotations

# T2601 + T2602: strict multi-tenant + rate limiting primitives
from .tenant_context import (  # noqa: E402,F401
    TenantContext, set_tenant_context, reset_tenant_context,
    get_tenant_context, get_tenant, with_tenant,
)
from .tenant_resolver import (  # noqa: E402,F401
    TenantResolver, get_tenant_context_dep, get_tenant_resolver,
)
from .rate_limiter import (  # noqa: E402,F401
    get_limiter, set_limiter, per_route_limit,
    rate_limit_exceeded_handler, install_slowapi,
)
from .quota import (  # noqa: E402,F401
    PlanLimits, get_plan, list_plans,
    QuotaStore, get_quota_store, reset_quota_store,
    enforce_request, enforce_resource, remaining,
)

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

# T2704: prompt v2 (Agenta vendor-in) + LLM-as-judge evaluator
from .prompt_v2 import (  # noqa: E402,F401,F403
    InMemoryPromptRegistry,
    METRIC_DIMENSIONS,
    PromptMetric,
    PromptRegistryError,
    PromptService,
    PromptStatus,
    PromptVersion,
    get_prompt_service,
    reset_prompt_service,
)
from .evaluator import (  # noqa: E402,F401,F403
    EvalCase,
    EvalRun,
    JudgeVerdict,
    PromptComparison,
    PromptEvaluator,
    compare_prompts,
    default_runner,
    gold_standard_suite,
    judge_output,
)

# T3003 — White-label + private deployment branding
from .whitelabel import (  # noqa: E402,F401,F403
    ALLOWED_FONT_FAMILIES,
    ALLOWED_LOCALES,
    ALLOWED_TEMPLATES,
    Branding,
    BrandingNotFoundError,
    BrandingValidationError,
    CSS_VAR_KEYS,
    WhitelabelError,
    WhitelabelService,
    build_fastapi_router as build_whitelabel_router,
    get_whitelabel_service,
    render_email_footer,
    render_email_header,
    render_email_html,
    render_pdf_report_brand,
    reset_whitelabel_service,
    to_css_variables,
)

# T3901 — Auto weekly report + anomaly detector
from .auto_report import (  # noqa: E402,F401,F403
    AutoReportService,
    DAUMetric,
    FeatureUsage,
    ReportFormat,
    RequirementUsage,
    SIXTEEN_REQUIREMENTS,
    WeeklyReport,
    get_auto_report_service,
    reset_auto_report_service,
)
from .anomaly_detector import (  # noqa: E402,F401,F403
    AnomalyDetector,
    AnomalyResult,
    AnomalyType,
    BehaviorInsight,
    FeatureUsageRow,
    Severity,
    get_anomaly_detector,
    reset_anomaly_detector,
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

    # T2601 strict multi-tenant
    "TenantContext", "set_tenant_context", "reset_tenant_context",
    "get_tenant_context", "get_tenant", "with_tenant",
    "TenantResolver", "get_tenant_context_dep", "get_tenant_resolver",
    # T2602 rate limiting + quota
    "get_limiter", "set_limiter", "per_route_limit",
    "rate_limit_exceeded_handler", "install_slowapi",
    "PlanLimits", "get_plan", "list_plans",
    "QuotaStore", "get_quota_store", "reset_quota_store",
    "enforce_request", "enforce_resource", "remaining",
    # T2603 audit v2
    "AuditContext", "audit", "audit_pii",
    "set_audit_context", "get_audit_context", "update_audit_context", "clear_audit_context",
    "get_audit_store", "reset_audit_store",
    "scan_module_for_pii", "build_audit_decorators", "coverage_report",
    "PII_FIELDS", "DEFAULT_LAWFUL_BASIS", "ACTION_DATA_CLASS",
    "compute_retention_until", "AuditRecord",
    # T2603 consent v6
    "ConsentStore", "ConsentState", "PurposeConsent", "CrossBorderNotice",
    "PURPOSES", "PIPL_CROSS_BORDER_DISCLOSURE",
    "get_consent_store", "reset_consent_store", "list_purposes",
    # T2704 prompt v2 (Agenta vendor-in)
    "PromptStatus", "PromptVersion", "PromptMetric", "PromptRegistryError",
    "InMemoryPromptRegistry", "PromptService",
    "get_prompt_service", "reset_prompt_service", "METRIC_DIMENSIONS",
    # T2704 evaluator
    "EvalCase", "JudgeVerdict", "EvalRun", "PromptEvaluator",
    "PromptComparison", "judge_output", "default_runner",
    "gold_standard_suite", "compare_prompts",
    # T3003 white-label
    "ALLOWED_FONT_FAMILIES", "ALLOWED_LOCALES", "ALLOWED_TEMPLATES",
    "Branding", "BrandingNotFoundError", "BrandingValidationError",
    "CSS_VAR_KEYS", "WhitelabelError", "WhitelabelService",
    "build_whitelabel_router", "get_whitelabel_service",
    "render_email_footer", "render_email_header",
    "render_email_html", "render_pdf_report_brand",
    "reset_whitelabel_service", "to_css_variables",

    # T3901 auto weekly report
    "DAUMetric", "FeatureUsage", "RequirementUsage", "WeeklyReport",
    "ReportFormat", "AutoReportService",
    "SIXTEEN_REQUIREMENTS",
    "get_auto_report_service", "reset_auto_report_service",
    # T3901 anomaly detector
    "AnomalyResult", "AnomalyType", "BehaviorInsight", "FeatureUsageRow",
    "Severity", "AnomalyDetector",
    "get_anomaly_detector", "reset_anomaly_detector",
]
