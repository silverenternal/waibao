"""v10.0 T5002/T5003 — Unified error-envelope tests.

Covers the canonical ``{error: {code, message, retryable, request_id, ...}}``
envelope, the ``ServiceError`` taxonomy, the ``request_id`` correlation
machinery and the ``safe_call`` / ``swallow`` / ``wrap_unexpected`` collapse
helpers.
"""
from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware import (
    RequestIdMiddleware,
    _error_body,
    _resolve_request_id,
    install_error_handlers,
    install_request_id_middleware,
)
from services.platform.errors import (
    AuthError,
    MESSAGE_BY_CODE,
    NotFoundError,
    ProviderError,
    RETRYABLE_CODES,
    STATUS_BY_CODE,
    ServiceError,
    ServiceErrorCode,
    ValidationError,
    error_response,
    is_retryable,
    message_for,
    safe_call,
    status_for,
    swallow,
    wrap_unexpected,
)


# ===========================================================================
# Envelope shape
# ===========================================================================
class TestErrorEnvelope:
    def test_envelope_has_code_message_retryable_request_id(self):
        err = ServiceError(ServiceErrorCode.NOT_FOUND)
        body = err.to_dict()
        e = body["error"]
        assert e["code"] == "NOT_FOUND"
        assert e["message"] == "Resource not found"
        assert e["retryable"] is False
        assert "request_id" in e

    def test_request_id_defaults_to_empty_string(self):
        body = ServiceError(ServiceErrorCode.INTERNAL_ERROR).to_dict()
        assert body["error"]["request_id"] == ""

    def test_with_request_id_attaches_and_serializes(self):
        err = ServiceError(ServiceErrorCode.NOT_FOUND).with_request_id("req_abc")
        assert err.request_id == "req_abc"
        assert err.to_dict()["error"]["request_id"] == "req_abc"

    def test_request_id_in_constructor(self):
        err = ServiceError(ServiceErrorCode.TIMEOUT, request_id="rid-1")
        assert err.to_dict()["error"]["request_id"] == "rid-1"

    def test_details_only_present_when_provided(self):
        e = ServiceError(ServiceErrorCode.VALIDATION_ERROR).to_dict()["error"]
        assert "details" not in e
        e2 = ServiceError(ServiceErrorCode.VALIDATION_ERROR, details={"field": "x"}).to_dict()["error"]
        assert e2["details"] == {"field": "x"}

    def test_retry_after_only_present_when_provided(self):
        e = ServiceError(ServiceErrorCode.RATE_LIMITED).to_dict()["error"]
        assert "retry_after" not in e
        e2 = ServiceError(ServiceErrorCode.RATE_LIMITED, retry_after=30).to_dict()["error"]
        assert e2["retry_after"] == 30


# ===========================================================================
# Taxonomy integrity
# ===========================================================================
class TestTaxonomy:
    def test_every_code_has_status_and_message(self):
        for code in ServiceErrorCode:
            assert code in STATUS_BY_CODE, f"{code} missing status"
            assert code in MESSAGE_BY_CODE, f"{code} missing message"

    def test_status_for_unknown_falls_back_to_500(self):
        assert status_for(ServiceErrorCode.INTERNAL_ERROR) == 500

    def test_message_for_returns_canonical(self):
        assert "not found" in message_for(ServiceErrorCode.NOT_FOUND).lower()

    def test_at_least_100_codes(self):
        assert len(list(ServiceErrorCode)) >= 100

    def test_retryable_flag_matches_set(self):
        for code in ServiceErrorCode:
            assert is_retryable(code) == (code in RETRYABLE_CODES)

    def test_transient_codes_are_retryable(self):
        for c in (ServiceErrorCode.TIMEOUT, ServiceErrorCode.UPSTREAM_ERROR,
                  ServiceErrorCode.DATABASE_ERROR, ServiceErrorCode.LLM_PROVIDER_ERROR):
            assert is_retryable(c) is True

    def test_client_errors_are_not_retryable(self):
        for c in (ServiceErrorCode.NOT_FOUND, ServiceErrorCode.VALIDATION_ERROR,
                  ServiceErrorCode.AUTH_PERMISSION_DENIED, ServiceErrorCode.CONFLICT):
            assert is_retryable(c) is False


# ===========================================================================
# Constructors & subclasses
# ===========================================================================
class TestConstructors:
    def test_not_found_subclass(self):
        err = NotFoundError("Widget")
        assert err.code == ServiceErrorCode.NOT_FOUND
        assert err.status_code == 404
        assert "Widget" in err.message

    def test_validation_subclass(self):
        err = ValidationError("bad input")
        assert err.code == ServiceErrorCode.VALIDATION_ERROR
        assert err.status_code == 422

    def test_auth_subclass_default_code(self):
        err = AuthError()
        assert err.code == ServiceErrorCode.AUTH_PERMISSION_DENIED
        assert err.status_code == 403

    def test_provider_subclass(self):
        err = ProviderError("stripe down")
        assert err.code == ServiceErrorCode.UPSTREAM_ERROR
        assert err.retryable is True

    def test_raw_string_code_unknown(self):
        err = ServiceError("SOMETHING_NEW", "x")
        assert err.code_value == "SOMETHING_NEW"
        assert err.status_code == 500

    def test_rate_limited_carries_retry_after(self):
        err = ServiceError.rate_limited(retry_after=42)
        assert err.status_code == 429
        assert err.retry_after == 42
        assert ("Retry-After", "42") in err.headers().items()

    def test_cause_is_chained(self):
        orig = KeyError("k")
        err = ServiceError(ServiceErrorCode.INTERNAL_ERROR, cause=orig)
        assert err.__cause__ is orig

    def test_code_value_property(self):
        assert ServiceError(ServiceErrorCode.TIMEOUT).code_value == "TIMEOUT"


