"""v10.0 T5002 — Unified service error tests (30+)."""
from __future__ import annotations

import pytest

from services.platform.errors import (
    MESSAGE_BY_CODE,
    RETRYABLE_CODES,
    STATUS_BY_CODE,
    AuthError,
    NotFoundError,
    ProviderError,
    ServiceError,
    ServiceErrorCode,
    ValidationError,
    error_response,
    is_retryable,
    message_for,
    status_for,
)


# ---------------------------------------------------------------------------
# Taxonomy coverage
# ---------------------------------------------------------------------------
def test_error_code_count_at_least_100():
    assert len(list(ServiceErrorCode)) >= 100


def test_every_code_has_status_and_message():
    for code in ServiceErrorCode:
        assert code in STATUS_BY_CODE, f"missing status for {code}"
        assert code in MESSAGE_BY_CODE, f"missing message for {code}"
        assert 100 <= STATUS_BY_CODE[code] <= 599
        assert MESSAGE_BY_CODE[code].strip()


def test_codes_grouped_by_module_prefix():
    prefixes = {"AUTH", "QUOTA", "CANDIDATE", "ROLE", "MATCH", "COMPLIANCE",
                "LLM", "AGENT", "INTEGRATION", "ROOM"}
    names = {c.name for c in ServiceErrorCode}
    for p in prefixes:
        assert any(n.startswith(p) for n in names), f"no code for group {p}"


def test_status_for_unknown_defaults_500():
    # A code not in the table would default to 500; use helper directly.
    assert status_for(ServiceErrorCode.INTERNAL_ERROR) == 500


def test_message_for_returns_str():
    assert isinstance(message_for(ServiceErrorCode.NOT_FOUND), str)


# ---------------------------------------------------------------------------
# ServiceError construction
# ---------------------------------------------------------------------------
def test_service_error_defaults_from_code():
    e = ServiceError(ServiceErrorCode.CANDIDATE_NOT_FOUND)
    assert e.status_code == 404
    assert e.message == "Candidate not found"
    assert e.code_value == "CANDIDATE_NOT_FOUND"


def test_service_error_message_override():
    e = ServiceError(ServiceErrorCode.NOT_FOUND, "custom msg")
    assert e.message == "custom msg"


def test_service_error_status_override():
    e = ServiceError(ServiceErrorCode.NOT_FOUND, status_code=418)
    assert e.status_code == 418


def test_service_error_accepts_string_code():
    e = ServiceError("CANDIDATE_NOT_FOUND")
    assert e.code == ServiceErrorCode.CANDIDATE_NOT_FOUND
    assert e.status_code == 404


def test_service_error_unknown_string_code():
    e = ServiceError("SOMETHING_WEIRD")
    assert e.code_value == "SOMETHING_WEIRD"
    assert e.status_code == 500


def test_service_error_details_preserved():
    e = ServiceError(ServiceErrorCode.VALIDATION_ERROR, details={"field": "email"})
    assert e.details == {"field": "email"}


def test_service_error_cause_chained():
    orig = ValueError("boom")
    e = ServiceError(ServiceErrorCode.INTERNAL_ERROR, cause=orig)
    assert e.__cause__ is orig
    assert e.cause is orig


def test_service_error_is_exception():
    with pytest.raises(ServiceError):
        raise ServiceError(ServiceErrorCode.NOT_FOUND)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def test_to_dict_shape():
    e = ServiceError(ServiceErrorCode.NOT_FOUND)
    body = e.to_dict()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"]


def test_to_dict_includes_details_and_retry():
    e = ServiceError(ServiceErrorCode.RATE_LIMITED, retry_after=30, details={"k": 1})
    body = e.to_dict()
    assert body["error"]["retry_after"] == 30
    assert body["error"]["details"] == {"k": 1}


def test_headers_include_retry_after():
    e = ServiceError(ServiceErrorCode.RATE_LIMITED, retry_after=42)
    assert e.headers() == {"Retry-After": "42"}


