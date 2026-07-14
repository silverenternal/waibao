"""v10.0 T5002 — Unified Service-layer error handling.

This module is the single source of truth for **service-layer** errors.  It
sits one layer below the HTTP boundary (``exceptions.APIError``) and is meant
to be raised from any of the ~56 service modules under
``backend/services/``.

Design goals
------------
* A single exception class — :class:`ServiceError` — carrying a stable
  ``code``, a human message, an HTTP ``status_code`` and an optional
  ``retry_after`` hint.
* A ``100+`` code taxonomy grouped by module (auth, candidate, role,
  matching, billing, agent, integration, platform …) so services never
  raise magic strings.
* An ``error_response()`` helper producing a canonical JSON body.
* Zero coupling to FastAPI so services stay import-light; the API layer
  translates :class:`ServiceError` → HTTP in ``api/middleware.py``.

Interop
-------
``ServiceError`` interoperates with the older ``errors.ErrorCode`` /
``exceptions.APIError`` pair:

* ``ServiceError.to_api_error()`` converts to an ``APIError`` when a
  service error must cross the HTTP boundary through the legacy handler.
* Every :class:`ServiceErrorCode` value is a plain string, so the two
  taxonomies can be compared / logged uniformly.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Mapping, Optional

logger = logging.getLogger("recruittech.platform.errors")


# ===========================================================================
# Error code taxonomy — grouped by module (100+ codes)
# ===========================================================================
class ServiceErrorCode(str, Enum):
    """Stable service-layer error codes, grouped by module.

    Naming: ``<MODULE>_<CONDITION>``.  The string *value* mirrors the member
    name so ``ServiceErrorCode("AUTH_INVALID_CREDENTIALS")`` round-trips.
    """

    # ---- Generic / Core (10) ---------------------------------------------
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"

    # ---- Resilience / Infra (8) ------------------------------------------
    TIMEOUT = "TIMEOUT"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    CACHE_ERROR = "CACHE_ERROR"

    # ---- Auth / Tenant (12) ----------------------------------------------
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_INSUFFICIENT_ROLE = "AUTH_INSUFFICIENT_ROLE"
    AUTH_USER_DISABLED = "AUTH_USER_DISABLED"
    AUTH_MISSING_TENANT = "AUTH_MISSING_TENANT"
    AUTH_TENANT_MISMATCH = "AUTH_TENANT_MISMATCH"
    AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED"
    AUTH_MFA_REQUIRED = "AUTH_MFA_REQUIRED"
    AUTH_API_KEY_INVALID = "AUTH_API_KEY_INVALID"
    AUTH_API_KEY_REVOKED = "AUTH_API_KEY_REVOKED"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"

    # ---- Quota / Billing (12) --------------------------------------------
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    QUOTA_TENANT_LIMIT = "QUOTA_TENANT_LIMIT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PLAN_UPGRADE_REQUIRED = "PLAN_UPGRADE_REQUIRED"
    SERVICE_DISABLED = "SERVICE_DISABLED"
    FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"
    QUOTE_NOT_FOUND = "QUOTE_NOT_FOUND"
    QUOTE_ALREADY_ACCEPTED = "QUOTE_ALREADY_ACCEPTED"
    QUOTE_INVALID_AMOUNT = "QUOTE_INVALID_AMOUNT"
    INVOICE_NOT_FOUND = "INVOICE_NOT_FOUND"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_PROVIDER_ERROR = "PAYMENT_PROVIDER_ERROR"

    # ---- Candidate / Jobseeker (10) --------------------------------------
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    CANDIDATE_ALREADY_EXISTS = "CANDIDATE_ALREADY_EXISTS"
    CANDIDATE_INVALID_RESUME = "CANDIDATE_INVALID_RESUME"
    CANDIDATE_DUPLICATE = "CANDIDATE_DUPLICATE"
    CANDIDATE_ARCHIVED = "CANDIDATE_ARCHIVED"
    CANDIDATE_PROFILE_INCOMPLETE = "CANDIDATE_PROFILE_INCOMPLETE"
    PROFILE_EXTRACTION_FAILED = "PROFILE_EXTRACTION_FAILED"
    RESUME_PARSE_FAILED = "RESUME_PARSE_FAILED"
    JOURNAL_NOT_FOUND = "JOURNAL_NOT_FOUND"
    CAREER_PLAN_NOT_FOUND = "CAREER_PLAN_NOT_FOUND"

    # ---- Role / Employer (10) --------------------------------------------
    ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
    ROLE_ALREADY_CLOSED = "ROLE_ALREADY_CLOSED"
    ROLE_INVALID_STATE = "ROLE_INVALID_STATE"
    ROLE_BUDGET_EXCEEDED = "ROLE_BUDGET_EXCEEDED"
    ROLE_REQUIRED_FIELDS_MISSING = "ROLE_REQUIRED_FIELDS_MISSING"
    JOB_SPEC_INVALID = "JOB_SPEC_INVALID"
    JD_GENERATION_FAILED = "JD_GENERATION_FAILED"
    TALENT_BRIEF_INCOMPLETE = "TALENT_BRIEF_INCOMPLETE"
    EMPLOYER_NOT_FOUND = "EMPLOYER_NOT_FOUND"
    EMPLOYER_UNVERIFIED = "EMPLOYER_UNVERIFIED"

    # ---- Matching (10) ---------------------------------------------------
    MATCH_NOT_FOUND = "MATCH_NOT_FOUND"
    MATCH_SCORE_BELOW_THRESHOLD = "MATCH_SCORE_BELOW_THRESHOLD"
    MATCH_EXPLANATION_FAILED = "MATCH_EXPLANATION_FAILED"
    MATCH_NO_CANDIDATES = "MATCH_NO_CANDIDATES"
    MATCH_NO_ROLES = "MATCH_NO_ROLES"
    MATCH_WEIGHTS_INVALID = "MATCH_WEIGHTS_INVALID"
    MATCH_EMBEDDING_FAILED = "MATCH_EMBEDDING_FAILED"
    MATCH_FEEDBACK_INVALID = "MATCH_FEEDBACK_INVALID"
    CONSENSUS_COMPUTE_FAILED = "CONSENSUS_COMPUTE_FAILED"
    RECOMMENDATION_FAILED = "RECOMMENDATION_FAILED"

    # ---- Compliance / Privacy (10) ---------------------------------------
    COMPLIANCE_VIOLATION = "COMPLIANCE_VIOLATION"
    COMPLIANCE_DOCUMENT_EXPIRED = "COMPLIANCE_DOCUMENT_EXPIRED"
    COMPLIANCE_DOCUMENT_MISSING = "COMPLIANCE_DOCUMENT_MISSING"
    COMPLIANCE_BIAS_DETECTED = "COMPLIANCE_BIAS_DETECTED"
    COMPLIANCE_AUDIT_FAILED = "COMPLIANCE_AUDIT_FAILED"
    GDPR_DELETE_FAILED = "GDPR_DELETE_FAILED"
    GDPR_EXPORT_FAILED = "GDPR_EXPORT_FAILED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    PII_ENCRYPTION_FAILED = "PII_ENCRYPTION_FAILED"
    DATA_RESIDENCY_VIOLATION = "DATA_RESIDENCY_VIOLATION"

    # ---- LLM / Agents (12) -----------------------------------------------
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_BUDGET_EXCEEDED = "LLM_BUDGET_EXCEEDED"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    AGENT_NOT_REGISTERED = "AGENT_NOT_REGISTERED"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"
    AGENT_INPUT_INVALID = "AGENT_INPUT_INVALID"
    AGENT_OUTPUT_INVALID = "AGENT_OUTPUT_INVALID"
    AGENT_PERSONA_FORBIDDEN = "AGENT_PERSONA_FORBIDDEN"
    AGENT_DEGRADED = "AGENT_DEGRADED"
    AGENT_PII_DETECTED = "AGENT_PII_DETECTED"
    AGENT_INJECTION_BLOCKED = "AGENT_INJECTION_BLOCKED"
    PROMPT_NOT_FOUND = "PROMPT_NOT_FOUND"

    # ---- Integrations / External (12) ------------------------------------
    INTEGRATION_WEBHOOK_INVALID = "INTEGRATION_WEBHOOK_INVALID"
    INTEGRATION_SIGNATURE_INVALID = "INTEGRATION_SIGNATURE_INVALID"
    INTEGRATION_OAUTH_FAILED = "INTEGRATION_OAUTH_FAILED"
    INTEGRATION_API_RATE_LIMITED = "INTEGRATION_API_RATE_LIMITED"
    INTEGRATION_PAYLOAD_TOO_LARGE = "INTEGRATION_PAYLOAD_TOO_LARGE"
    INTEGRATION_NOT_CONFIGURED = "INTEGRATION_NOT_CONFIGURED"
    ATS_SYNC_FAILED = "ATS_SYNC_FAILED"
    CALENDAR_SYNC_FAILED = "CALENDAR_SYNC_FAILED"
    NOTIFY_DELIVERY_FAILED = "NOTIFY_DELIVERY_FAILED"
    VIDEO_PROVIDER_ERROR = "VIDEO_PROVIDER_ERROR"
    BACKGROUND_CHECK_FAILED = "BACKGROUND_CHECK_FAILED"
    ASSESSMENT_PROVIDER_ERROR = "ASSESSMENT_PROVIDER_ERROR"

    # ---- Realtime / Rooms / Support (10) ---------------------------------
    REALTIME_CONNECTION_FAILED = "REALTIME_CONNECTION_FAILED"
    REALTIME_CHANNEL_NOT_FOUND = "REALTIME_CHANNEL_NOT_FOUND"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ROOM_PARTICIPANT_LIMIT = "ROOM_PARTICIPANT_LIMIT"
    MESSAGE_RATE_LIMITED = "MESSAGE_RATE_LIMITED"
    TICKET_NOT_FOUND = "TICKET_NOT_FOUND"
    TICKET_ALREADY_CLOSED = "TICKET_ALREADY_CLOSED"
    HANDOFF_FAILED = "HANDOFF_FAILED"
    NOTIFICATION_PREF_INVALID = "NOTIFICATION_PREF_INVALID"
    FILE_STORAGE_ERROR = "FILE_STORAGE_ERROR"


# ===========================================================================
# code → (http_status, default_message)
# ===========================================================================
_DEFAULT_STATUS = 500

STATUS_BY_CODE: dict[ServiceErrorCode, int] = {
    # Core
    ServiceErrorCode.INTERNAL_ERROR: 500,
    ServiceErrorCode.UNKNOWN_ERROR: 500,
    ServiceErrorCode.VALIDATION_ERROR: 422,
    ServiceErrorCode.NOT_FOUND: 404,
    ServiceErrorCode.ALREADY_EXISTS: 409,
    ServiceErrorCode.CONFLICT: 409,
    ServiceErrorCode.BAD_REQUEST: 400,
    ServiceErrorCode.PRECONDITION_FAILED: 412,
    ServiceErrorCode.NOT_IMPLEMENTED: 501,
    ServiceErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    # Resilience
    ServiceErrorCode.TIMEOUT: 504,
    ServiceErrorCode.RETRY_EXHAUSTED: 503,
    ServiceErrorCode.CIRCUIT_OPEN: 503,
    ServiceErrorCode.RATE_LIMITED: 429,
    ServiceErrorCode.UPSTREAM_ERROR: 502,
    ServiceErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ServiceErrorCode.DATABASE_ERROR: 500,
    ServiceErrorCode.CACHE_ERROR: 500,
    # Auth
    ServiceErrorCode.AUTH_INVALID_CREDENTIALS: 401,
    ServiceErrorCode.AUTH_TOKEN_EXPIRED: 401,
    ServiceErrorCode.AUTH_TOKEN_INVALID: 401,
    ServiceErrorCode.AUTH_INSUFFICIENT_ROLE: 403,
    ServiceErrorCode.AUTH_USER_DISABLED: 403,
    ServiceErrorCode.AUTH_MISSING_TENANT: 400,
    ServiceErrorCode.AUTH_TENANT_MISMATCH: 403,
    ServiceErrorCode.AUTH_SESSION_EXPIRED: 401,
    ServiceErrorCode.AUTH_MFA_REQUIRED: 401,
    ServiceErrorCode.AUTH_API_KEY_INVALID: 401,
    ServiceErrorCode.AUTH_API_KEY_REVOKED: 401,
    ServiceErrorCode.AUTH_PERMISSION_DENIED: 403,
    # Quota / Billing
    ServiceErrorCode.QUOTA_EXCEEDED: 429,
    ServiceErrorCode.QUOTA_TENANT_LIMIT: 429,
    ServiceErrorCode.BUDGET_EXCEEDED: 402,
    ServiceErrorCode.PLAN_UPGRADE_REQUIRED: 402,
    ServiceErrorCode.SERVICE_DISABLED: 404,
    ServiceErrorCode.FEATURE_NOT_ENABLED: 403,
    ServiceErrorCode.QUOTE_NOT_FOUND: 404,
    ServiceErrorCode.QUOTE_ALREADY_ACCEPTED: 409,
    ServiceErrorCode.QUOTE_INVALID_AMOUNT: 422,
    ServiceErrorCode.INVOICE_NOT_FOUND: 404,
    ServiceErrorCode.PAYMENT_FAILED: 402,
    ServiceErrorCode.PAYMENT_PROVIDER_ERROR: 502,
    # Candidate
    ServiceErrorCode.CANDIDATE_NOT_FOUND: 404,
    ServiceErrorCode.CANDIDATE_ALREADY_EXISTS: 409,
    ServiceErrorCode.CANDIDATE_INVALID_RESUME: 422,
    ServiceErrorCode.CANDIDATE_DUPLICATE: 409,
    ServiceErrorCode.CANDIDATE_ARCHIVED: 410,
    ServiceErrorCode.CANDIDATE_PROFILE_INCOMPLETE: 422,
    ServiceErrorCode.PROFILE_EXTRACTION_FAILED: 500,
    ServiceErrorCode.RESUME_PARSE_FAILED: 422,
    ServiceErrorCode.JOURNAL_NOT_FOUND: 404,
    ServiceErrorCode.CAREER_PLAN_NOT_FOUND: 404,
    # Role
    ServiceErrorCode.ROLE_NOT_FOUND: 404,
    ServiceErrorCode.ROLE_ALREADY_CLOSED: 409,
    ServiceErrorCode.ROLE_INVALID_STATE: 409,
    ServiceErrorCode.ROLE_BUDGET_EXCEEDED: 422,
    ServiceErrorCode.ROLE_REQUIRED_FIELDS_MISSING: 422,
    ServiceErrorCode.JOB_SPEC_INVALID: 422,
    ServiceErrorCode.JD_GENERATION_FAILED: 500,
    ServiceErrorCode.TALENT_BRIEF_INCOMPLETE: 422,
    ServiceErrorCode.EMPLOYER_NOT_FOUND: 404,
    ServiceErrorCode.EMPLOYER_UNVERIFIED: 403,
    # Matching
    ServiceErrorCode.MATCH_NOT_FOUND: 404,
    ServiceErrorCode.MATCH_SCORE_BELOW_THRESHOLD: 422,
    ServiceErrorCode.MATCH_EXPLANATION_FAILED: 500,
    ServiceErrorCode.MATCH_NO_CANDIDATES: 404,
    ServiceErrorCode.MATCH_NO_ROLES: 404,
    ServiceErrorCode.MATCH_WEIGHTS_INVALID: 422,
    ServiceErrorCode.MATCH_EMBEDDING_FAILED: 500,
    ServiceErrorCode.MATCH_FEEDBACK_INVALID: 422,
    ServiceErrorCode.CONSENSUS_COMPUTE_FAILED: 500,
    ServiceErrorCode.RECOMMENDATION_FAILED: 500,
    # Compliance
    ServiceErrorCode.COMPLIANCE_VIOLATION: 422,
    ServiceErrorCode.COMPLIANCE_DOCUMENT_EXPIRED: 410,
    ServiceErrorCode.COMPLIANCE_DOCUMENT_MISSING: 422,
    ServiceErrorCode.COMPLIANCE_BIAS_DETECTED: 422,
    ServiceErrorCode.COMPLIANCE_AUDIT_FAILED: 500,
    ServiceErrorCode.GDPR_DELETE_FAILED: 500,
    ServiceErrorCode.GDPR_EXPORT_FAILED: 500,
    ServiceErrorCode.CONSENT_REQUIRED: 403,
    ServiceErrorCode.PII_ENCRYPTION_FAILED: 500,
    ServiceErrorCode.DATA_RESIDENCY_VIOLATION: 451,
    # LLM / Agents
    ServiceErrorCode.LLM_PROVIDER_ERROR: 502,
    ServiceErrorCode.LLM_TIMEOUT: 504,
    ServiceErrorCode.LLM_RATE_LIMIT: 429,
    ServiceErrorCode.LLM_BUDGET_EXCEEDED: 402,
    ServiceErrorCode.LLM_INVALID_RESPONSE: 502,
    ServiceErrorCode.AGENT_NOT_REGISTERED: 501,
    ServiceErrorCode.AGENT_EXECUTION_FAILED: 500,
    ServiceErrorCode.AGENT_INPUT_INVALID: 422,
    ServiceErrorCode.AGENT_OUTPUT_INVALID: 502,
    ServiceErrorCode.AGENT_PERSONA_FORBIDDEN: 403,
    ServiceErrorCode.AGENT_DEGRADED: 503,
    ServiceErrorCode.AGENT_PII_DETECTED: 422,
    ServiceErrorCode.AGENT_INJECTION_BLOCKED: 422,
    ServiceErrorCode.PROMPT_NOT_FOUND: 404,
    # Integrations
    ServiceErrorCode.INTEGRATION_WEBHOOK_INVALID: 400,
    ServiceErrorCode.INTEGRATION_SIGNATURE_INVALID: 401,
    ServiceErrorCode.INTEGRATION_OAUTH_FAILED: 401,
    ServiceErrorCode.INTEGRATION_API_RATE_LIMITED: 429,
    ServiceErrorCode.INTEGRATION_PAYLOAD_TOO_LARGE: 413,
    ServiceErrorCode.INTEGRATION_NOT_CONFIGURED: 424,
    ServiceErrorCode.ATS_SYNC_FAILED: 502,
    ServiceErrorCode.CALENDAR_SYNC_FAILED: 502,
    ServiceErrorCode.NOTIFY_DELIVERY_FAILED: 502,
    ServiceErrorCode.VIDEO_PROVIDER_ERROR: 502,
    ServiceErrorCode.BACKGROUND_CHECK_FAILED: 502,
    ServiceErrorCode.ASSESSMENT_PROVIDER_ERROR: 502,
    # Realtime / Rooms / Support
    ServiceErrorCode.REALTIME_CONNECTION_FAILED: 503,
    ServiceErrorCode.REALTIME_CHANNEL_NOT_FOUND: 404,
    ServiceErrorCode.ROOM_NOT_FOUND: 404,
    ServiceErrorCode.ROOM_PARTICIPANT_LIMIT: 409,
    ServiceErrorCode.MESSAGE_RATE_LIMITED: 429,
    ServiceErrorCode.TICKET_NOT_FOUND: 404,
    ServiceErrorCode.TICKET_ALREADY_CLOSED: 409,
    ServiceErrorCode.HANDOFF_FAILED: 500,
    ServiceErrorCode.NOTIFICATION_PREF_INVALID: 422,
    ServiceErrorCode.FILE_STORAGE_ERROR: 500,
}

MESSAGE_BY_CODE: dict[ServiceErrorCode, str] = {
    ServiceErrorCode.INTERNAL_ERROR: "Internal service error",
    ServiceErrorCode.UNKNOWN_ERROR: "Unknown error",
    ServiceErrorCode.VALIDATION_ERROR: "Validation failed",
    ServiceErrorCode.NOT_FOUND: "Resource not found",
    ServiceErrorCode.ALREADY_EXISTS: "Resource already exists",
    ServiceErrorCode.CONFLICT: "Resource conflict",
    ServiceErrorCode.BAD_REQUEST: "Bad request",
    ServiceErrorCode.PRECONDITION_FAILED: "Precondition failed",
    ServiceErrorCode.NOT_IMPLEMENTED: "Not implemented",
    ServiceErrorCode.DEPENDENCY_UNAVAILABLE: "A required dependency is unavailable",
    ServiceErrorCode.TIMEOUT: "Operation timed out",
    ServiceErrorCode.RETRY_EXHAUSTED: "All retry attempts exhausted",
    ServiceErrorCode.CIRCUIT_OPEN: "Circuit breaker is open",
    ServiceErrorCode.RATE_LIMITED: "Too many requests",
    ServiceErrorCode.UPSTREAM_ERROR: "Upstream service returned an error",
    ServiceErrorCode.UPSTREAM_UNAVAILABLE: "Upstream service is unavailable",
    ServiceErrorCode.DATABASE_ERROR: "Database operation failed",
    ServiceErrorCode.CACHE_ERROR: "Cache operation failed",
    ServiceErrorCode.AUTH_INVALID_CREDENTIALS: "Invalid credentials",
    ServiceErrorCode.AUTH_TOKEN_EXPIRED: "Authentication token expired",
    ServiceErrorCode.AUTH_TOKEN_INVALID: "Authentication token invalid",
    ServiceErrorCode.AUTH_INSUFFICIENT_ROLE: "Insufficient role",
    ServiceErrorCode.AUTH_USER_DISABLED: "User account disabled",
    ServiceErrorCode.AUTH_MISSING_TENANT: "Tenant context missing",
    ServiceErrorCode.AUTH_TENANT_MISMATCH: "Tenant mismatch",
    ServiceErrorCode.AUTH_SESSION_EXPIRED: "Session expired",
    ServiceErrorCode.AUTH_MFA_REQUIRED: "Multi-factor authentication required",
    ServiceErrorCode.AUTH_API_KEY_INVALID: "API key invalid",
    ServiceErrorCode.AUTH_API_KEY_REVOKED: "API key revoked",
    ServiceErrorCode.AUTH_PERMISSION_DENIED: "Permission denied",
    ServiceErrorCode.QUOTA_EXCEEDED: "Quota exceeded",
    ServiceErrorCode.QUOTA_TENANT_LIMIT: "Tenant quota limit reached",
    ServiceErrorCode.BUDGET_EXCEEDED: "Budget exceeded",
    ServiceErrorCode.PLAN_UPGRADE_REQUIRED: "Plan upgrade required",
    ServiceErrorCode.SERVICE_DISABLED: "Service is disabled",
    ServiceErrorCode.FEATURE_NOT_ENABLED: "Feature not enabled for this tenant",
    ServiceErrorCode.QUOTE_NOT_FOUND: "Quote not found",
    ServiceErrorCode.QUOTE_ALREADY_ACCEPTED: "Quote already accepted",
    ServiceErrorCode.QUOTE_INVALID_AMOUNT: "Quote amount invalid",
    ServiceErrorCode.INVOICE_NOT_FOUND: "Invoice not found",
    ServiceErrorCode.PAYMENT_FAILED: "Payment failed",
    ServiceErrorCode.PAYMENT_PROVIDER_ERROR: "Payment provider error",
    ServiceErrorCode.CANDIDATE_NOT_FOUND: "Candidate not found",
    ServiceErrorCode.CANDIDATE_ALREADY_EXISTS: "Candidate already exists",
    ServiceErrorCode.CANDIDATE_INVALID_RESUME: "Resume invalid or unreadable",
    ServiceErrorCode.CANDIDATE_DUPLICATE: "Duplicate candidate",
    ServiceErrorCode.CANDIDATE_ARCHIVED: "Candidate is archived",
    ServiceErrorCode.CANDIDATE_PROFILE_INCOMPLETE: "Candidate profile incomplete",
    ServiceErrorCode.PROFILE_EXTRACTION_FAILED: "Profile extraction failed",
    ServiceErrorCode.RESUME_PARSE_FAILED: "Resume parsing failed",
    ServiceErrorCode.JOURNAL_NOT_FOUND: "Journal not found",
    ServiceErrorCode.CAREER_PLAN_NOT_FOUND: "Career plan not found",
    ServiceErrorCode.ROLE_NOT_FOUND: "Role not found",
    ServiceErrorCode.ROLE_ALREADY_CLOSED: "Role already closed",
    ServiceErrorCode.ROLE_INVALID_STATE: "Role in invalid state",
    ServiceErrorCode.ROLE_BUDGET_EXCEEDED: "Role budget exceeded",
    ServiceErrorCode.ROLE_REQUIRED_FIELDS_MISSING: "Required role fields missing",
    ServiceErrorCode.JOB_SPEC_INVALID: "Job spec invalid",
    ServiceErrorCode.JD_GENERATION_FAILED: "JD generation failed",
    ServiceErrorCode.TALENT_BRIEF_INCOMPLETE: "Talent brief incomplete",
    ServiceErrorCode.EMPLOYER_NOT_FOUND: "Employer not found",
    ServiceErrorCode.EMPLOYER_UNVERIFIED: "Employer not verified",
    ServiceErrorCode.MATCH_NOT_FOUND: "Match not found",
    ServiceErrorCode.MATCH_SCORE_BELOW_THRESHOLD: "Match score below threshold",
    ServiceErrorCode.MATCH_EXPLANATION_FAILED: "Match explanation failed",
    ServiceErrorCode.MATCH_NO_CANDIDATES: "No candidates for role",
    ServiceErrorCode.MATCH_NO_ROLES: "No roles for candidate",
    ServiceErrorCode.MATCH_WEIGHTS_INVALID: "Match weights invalid",
    ServiceErrorCode.MATCH_EMBEDDING_FAILED: "Embedding computation failed",
    ServiceErrorCode.MATCH_FEEDBACK_INVALID: "Match feedback invalid",
    ServiceErrorCode.CONSENSUS_COMPUTE_FAILED: "Consensus computation failed",
    ServiceErrorCode.RECOMMENDATION_FAILED: "Recommendation failed",
    ServiceErrorCode.COMPLIANCE_VIOLATION: "Compliance violation",
    ServiceErrorCode.COMPLIANCE_DOCUMENT_EXPIRED: "Compliance document expired",
    ServiceErrorCode.COMPLIANCE_DOCUMENT_MISSING: "Compliance document missing",
    ServiceErrorCode.COMPLIANCE_BIAS_DETECTED: "Bias detected",
    ServiceErrorCode.COMPLIANCE_AUDIT_FAILED: "Compliance audit failed",
    ServiceErrorCode.GDPR_DELETE_FAILED: "GDPR delete failed",
    ServiceErrorCode.GDPR_EXPORT_FAILED: "GDPR export failed",
    ServiceErrorCode.CONSENT_REQUIRED: "User consent required",
    ServiceErrorCode.PII_ENCRYPTION_FAILED: "PII encryption failed",
    ServiceErrorCode.DATA_RESIDENCY_VIOLATION: "Data residency violation",
    ServiceErrorCode.LLM_PROVIDER_ERROR: "LLM provider error",
    ServiceErrorCode.LLM_TIMEOUT: "LLM provider timed out",
    ServiceErrorCode.LLM_RATE_LIMIT: "LLM provider rate limit",
    ServiceErrorCode.LLM_BUDGET_EXCEEDED: "LLM budget exhausted",
    ServiceErrorCode.LLM_INVALID_RESPONSE: "LLM returned invalid response",
    ServiceErrorCode.AGENT_NOT_REGISTERED: "Agent not registered",
    ServiceErrorCode.AGENT_EXECUTION_FAILED: "Agent execution failed",
    ServiceErrorCode.AGENT_INPUT_INVALID: "Agent input invalid",
    ServiceErrorCode.AGENT_OUTPUT_INVALID: "Agent output invalid",
    ServiceErrorCode.AGENT_PERSONA_FORBIDDEN: "Persona not allowed for agent",
    ServiceErrorCode.AGENT_DEGRADED: "Agent running in degraded mode",
    ServiceErrorCode.AGENT_PII_DETECTED: "PII detected in agent input",
    ServiceErrorCode.AGENT_INJECTION_BLOCKED: "Prompt injection blocked",
    ServiceErrorCode.PROMPT_NOT_FOUND: "Prompt not found",
    ServiceErrorCode.INTEGRATION_WEBHOOK_INVALID: "Webhook payload invalid",
    ServiceErrorCode.INTEGRATION_SIGNATURE_INVALID: "Webhook signature invalid",
    ServiceErrorCode.INTEGRATION_OAUTH_FAILED: "OAuth handshake failed",
    ServiceErrorCode.INTEGRATION_API_RATE_LIMITED: "Third-party rate limit",
    ServiceErrorCode.INTEGRATION_PAYLOAD_TOO_LARGE: "Integration payload too large",
    ServiceErrorCode.INTEGRATION_NOT_CONFIGURED: "Integration not configured",
    ServiceErrorCode.ATS_SYNC_FAILED: "ATS sync failed",
    ServiceErrorCode.CALENDAR_SYNC_FAILED: "Calendar sync failed",
    ServiceErrorCode.NOTIFY_DELIVERY_FAILED: "Notification delivery failed",
    ServiceErrorCode.VIDEO_PROVIDER_ERROR: "Video provider error",
    ServiceErrorCode.BACKGROUND_CHECK_FAILED: "Background check failed",
    ServiceErrorCode.ASSESSMENT_PROVIDER_ERROR: "Assessment provider error",
    ServiceErrorCode.REALTIME_CONNECTION_FAILED: "Realtime connection failed",
    ServiceErrorCode.REALTIME_CHANNEL_NOT_FOUND: "Realtime channel not found",
    ServiceErrorCode.ROOM_NOT_FOUND: "Room not found",
    ServiceErrorCode.ROOM_PARTICIPANT_LIMIT: "Room participant limit reached",
    ServiceErrorCode.MESSAGE_RATE_LIMITED: "Message rate limited",
    ServiceErrorCode.TICKET_NOT_FOUND: "Ticket not found",
    ServiceErrorCode.TICKET_ALREADY_CLOSED: "Ticket already closed",
    ServiceErrorCode.HANDOFF_FAILED: "Handoff failed",
    ServiceErrorCode.NOTIFICATION_PREF_INVALID: "Notification preference invalid",
    ServiceErrorCode.FILE_STORAGE_ERROR: "File storage error",
}

# Codes that are inherently transient and safe to retry by default.
RETRYABLE_CODES: frozenset[ServiceErrorCode] = frozenset({
    ServiceErrorCode.TIMEOUT,
    ServiceErrorCode.UPSTREAM_ERROR,
    ServiceErrorCode.UPSTREAM_UNAVAILABLE,
    ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
    ServiceErrorCode.DATABASE_ERROR,
    ServiceErrorCode.CACHE_ERROR,
    ServiceErrorCode.LLM_PROVIDER_ERROR,
    ServiceErrorCode.LLM_TIMEOUT,
    ServiceErrorCode.ATS_SYNC_FAILED,
    ServiceErrorCode.CALENDAR_SYNC_FAILED,
    ServiceErrorCode.NOTIFY_DELIVERY_FAILED,
    ServiceErrorCode.VIDEO_PROVIDER_ERROR,
    ServiceErrorCode.PAYMENT_PROVIDER_ERROR,
})


def status_for(code: ServiceErrorCode) -> int:
    return STATUS_BY_CODE.get(code, _DEFAULT_STATUS)


def message_for(code: ServiceErrorCode) -> str:
    return MESSAGE_BY_CODE.get(code, "Unknown error")


def is_retryable(code: ServiceErrorCode) -> bool:
    return code in RETRYABLE_CODES


# ===========================================================================
# ServiceError
# ===========================================================================
class ServiceError(Exception):
    """The single exception type raised by service-layer code.

    Parameters
    ----------
    code:
        A :class:`ServiceErrorCode` (preferred) or raw string.
    message:
        Human-readable override.  Defaults to the code's canonical message.
    status_code:
        Explicit HTTP status; defaults to the code's canonical status.
    retry_after:
        Optional seconds hint for ``Retry-After`` (rate-limit / circuit).
    details:
        Free-form structured context merged into the JSON body under
        ``details``.  Never include secrets here.
    cause:
        Optional originating exception, chained for logs.
    request_id:
        Optional correlation id surfaced in the error envelope so a single
        failure can be traced end-to-end.  The API middleware fills this from
        the ``X-Request-ID`` header (or mints one) at the boundary; services
        may also set it explicitly via :meth:`with_request_id`.
    """

    def __init__(
        self,
        code: ServiceErrorCode | str,
        message: Optional[str] = None,
        *,
        status_code: Optional[int] = None,
        retry_after: Optional[int] = None,
        details: Optional[Mapping[str, Any]] = None,
        cause: Optional[BaseException] = None,
        request_id: Optional[str] = None,
    ) -> None:
        self.code = self._coerce_code(code)
        if isinstance(self.code, ServiceErrorCode):
            self.message = message or message_for(self.code)
            self.status_code = status_code or status_for(self.code)
        else:
            self.message = message or "Unknown error"
            self.status_code = status_code or _DEFAULT_STATUS
        self.retry_after = retry_after
        self.details: dict[str, Any] = dict(details or {})
        self.cause = cause
        self.request_id = request_id
        super().__init__(self.message)
        if cause is not None:
            self.__cause__ = cause

    def with_request_id(self, request_id: str) -> "ServiceError":
        """Attach a correlation id (builder, returns self for chaining)."""
        self.request_id = request_id
        return self

    @staticmethod
    def _coerce_code(code: ServiceErrorCode | str) -> ServiceErrorCode | str:
        if isinstance(code, ServiceErrorCode):
            return code
        try:
            return ServiceErrorCode(code)
        except ValueError:
            return code

    @property
    def code_value(self) -> str:
        return self.code.value if isinstance(self.code, ServiceErrorCode) else str(self.code)

    @property
    def retryable(self) -> bool:
        return isinstance(self.code, ServiceErrorCode) and is_retryable(self.code)

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON body, v10.0 envelope.

        Shape::

            {"error": {"code", "message", "retryable", "request_id",
                       ["details"], ["retry_after"]}}

        ``retryable`` and ``request_id`` are always present so clients can
        branch on them without truthiness checks; ``request_id`` is the empty
        string until the API middleware stamps it.
        """
        err: dict[str, Any] = {
            "code": self.code_value,
            "message": self.message,
            "retryable": self.retryable,
            "request_id": self.request_id or "",
        }
        if self.details:
            err["details"] = self.details
        if self.retry_after is not None:
            err["retry_after"] = self.retry_after
        return {"error": err}

    def headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.retry_after is not None:
            h["Retry-After"] = str(self.retry_after)
        return h

    def to_api_error(self):
        """Bridge to the legacy ``exceptions.APIError`` HTTP boundary type."""
        from exceptions import APIError

        return APIError(
            self.code_value,
            self.message,
            status_code=self.status_code,
            headers=self.headers() or None,
            extra={"details": self.details} if self.details else None,
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"ServiceError(code={self.code_value!r}, "
            f"status={self.status_code}, message={self.message!r})"
        )

    # ---- convenience constructors ---------------------------------------
    @classmethod
    def not_found(cls, resource: str = "Resource", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.NOT_FOUND, f"{resource} not found", **kw)

    @classmethod
    def validation(cls, message: str = "Validation failed", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.VALIDATION_ERROR, message, **kw)

    @classmethod
    def conflict(cls, message: str = "Resource conflict", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.CONFLICT, message, **kw)

    @classmethod
    def permission_denied(cls, message: str = "Permission denied", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.AUTH_PERMISSION_DENIED, message, **kw)

    @classmethod
    def rate_limited(cls, retry_after: int = 60, **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.RATE_LIMITED, retry_after=retry_after, **kw)

    @classmethod
    def timeout(cls, message: str = "Operation timed out", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.TIMEOUT, message, **kw)

    @classmethod
    def internal(cls, message: str = "Internal service error", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.INTERNAL_ERROR, message, **kw)

    @classmethod
    def upstream(cls, message: str = "Upstream error", **kw: Any) -> "ServiceError":
        return cls(ServiceErrorCode.UPSTREAM_ERROR, message, **kw)


