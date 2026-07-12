"""Centralised error codes for the Mothership backend (T1606).

Each error code carries:

* a stable string identifier (e.g. ``CANDIDATE_NOT_FOUND``)
* a numeric HTTP status
* a human-readable default message

Codes are grouped by module so they can be referenced safely across the
codebase without magic strings.  Adding a new code only requires appending
to the appropriate group; ``ErrorCode.__members__`` is regenerated at
class creation time.
"""
from __future__ import annotations

from enum import Enum
from typing import Final


class ErrorCode(str, Enum):
    """All application error codes, grouped by module."""

    # ------------------------------------------------------------------
    # Core / Generic (1xxx)
    # ------------------------------------------------------------------
    INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"
    VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
    NOT_FOUND: Final[str] = "NOT_FOUND"
    UNAUTHORIZED: Final[str] = "UNAUTHORIZED"
    FORBIDDEN: Final[str] = "FORBIDDEN"
    CONFLICT: Final[str] = "CONFLICT"
    RATE_LIMITED: Final[str] = "RATE_LIMITED"
    BAD_REQUEST: Final[str] = "BAD_REQUEST"
    SERVICE_UNAVAILABLE: Final[str] = "SERVICE_UNAVAILABLE"
    TIMEOUT: Final[str] = "TIMEOUT"

    # ------------------------------------------------------------------
    # Auth (2xxx)
    # ------------------------------------------------------------------
    AUTH_INVALID_CREDENTIALS: Final[str] = "AUTH_INVALID_CREDENTIALS"
    AUTH_TOKEN_EXPIRED: Final[str] = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID: Final[str] = "AUTH_TOKEN_INVALID"
    AUTH_INSUFFICIENT_ROLE: Final[str] = "AUTH_INSUFFICIENT_ROLE"
    AUTH_USER_DISABLED: Final[str] = "AUTH_USER_DISABLED"
    AUTH_MISSING_TENANT: Final[str] = "AUTH_MISSING_TENANT"

    # ------------------------------------------------------------------
    # Candidates (3xxx)
    # ------------------------------------------------------------------
    CANDIDATE_NOT_FOUND: Final[str] = "CANDIDATE_NOT_FOUND"
    CANDIDATE_ALREADY_EXISTS: Final[str] = "CANDIDATE_ALREADY_EXISTS"
    CANDIDATE_INVALID_RESUME: Final[str] = "CANDIDATE_INVALID_RESUME"
    CANDIDATE_DUPLICATE: Final[str] = "CANDIDATE_DUPLICATE"
    CANDIDATE_ARCHIVED: Final[str] = "CANDIDATE_ARCHIVED"
    CANDIDATE_PROFILE_INCOMPLETE: Final[str] = "CANDIDATE_PROFILE_INCOMPLETE"

    # ------------------------------------------------------------------
    # Roles (4xxx)
    # ------------------------------------------------------------------
    ROLE_NOT_FOUND: Final[str] = "ROLE_NOT_FOUND"
    ROLE_ALREADY_CLOSED: Final[str] = "ROLE_ALREADY_CLOSED"
    ROLE_INVALID_STATE: Final[str] = "ROLE_INVALID_STATE"
    ROLE_BUDGET_EXCEEDED: Final[str] = "ROLE_BUDGET_EXCEEDED"
    ROLE_REQUIRED_FIELDS_MISSING: Final[str] = "ROLE_REQUIRED_FIELDS_MISSING"

    # ------------------------------------------------------------------
    # Matching (5xxx)
    # ------------------------------------------------------------------
    MATCH_NOT_FOUND: Final[str] = "MATCH_NOT_FOUND"
    MATCH_SCORE_BELOW_THRESHOLD: Final[str] = "MATCH_SCORE_BELOW_THRESHOLD"
    MATCH_EXPLANATION_FAILED: Final[str] = "MATCH_EXPLANATION_FAILED"
    MATCH_NO_CANDIDATES: Final[str] = "MATCH_NO_CANDIDATES"
    MATCH_NO_ROLES: Final[str] = "MATCH_NO_ROLES"
    MATCH_WEIGHTS_INVALID: Final[str] = "MATCH_WEIGHTS_INVALID"

    # ------------------------------------------------------------------
    # Compliance (6xxx)
    # ------------------------------------------------------------------
    COMPLIANCE_VIOLATION: Final[str] = "COMPLIANCE_VIOLATION"
    COMPLIANCE_DOCUMENT_EXPIRED: Final[str] = "COMPLIANCE_DOCUMENT_EXPIRED"
    COMPLIANCE_DOCUMENT_MISSING: Final[str] = "COMPLIANCE_DOCUMENT_MISSING"
    COMPLIANCE_BIAS_DETECTED: Final[str] = "COMPLIANCE_BIAS_DETECTED"
    COMPLIANCE_AUDIT_FAILED: Final[str] = "COMPLIANCE_AUDIT_FAILED"
    GDPR_DELETE_REQUEST_FAILED: Final[str] = "GDPR_DELETE_REQUEST_FAILED"
    GDPR_EXPORT_REQUEST_FAILED: Final[str] = "GDPR_EXPORT_REQUEST_FAILED"
    CCPA_OPT_OUT_FAILED: Final[str] = "CCPA_OPT_OUT_FAILED"

    # ------------------------------------------------------------------
    # LLM / Agents (7xxx)
    # ------------------------------------------------------------------
    LLM_PROVIDER_ERROR: Final[str] = "LLM_PROVIDER_ERROR"
    LLM_TIMEOUT: Final[str] = "LLM_TIMEOUT"
    LLM_RATE_LIMIT: Final[str] = "LLM_RATE_LIMIT"
    LLM_BUDGET_EXCEEDED: Final[str] = "LLM_BUDGET_EXCEEDED"
    LLM_INVALID_RESPONSE: Final[str] = "LLM_INVALID_RESPONSE"
    AGENT_NOT_REGISTERED: Final[str] = "AGENT_NOT_REGISTERED"
    AGENT_EXECUTION_FAILED: Final[str] = "AGENT_EXECUTION_FAILED"
    COPILOT_QUERY_INVALID: Final[str] = "COPILOT_QUERY_INVALID"

    # ------------------------------------------------------------------
    # Pipeline / Ingest (8xxx)
    # ------------------------------------------------------------------
    PIPELINE_INGEST_FAILED: Final[str] = "PIPELINE_INGEST_FAILED"
    PIPELINE_NORMALIZE_FAILED: Final[str] = "PIPELINE_NORMALIZE_FAILED"
    PIPELINE_DEDUP_FAILED: Final[str] = "PIPELINE_DEDUP_FAILED"
    PIPELINE_ENRICH_FAILED: Final[str] = "PIPELINE_ENRICH_FAILED"
    ADAPTER_NOT_FOUND: Final[str] = "ADAPTER_NOT_FOUND"
    ADAPTER_AUTH_FAILED: Final[str] = "ADAPTER_AUTH_FAILED"

    # ------------------------------------------------------------------
    # Integrations / External (9xxx)
    # ------------------------------------------------------------------
    INTEGRATION_WEBHOOK_INVALID: Final[str] = "INTEGRATION_WEBHOOK_INVALID"
    INTEGRATION_WEBHOOK_SIGNATURE_INVALID: Final[str] = "INTEGRATION_WEBHOOK_SIGNATURE_INVALID"
    INTEGRATION_OAUTH_FAILED: Final[str] = "INTEGRATION_OAUTH_FAILED"
    INTEGRATION_API_RATE_LIMITED: Final[str] = "INTEGRATION_API_RATE_LIMITED"
    INTEGRATION_PAYLOAD_TOO_LARGE: Final[str] = "INTEGRATION_PAYLOAD_TOO_LARGE"

    # ------------------------------------------------------------------
    # Billing / Quotes / Offers (10xxx)
    # ------------------------------------------------------------------
    QUOTE_NOT_FOUND: Final[str] = "QUOTE_NOT_FOUND"
    QUOTE_ALREADY_ACCEPTED: Final[str] = "QUOTE_ALREADY_ACCEPTED"
    QUOTE_INVALID_AMOUNT: Final[str] = "QUOTE_INVALID_AMOUNT"
    OFFER_NOT_FOUND: Final[str] = "OFFER_NOT_FOUND"
    OFFER_NEGOTIATION_FAILED: Final[str] = "OFFER_NEGOTIATION_FAILED"
    PAYMENT_FAILED: Final[str] = "PAYMENT_FAILED"
    PAYMENT_PROVIDER_ERROR: Final[str] = "PAYMENT_PROVIDER_ERROR"
    INVOICE_NOT_FOUND: Final[str] = "INVOICE_NOT_FOUND"

    # ------------------------------------------------------------------
    # Realtime / Chat / Rooms (11xxx)
    # ------------------------------------------------------------------
    REALTIME_CONNECTION_FAILED: Final[str] = "REALTIME_CONNECTION_FAILED"
    REALTIME_CHANNEL_NOT_FOUND: Final[str] = "REALTIME_CHANNEL_NOT_FOUND"
    ROOM_NOT_FOUND: Final[str] = "ROOM_NOT_FOUND"
    ROOM_PARTICIPANT_LIMIT: Final[str] = "ROOM_PARTICIPANT_LIMIT"
    MESSAGE_RATE_LIMITED: Final[str] = "MESSAGE_RATE_LIMITED"