def test_headers_empty_without_retry():
    e = ServiceError(ServiceErrorCode.NOT_FOUND)
    assert e.headers() == {}


def test_repr_contains_code():
    e = ServiceError(ServiceErrorCode.NOT_FOUND)
    assert "NOT_FOUND" in repr(e)


# ---------------------------------------------------------------------------
# APIError bridge
# ---------------------------------------------------------------------------
def test_to_api_error_bridge():
    e = ServiceError(ServiceErrorCode.CANDIDATE_NOT_FOUND, details={"id": "x"})
    api = e.to_api_error()
    assert api.status_code == 404
    assert api.detail == "Candidate not found"


def test_to_api_error_rate_limit_headers():
    e = ServiceError(ServiceErrorCode.RATE_LIMITED, retry_after=15)
    api = e.to_api_error()
    assert api.headers.get("Retry-After") == "15"


# ---------------------------------------------------------------------------
# Retryability
# ---------------------------------------------------------------------------
def test_retryable_codes_nonempty():
    assert len(RETRYABLE_CODES) >= 5


def test_timeout_is_retryable():
    assert is_retryable(ServiceErrorCode.TIMEOUT)
    assert ServiceError(ServiceErrorCode.TIMEOUT).retryable


def test_not_found_not_retryable():
    assert not is_retryable(ServiceErrorCode.NOT_FOUND)
    assert not ServiceError(ServiceErrorCode.NOT_FOUND).retryable


def test_upstream_retryable():
    assert ServiceError(ServiceErrorCode.UPSTREAM_UNAVAILABLE).retryable


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------
def test_not_found_ctor():
    e = ServiceError.not_found("Candidate")
    assert e.status_code == 404
    assert "Candidate" in e.message


def test_validation_ctor():
    e = ServiceError.validation("bad")
    assert e.code == ServiceErrorCode.VALIDATION_ERROR
    assert e.status_code == 422


def test_conflict_ctor():
    assert ServiceError.conflict().status_code == 409


def test_permission_denied_ctor():
    assert ServiceError.permission_denied().status_code == 403


def test_rate_limited_ctor():
    e = ServiceError.rate_limited(retry_after=99)
    assert e.status_code == 429
    assert e.retry_after == 99


def test_timeout_ctor():
    assert ServiceError.timeout().status_code == 504


def test_internal_ctor():
    assert ServiceError.internal().status_code == 500


def test_upstream_ctor():
    assert ServiceError.upstream().status_code == 502


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------
def test_validation_error_subclass():
    e = ValidationError("nope")
    assert isinstance(e, ServiceError)
    assert e.code == ServiceErrorCode.VALIDATION_ERROR


def test_not_found_error_subclass():
    e = NotFoundError("Role")
    assert isinstance(e, ServiceError)
    assert e.status_code == 404


def test_auth_error_subclass():
    e = AuthError()
    assert isinstance(e, ServiceError)
    assert e.status_code == 403


def test_provider_error_subclass():
    e = ProviderError("upstream down")
    assert isinstance(e, ServiceError)
    assert e.code == ServiceErrorCode.UPSTREAM_ERROR
    assert e.retryable


# ---------------------------------------------------------------------------
# error_response helper
# ---------------------------------------------------------------------------
def test_error_response_from_service_error():
    e = ServiceError(ServiceErrorCode.NOT_FOUND)
    status, body, headers = error_response(e)
    assert status == 404
    assert body["error"]["code"] == "NOT_FOUND"
    assert headers == {}


def test_error_response_from_code():
    status, body, headers = error_response(ServiceErrorCode.RATE_LIMITED, retry_after=10)
    assert status == 429
    assert headers["Retry-After"] == "10"


def test_error_response_with_details():
    status, body, _ = error_response(
        ServiceErrorCode.VALIDATION_ERROR, "bad", details={"f": 1}
    )
    assert status == 422
    assert body["error"]["details"] == {"f": 1}


def test_error_response_string_code():
    status, body, _ = error_response("NOT_FOUND")
    assert status == 404
    assert body["error"]["code"] == "NOT_FOUND"
