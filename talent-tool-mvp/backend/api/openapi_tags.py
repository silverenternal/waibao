"""v10.0 T5003 — OpenAPI tag taxonomy & metadata.

Centralises the API tag groups, their descriptions and external-docs links
so ``/docs`` and ``/redoc`` render a coherent, navigable surface instead of
80+ ad-hoc tags.  ``openapi_tags_metadata()`` is passed to
``FastAPI(openapi_tags=...)`` and ``apply_openapi(app)`` post-processes the
generated schema to attach richer descriptions + real request examples.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tag groups — (name, description). Ordered for the docs sidebar.
# ---------------------------------------------------------------------------
TAG_GROUPS: list[tuple[str, str]] = [
    ("system", "Health, readiness and platform metadata endpoints."),
    ("users", "Current-user profile and session endpoints."),
    ("auth", "Authentication, SSO/SAML and API-key management."),
    ("jobseeker", "Candidate-facing: profile, journal, emotion, career plan."),
    ("employer", "Employer-facing: JD, talent brief, compliance, policy, tone."),
    ("matching", "Two-way matching, explanations, feedback and consensus."),
    ("interview", "AI interview, scheduling, video and assessments."),
    ("offers", "Offers, salary, negotiation and quotes."),
    ("analytics", "Dashboards, BI, funnels and predictive insights."),
    ("collaboration", "Rooms, realtime, handoffs and multi-party dialogue."),
    ("support", "Tickets, SLA, escalation and notifications."),
    ("integrations", "ATS, calendar, DingTalk/Feishu, webhooks and corp sync."),
    ("marketplace", "Public service catalog and plugin marketplace."),
    ("compliance", "GDPR, consent, audit, bias and data residency."),
    ("billing", "Subscriptions, plans, invoices and cost."),
    ("admin", "Operator-only: config, feature flags, services, weights, audit."),
]

# Convenience: canonical tag name set.
TAG_NAMES: tuple[str, ...] = tuple(name for name, _ in TAG_GROUPS)

# Map fine-grained router tags → canonical group (best-effort normalisation).
TAG_ALIASES: dict[str, str] = {
    "auth-sso": "auth",
    "auth-miniprogram": "auth",
    "admin-api-keys": "admin",
    "admin-config": "admin",
    "admin-feature-flags": "admin",
    "admin-plugins": "admin",
    "admin-services": "admin",
    "analytics-v2": "analytics",
    "bi": "analytics",
    "predictive": "analytics",
    "assessment": "interview",
    "ai-interview": "interview",
    "video-interview": "interview",
    "background-check": "interview",
    "ats-integrations": "integrations",
    "corp-integrations": "integrations",
    "corp-events": "integrations",
    "dingtalk": "integrations",
    "feishu": "integrations",
    "gdpr_v2": "compliance",
    "bias": "compliance",
    "consensus_v2": "matching",
    "matching_feedback": "matching",
    "compare": "matching",
    "jd_marketing": "employer",
    "policy_explainer": "employer",
    "ps_detection": "compliance",
    "public-api": "marketplace",
    "public-services": "marketplace",
    "rag-collections": "analytics",
    "rag-documents": "analytics",
    "rag-query": "analytics",
    "memories": "jobseeker",
    "daily_suggestions": "jobseeker",
    "silence": "support",
    "escalated": "support",
    "events": "analytics",
    "exports": "analytics",
    "rules": "admin",
    "batch": "admin",
    "developer-portal": "integrations",
}


def canonical_tag(tag: str) -> str:
    """Normalise a router-level tag to its canonical group name."""
    if tag in TAG_NAMES:
        return tag
    return TAG_ALIASES.get(tag, tag)


def openapi_tags_metadata() -> list[dict[str, str]]:
    """Return the ``openapi_tags`` list for ``FastAPI(openapi_tags=...)``."""
    return [{"name": name, "description": desc} for name, desc in TAG_GROUPS]


# ---------------------------------------------------------------------------
# Standard error response schema shared by all endpoints.
# ---------------------------------------------------------------------------
ERROR_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "example": "CANDIDATE_NOT_FOUND"},
                "message": {"type": "string", "example": "Candidate not found"},
                "details": {"type": "object"},
                "retry_after": {"type": "integer", "example": 60},
            },
            "required": ["code", "message"],
        }
    },
}

STANDARD_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    400: {"description": "Bad request", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    401: {"description": "Unauthorized", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    403: {"description": "Forbidden", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    404: {"description": "Not found", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    422: {"description": "Validation error", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    429: {"description": "Rate limited", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
    500: {"description": "Internal error", "content": {"application/json": {"schema": ERROR_RESPONSE_SCHEMA}}},
}


def apply_openapi(app: Any) -> None:
    """Post-process an app's generated OpenAPI schema.

    * Merges in the canonical tag groups.
    * Adds the shared error-response component so clients can codegen it.
    Idempotent and failure-tolerant (docs generation must never break boot).
    """
    try:
        from fastapi.openapi.utils import get_openapi
    except Exception:  # pragma: no cover
        return

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=openapi_tags_metadata(),
        )
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas.setdefault("ErrorResponse", ERROR_RESPONSE_SCHEMA)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[assignment]


__all__ = [
    "TAG_GROUPS",
    "TAG_NAMES",
    "TAG_ALIASES",
    "canonical_tag",
    "openapi_tags_metadata",
    "ERROR_RESPONSE_SCHEMA",
    "STANDARD_ERROR_RESPONSES",
    "apply_openapi",
]