# ===========================================================================
# error_response helper
# ===========================================================================
class TestErrorResponseHelper:
    def test_from_service_error(self):
        status, body, headers = error_response(ServiceError.not_found("X"))
        assert status == 404
        assert body["error"]["code"] == "NOT_FOUND"

    def test_from_raw_pieces(self):
        status, body, _ = error_response(
            ServiceErrorCode.RATE_LIMITED, "slow down", retry_after=5
        )
        assert status == 429
        assert body["error"]["retry_after"] == 5

    def test_to_api_error_bridge(self):
        err = ServiceError.not_found("X")
        api_err = err.to_api_error()
        assert api_err.status_code == 404


# ===========================================================================
# Collapse helpers: safe_call / swallow / wrap_unexpected
# ===========================================================================
class TestCollapseHelpers:
    def test_safe_call_returns_value_on_success(self):
        assert safe_call(lambda: 1 + 1) == 2

    def test_safe_call_returns_default_on_failure(self):
        assert safe_call(lambda: 1 / 0, default="fallback") == "fallback"

    def test_safe_call_logs_when_logger_given(self, caplog):
        log = logging.getLogger("test.safe_call")
        with caplog.at_level(logging.WARNING, logger="test.safe_call"):
            safe_call(lambda: 1 / 0, default=None, log=log, message="boom")
        assert any("boom" in r.getMessage() for r in caplog.records)

    def test_safe_call_no_logger_does_not_raise(self):
        assert safe_call(lambda: {}["x"], default=7) == 7

    def test_swallow_decorator(self):
        @swallow(default=-1)
        def div(a, b):
            return a // b

        assert div(10, 2) == 5
        assert div(10, 0) == -1

    def test_wrap_unexpected_translates_bare_exception(self):
        with pytest.raises(ServiceError) as ei:
            wrap_unexpected(lambda: {}["missing"])
        assert ei.value.code == ServiceErrorCode.INTERNAL_ERROR
        assert ei.value.__cause__ is not None

    def test_wrap_unexpected_passes_service_error_through(self):
        def raise_se():
            raise ServiceError.not_found("X")

        with pytest.raises(ServiceError) as ei:
            wrap_unexpected(raise_se)
        assert ei.value.code == ServiceErrorCode.NOT_FOUND

    def test_wrap_unexpected_custom_code(self):
        with pytest.raises(ServiceError) as ei:
            wrap_unexpected(lambda: 1 / 0, code=ServiceErrorCode.DATABASE_ERROR)
        assert ei.value.code == ServiceErrorCode.DATABASE_ERROR


# ===========================================================================
# request_id middleware + error handler integration
# ===========================================================================
@pytest.fixture()
def rid_app():
    app = FastAPI()
    install_request_id_middleware(app)
    install_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise ServiceError(ServiceErrorCode.INTERNAL_ERROR, "kaboom")

    @app.get("/se/{code}")
    async def se(code: str):
        raise ServiceError(ServiceErrorCode(code), details={"why": code})

    return app


class TestRequestIdMiddleware:
    def test_mints_request_id_when_absent(self, rid_app):
        client = TestClient(rid_app, raise_server_exceptions=False)
        r = client.get("/boom")
        assert r.status_code == 500
        rid = r.headers.get("X-Request-ID")
        assert rid and rid.startswith("req_")
        assert r.json()["error"]["request_id"] == rid

    def test_honours_inbound_request_id_header(self, rid_app):
        client = TestClient(rid_app, raise_server_exceptions=False)
        r = client.get("/boom", headers={"X-Request-ID": "caller-123"})
        assert r.headers["X-Request-ID"] == "caller-123"
        assert r.json()["error"]["request_id"] == "caller-123"

    def test_envelope_carries_retryable(self, rid_app):
        client = TestClient(rid_app, raise_server_exceptions=False)
        r = client.get("/se/TIMEOUT")
        body = r.json()["error"]
        assert body["retryable"] is True
        assert body["request_id"]

    def test_install_is_idempotent(self):
        app = FastAPI()
        install_request_id_middleware(app)
        n_before = len(app.user_middleware)
        install_request_id_middleware(app)
        assert len(app.user_middleware) == n_before


# ===========================================================================
# _error_body / _resolve_request_id helpers
# ===========================================================================
class TestErrorBodyHelpers:
    def test_error_body_minimal(self):
        b = _error_body("CODE", "msg")["error"]
        assert b["code"] == "CODE"
        assert b["message"] == "msg"

    def test_error_body_full(self):
        b = _error_body("CODE", "msg", details={"k": 1}, retry_after=5,
                        path="/x", request_id="r1", retryable=True)["error"]
        assert b["details"] == {"k": 1}
        assert b["retry_after"] == 5
        assert b["path"] == "/x"
        assert b["request_id"] == "r1"
        assert b["retryable"] is True

    def test_resolve_request_id_from_header(self):
        app = FastAPI()
        captured = {}

        @app.get("/")
        async def root(request: Request):
            captured["rid"] = _resolve_request_id(request)
            return {"ok": True}

        client = TestClient(app)
        client.get("/", headers={"X-Request-ID": "hdr-1"})
        assert captured["rid"] == "hdr-1"

    def test_resolve_request_id_empty_when_absent(self):
        app = FastAPI()

        @app.get("/")
        async def root(request: Request):
            return {"rid": _resolve_request_id(request)}

        client = TestClient(app)
        assert client.get("/").json()["rid"] == ""