# Domain-specific subclasses (optional richer typing for `except`) ----------
class ValidationError(ServiceError):
    def __init__(self, message: str = "Validation failed", **kw: Any) -> None:
        super().__init__(ServiceErrorCode.VALIDATION_ERROR, message, **kw)


class NotFoundError(ServiceError):
    def __init__(self, resource: str = "Resource", **kw: Any) -> None:
        super().__init__(ServiceErrorCode.NOT_FOUND, f"{resource} not found", **kw)


class AuthError(ServiceError):
    def __init__(self, code: ServiceErrorCode = ServiceErrorCode.AUTH_PERMISSION_DENIED,
                 message: Optional[str] = None, **kw: Any) -> None:
        super().__init__(code, message, **kw)


class ProviderError(ServiceError):
    """Raised when an external provider / upstream integration fails."""

    def __init__(self, message: str = "Upstream error",
                 code: ServiceErrorCode = ServiceErrorCode.UPSTREAM_ERROR, **kw: Any) -> None:
        super().__init__(code, message, **kw)


# ===========================================================================
# error_response helper
# ===========================================================================
def error_response(
    error: ServiceError | ServiceErrorCode | str,
    message: Optional[str] = None,
    *,
    status_code: Optional[int] = None,
    details: Optional[Mapping[str, Any]] = None,
    retry_after: Optional[int] = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    """Build a canonical ``(status_code, body, headers)`` triple.

    Accepts either a fully-formed :class:`ServiceError` or the raw pieces.
    Framework-agnostic so callers (FastAPI handlers, background workers,
    tests) can shape the transport however they like.
    """
    if isinstance(error, ServiceError):
        err = error
    else:
        err = ServiceError(
            error,
            message,
            status_code=status_code,
            details=details,
            retry_after=retry_after,
        )
    return err.status_code, err.to_dict(), err.headers()


# ===========================================================================
# Helpers for "收口 except Exception" (collapse bare excepts)
# ===========================================================================
def safe_call(
    fn: Callable[..., Any],
    *args: Any,
    default: Any = None,
    log: Optional[logging.Logger] = None,
    message: str = "Operation failed",
    **kwargs: Any,
) -> Any:
    """Run ``fn(*args, **kwargs)``; on *any* exception return ``default``.

    A typed replacement for the pervasive ``except Exception: pass`` pattern:
    instead of swallowing errors silently it logs them (when a logger is
    supplied) and returns a controlled default, so a failure never produces a
    hidden ``None`` downstream.  Use only for genuinely best-effort side
    effects (metrics, cache writes, fan-out notifications).
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — intentional collapse point
        if log is not None:
            log.warning("%s: %s", message, exc, exc_info=False)
        return default


def swallow(
    *,
    default: Any = None,
    log: Optional[logging.Logger] = None,
    message: str = "Operation failed",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator form of :func:`safe_call`.

    Example::

        @swallow(log=logger, message="metrics emit failed")
        def emit_metric(): ...
    """
    import functools

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return safe_call(fn, *args, default=default, log=log,
                             message=message, **kwargs)
        return wrapper

    return decorator


def wrap_unexpected(
    fn: Callable[..., Any],
    *args: Any,
    code: "ServiceErrorCode | str" = ServiceErrorCode.INTERNAL_ERROR,
    message: str = "Unexpected error",
    **kwargs: Any,
) -> Any:
    """Run ``fn``; re-raise any non-:class:`ServiceError` as a typed one.

    Use to wrap the *boundary* of a service call so callers only ever see
    :class:`ServiceError` (never a bare ``KeyError`` / ``ValueError``).
    Already-typed :class:`ServiceError` exceptions pass through unchanged.
    """
    try:
        return fn(*args, **kwargs)
    except ServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 — boundary translation
        raise ServiceError(code, message, cause=exc) from exc


__all__ = [
    "ServiceErrorCode",
    "ServiceError",
    "ValidationError",
    "NotFoundError",
    "AuthError",
    "ProviderError",
    "STATUS_BY_CODE",
    "MESSAGE_BY_CODE",
    "RETRYABLE_CODES",
    "status_for",
    "message_for",
    "is_retryable",
    "error_response",
    "safe_call",
    "swallow",
    "wrap_unexpected",
]