# ---------------------------------------------------------------------------
# Mapping: code → (http_status, default_message)
# ---------------------------------------------------------------------------

ERROR_HTTP_STATUS: Final[dict[ErrorCode, int]] = {
    # Core
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.TIMEOUT: 504,
    # Auth
    ErrorCode.AUTH_INVALID_CREDENTIALS: 401,
    ErrorCode.AUTH_TOKEN_EXPIRED: 401,
    ErrorCode.AUTH_TOKEN_INVALID: 401,
    ErrorCode.AUTH_INSUFFICIENT_ROLE: 403,
    ErrorCode.AUTH_USER_DISABLED: 403,
    ErrorCode.AUTH_MISSING_TENANT: 400,
    # Candidates
    ErrorCode.CANDIDATE_NOT_FOUND: 404,
    ErrorCode.CANDIDATE_ALREADY_EXISTS: 409,
    ErrorCode.CANDIDATE_INVALID_RESUME: 422,
    ErrorCode.CANDIDATE_DUPLICATE: 409,
    ErrorCode.CANDIDATE_ARCHIVED: 410,
    ErrorCode.CANDIDATE_PROFILE_INCOMPLETE: 422,
    # Roles
    ErrorCode.ROLE_NOT_FOUND: 404,
    ErrorCode.ROLE_ALREADY_CLOSED: 409,
    ErrorCode.ROLE_INVALID_STATE: 409,
    ErrorCode.ROLE_BUDGET_EXCEEDED: 422,
    ErrorCode.ROLE_REQUIRED_FIELDS_MISSING: 422,
    # Matching
    ErrorCode.MATCH_NOT_FOUND: 404,
    ErrorCode.MATCH_SCORE_BELOW_THRESHOLD: 422,
    ErrorCode.MATCH_EXPLANATION_FAILED: 500,
    ErrorCode.MATCH_NO_CANDIDATES: 404,
    ErrorCode.MATCH_NO_ROLES: 404,
    ErrorCode.MATCH_WEIGHTS_INVALID: 422,
    # Compliance
    ErrorCode.COMPLIANCE_VIOLATION: 422,
    ErrorCode.COMPLIANCE_DOCUMENT_EXPIRED: 410,
    ErrorCode.COMPLIANCE_DOCUMENT_MISSING: 422,
    ErrorCode.COMPLIANCE_BIAS_DETECTED: 422,
    ErrorCode.COMPLIANCE_AUDIT_FAILED: 500,
    ErrorCode.GDPR_DELETE_REQUEST_FAILED: 500,
    ErrorCode.GDPR_EXPORT_REQUEST_FAILED: 500,
    ErrorCode.CCPA_OPT_OUT_FAILED: 500,
    # LLM / Agents
    ErrorCode.LLM_PROVIDER_ERROR: 502,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_RATE_LIMIT: 429,
    ErrorCode.LLM_BUDGET_EXCEEDED: 402,
    ErrorCode.LLM_INVALID_RESPONSE: 502,
    ErrorCode.AGENT_NOT_REGISTERED: 501,
    ErrorCode.AGENT_EXECUTION_FAILED: 500,
    ErrorCode.COPILOT_QUERY_INVALID: 422,
    # Pipeline
    ErrorCode.PIPELINE_INGEST_FAILED: 500,
    ErrorCode.PIPELINE_NORMALIZE_FAILED: 500,
    ErrorCode.PIPELINE_DEDUP_FAILED: 500,
    ErrorCode.PIPELINE_ENRICH_FAILED: 500,
    ErrorCode.ADAPTER_NOT_FOUND: 404,
    ErrorCode.ADAPTER_AUTH_FAILED: 401,
    # Integrations
    ErrorCode.INTEGRATION_WEBHOOK_INVALID: 400,
    ErrorCode.INTEGRATION_WEBHOOK_SIGNATURE_INVALID: 401,
    ErrorCode.INTEGRATION_OAUTH_FAILED: 401,
    ErrorCode.INTEGRATION_API_RATE_LIMITED: 429,
    ErrorCode.INTEGRATION_PAYLOAD_TOO_LARGE: 413,
    # Billing
    ErrorCode.QUOTE_NOT_FOUND: 404,
    ErrorCode.QUOTE_ALREADY_ACCEPTED: 409,
    ErrorCode.QUOTE_INVALID_AMOUNT: 422,
    ErrorCode.OFFER_NOT_FOUND: 404,
    ErrorCode.OFFER_NEGOTIATION_FAILED: 422,
    ErrorCode.PAYMENT_FAILED: 402,
    ErrorCode.PAYMENT_PROVIDER_ERROR: 502,
    ErrorCode.INVOICE_NOT_FOUND: 404,
    # Realtime
    ErrorCode.REALTIME_CONNECTION_FAILED: 503,
    ErrorCode.REALTIME_CHANNEL_NOT_FOUND: 404,
    ErrorCode.ROOM_NOT_FOUND: 404,
    ErrorCode.ROOM_PARTICIPANT_LIMIT: 409,
    ErrorCode.MESSAGE_RATE_LIMITED: 429,
}


