"""Unit tests for the centralised error handling layer (T1606)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from errors import (
    ERROR_HTTP_STATUS,
    ERROR_MESSAGES,
    ErrorCode,
    default_message_for,
    http_status_for,
)
from exceptions import APIError
from setup import setup_application


# ---------------------------------------------------------------------------
# ErrorCode coverage
# ---------------------------------------------------------------------------

def test_error_code_count_is_at_least_50():
    """T1606 spec: 50+ error codes organised by module group."""
    members = list(ErrorCode.__members__.items())
    assert len(members) >= 50, f"expected 50+ codes, got {len(members)}"


def test_every_code_has_status_and_message():
    """Every code must be present in both lookup tables."""
    for code in ErrorCode:
        assert code in ERROR_HTTP_STATUS, f"missing status for {code}"
        assert code in ERROR_MESSAGES, f"missing message for {code}"
        # status codes must be valid HTTP
        assert 100 <= ERROR_HTTP_STATUS[code] <= 599
        # messages must be non-empty
        assert ERROR_MESSAGES[code].strip()


def test_error_codes_grouped_by_module_prefix():
    """Group invariants: each module prefix appears at least once."""
    prefixes = {
        "AUTH": ["AUTH_INVALID_CREDENTIALS"],
        "CANDIDATE": ["CANDIDATE_NOT_FOUND"],
        "ROLE": ["ROLE_NOT_FOUND"],
        "MATCH": ["MATCH_NOT_FOUND"],
        "COMPLIANCE": ["COMPLIANCE_VIOLATION"],
        "GDPR": ["GDPR_DELETE_REQUEST_FAILED"],
        "LLM": ["LLM_PROVIDER_ERROR"],
        "AGENT": ["AGENT_NOT_REGISTERED"],
        "PIPELINE": ["PIPELINE_INGEST_FAILED"],
        "ADAPTER": ["ADAPTER_NOT_FOUND"],
        "INTEGRATION": ["INTEGRATION_WEBHOOK_INVALID"],
        "QUOTE": ["QUOTE_NOT_FOUND"],
        "OFFER": ["OFFER_NOT_FOUND"],
        "PAYMENT": ["PAYMENT_FAILED"],
        "ROOM": ["ROOM_NOT_FOUND"],
        "REALTIME": ["REALTIME_CONNECTION_FAILED"],
    }
    for prefix, samples in prefixes.items():
        for name in samples:
            assert hasattr(ErrorCode, name), f"missing code {name}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_http_status_for_unknown_code_defaults_500():
    class _Fake(str):
        pass

    # Strings that are not valid codes return 500
    assert http_status_for("THIS_IS_NOT_A_CODE") == 500  # type: ignore[arg-type]


def test_default_message_for_known_code():
    assert default_message_for(ErrorCode.NOT_FOUND) == "Resource not found"


def test_default_message_for_unknown_string():
    assert default_message_for("nope") == "Unknown error"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# APIError
# ---------------------------------------------------------------------------

def test_api_error_uses_default_message_and_status():
    err = APIError(ErrorCode.CANDIDATE_NOT_FOUND)
    assert err.status_code == 404
    assert "Candidate" in err.detail
    assert err.code is ErrorCode.CANDIDATE_NOT_FOUND
    assert isinstance(err.headers, dict)
    assert err.to_dict() == {"detail": err.detail, "code": "CANDIDATE_NOT_FOUND"}


def test_api_error_overrides_detail_and_status():
    err = APIError(ErrorCode.VALIDATION_ERROR, "Email required", status_code=400)
    assert err.status_code == 400
    assert err.detail == "Email required"


def test_api_error_accepts_string_code():
    err = APIError("CUSTOM_THING", "boom", status_code=418)
    assert err.status_code == 418
    assert err.code == "CUSTOM_THING"  # not in enum, kept as-is


def test_api_error_invalid_type_raises_typeerror():
    import pytest

    with pytest.raises(TypeError):
        APIError(12345)  # type: ignore[arg-type]


def test_api_error_to_dict_includes_extra():
    err = APIError(
        ErrorCode.MATCH_NOT_FOUND,
        "no match",
        extra={"candidate_id": "abc", "role_id": "xyz"},
    )
    body = err.to_dict()
    assert body["candidate_id"] == "abc"
    assert body["role_id"] == "xyz"
    assert body["code"] == "MATCH_NOT_FOUND"


def test_convenience_constructors():
    assert APIError.not_found("Candidate").status_code == 404
    assert APIError.forbidden().status_code == 403
    assert APIError.unauthorized().status_code == 401
    assert APIError.conflict().status_code == 409
    assert APIError.validation().status_code == 422

    rl = APIError.rate_limited(retry_after=30)
    assert rl.status_code == 429
    assert rl.headers["Retry-After"] == "30"


# ---------------------------------------------------------------------------
# setup_application integration
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    app = FastAPI()
    setup_application(app)

    @app.get("/boom")
    async def boom():  # type: ignore[no-redef]
        raise APIError(ErrorCode.CANDIDATE_NOT_FOUND, "No candidate 42")

    @app.get("/validation")
    async def validation():  # type: ignore[no-redef]
        raise APIError(ErrorCode.VALIDATION_ERROR, "bad input")

    @app.get("/forbidden")
    async def forbidden():  # type: ignore[no-redef]
        raise APIError.forbidden("nope")

    return app


def test_setup_application_renders_api_error():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "CANDIDATE_NOT_FOUND"
    assert "candidate 42" in body["detail"]


def test_setup_application_renders_rate_limited_with_retry_after():
    app = FastAPI()
    setup_application(app)

    @app.get("/rl")
    async def rl():  # type: ignore[no-redef]
        raise APIError.rate_limited(retry_after=42)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/rl")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "42"


def test_setup_application_sets_request_id_header():
    app = FastAPI()
    setup_application(app)

    @app.get("/ping")
    async def ping():  # type: ignore[no-redef]
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) == 8