ERROR_MESSAGES: Final[dict[ErrorCode, str]] = {
    # Core
    ErrorCode.INTERNAL_ERROR: "Internal server error",
    ErrorCode.VALIDATION_ERROR: "Request validation failed",
    ErrorCode.NOT_FOUND: "Resource not found",
    ErrorCode.UNAUTHORIZED: "Authentication required",
    ErrorCode.FORBIDDEN: "Permission denied",
    ErrorCode.CONFLICT: "Resource conflict",
    ErrorCode.RATE_LIMITED: "Too many requests",
    ErrorCode.BAD_REQUEST: "Bad request",
    ErrorCode.SERVICE_UNAVAILABLE: "Service unavailable",
    ErrorCode.TIMEOUT: "Request timed out",
    # Auth
    ErrorCode.AUTH_INVALID_CREDENTIALS: "Invalid email or password",
    ErrorCode.AUTH_TOKEN_EXPIRED: "Authentication token has expired",
    ErrorCode.AUTH_TOKEN_INVALID: "Authentication token is invalid",
    ErrorCode.AUTH_INSUFFICIENT_ROLE: "User role does not permit this action",
    ErrorCode.AUTH_USER_DISABLED: "User account is disabled",
    ErrorCode.AUTH_MISSING_TENANT: "Tenant context missing from request",
    # Candidates
    ErrorCode.CANDIDATE_NOT_FOUND: "Candidate not found",
    ErrorCode.CANDIDATE_ALREADY_EXISTS: "Candidate already exists",
    ErrorCode.CANDIDATE_INVALID_RESUME: "Resume is invalid or unreadable",
    ErrorCode.CANDIDATE_DUPLICATE: "Duplicate candidate detected",
    ErrorCode.CANDIDATE_ARCHIVED: "Candidate is archived",
    ErrorCode.CANDIDATE_PROFILE_INCOMPLETE: "Candidate profile is incomplete",
    # Roles
    ErrorCode.ROLE_NOT_FOUND: "Role not found",
    ErrorCode.ROLE_ALREADY_CLOSED: "Role is already closed",
    ErrorCode.ROLE_INVALID_STATE: "Role is in an invalid state for this action",
    ErrorCode.ROLE_BUDGET_EXCEEDED: "Role budget exceeded",
    ErrorCode.ROLE_REQUIRED_FIELDS_MISSING: "Required role fields are missing",
    # Matching
    ErrorCode.MATCH_NOT_FOUND: "Match not found",
    ErrorCode.MATCH_SCORE_BELOW_THRESHOLD: "Match score below configured threshold",
    ErrorCode.MATCH_EXPLANATION_FAILED: "Failed to generate match explanation",
    ErrorCode.MATCH_NO_CANDIDATES: "No candidates available for this role",
    ErrorCode.MATCH_NO_ROLES: "No roles available for this candidate",
    ErrorCode.MATCH_WEIGHTS_INVALID: "Invalid matching weights configuration",
    # Compliance
    ErrorCode.COMPLIANCE_VIOLATION: "Compliance violation detected",
    ErrorCode.COMPLIANCE_DOCUMENT_EXPIRED: "Compliance document has expired",
    ErrorCode.COMPLIANCE_DOCUMENT_MISSING: "Compliance document is missing",
    ErrorCode.COMPLIANCE_BIAS_DETECTED: "Potential bias detected in match output",
    ErrorCode.COMPLIANCE_AUDIT_FAILED: "Compliance audit failed",
    ErrorCode.GDPR_DELETE_REQUEST_FAILED: "GDPR delete request failed",
    ErrorCode.GDPR_EXPORT_REQUEST_FAILED: "GDPR export request failed",
    ErrorCode.CCPA_OPT_OUT_FAILED: "CCPA opt-out request failed",
    # LLM
    ErrorCode.LLM_PROVIDER_ERROR: "LLM provider returned an error",
    ErrorCode.LLM_TIMEOUT: "LLM provider timed out",
    ErrorCode.LLM_RATE_LIMIT: "LLM provider rate limit hit",
    ErrorCode.LLM_BUDGET_EXCEEDED: "LLM budget for this user is exhausted",
    ErrorCode.LLM_INVALID_RESPONSE: "LLM provider returned an invalid response",
    ErrorCode.AGENT_NOT_REGISTERED: "Agent is not registered",
    ErrorCode.AGENT_EXECUTION_FAILED: "Agent execution failed",
    ErrorCode.COPILOT_QUERY_INVALID: "Copilot query is invalid",
    # Pipeline
    ErrorCode.PIPELINE_INGEST_FAILED: "Pipeline ingestion failed",
    ErrorCode.PIPELINE_NORMALIZE_FAILED: "Pipeline normalization failed",
    ErrorCode.PIPELINE_DEDUP_FAILED: "Pipeline deduplication failed",
    ErrorCode.PIPELINE_ENRICH_FAILED: "Pipeline enrichment failed",
    ErrorCode.ADAPTER_NOT_FOUND: "Adapter not found",
    ErrorCode.ADAPTER_AUTH_FAILED: "Adapter authentication failed",
    # Integrations
    ErrorCode.INTEGRATION_WEBHOOK_INVALID: "Webhook payload is invalid",
    ErrorCode.INTEGRATION_WEBHOOK_SIGNATURE_INVALID: "Webhook signature is invalid",
    ErrorCode.INTEGRATION_OAUTH_FAILED: "OAuth handshake failed",
    ErrorCode.INTEGRATION_API_RATE_LIMITED: "Third-party API rate limit hit",
    ErrorCode.INTEGRATION_PAYLOAD_TOO_LARGE: "Integration payload too large",
    # Billing
    ErrorCode.QUOTE_NOT_FOUND: "Quote not found",
    ErrorCode.QUOTE_ALREADY_ACCEPTED: "Quote has already been accepted",
    ErrorCode.QUOTE_INVALID_AMOUNT: "Quote amount is invalid",
    ErrorCode.OFFER_NOT_FOUND: "Offer not found",
    ErrorCode.OFFER_NEGOTIATION_FAILED: "Offer negotiation failed",
    ErrorCode.PAYMENT_FAILED: "Payment failed",
    ErrorCode.PAYMENT_PROVIDER_ERROR: "Payment provider error",
    ErrorCode.INVOICE_NOT_FOUND: "Invoice not found",
    # Realtime
    ErrorCode.REALTIME_CONNECTION_FAILED: "Realtime connection failed",
    ErrorCode.REALTIME_CHANNEL_NOT_FOUND: "Realtime channel not found",
    ErrorCode.ROOM_NOT_FOUND: "Room not found",
    ErrorCode.ROOM_PARTICIPANT_LIMIT: "Room participant limit reached",
    ErrorCode.MESSAGE_RATE_LIMITED: "Message rate limit exceeded",
}


def http_status_for(code: ErrorCode) -> int:
    """Return the canonical HTTP status for an error code."""
    return ERROR_HTTP_STATUS.get(code, 500)


def default_message_for(code: ErrorCode) -> str:
    """Return the default human-readable message for an error code."""
    return ERROR_MESSAGES.get(code, "Unknown error")


__all__ = [
    "ErrorCode",
    "ERROR_HTTP_STATUS",
    "ERROR_MESSAGES",
    "http_status_for",
    "default_message_for",
]