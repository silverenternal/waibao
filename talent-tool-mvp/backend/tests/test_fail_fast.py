"""T5014 — Security fail-fast tests.

Covers:
  * JWT secret: missing / short / known-weak all raise; valid resolves.
  * SessionManager refuses to construct without a valid secret.
  * cryptography must be importable (no HMAC pseudo-encryption fallback).
  * PIIEncryptor fails fast on a bad key (no silent downgrade).
  * SAML parse_saml_response runs the signature-verification path and
    fail-fasts when python3-saml is required but missing.
  * SAML response still parses (attributes) when verification is off.
  * security_startup gate raises in strict mode, logs in non-strict.
"""
from __future__ import annotations

import base64
import os

import pytest


# ---------------------------------------------------------------------------
# JWT secret fail-fast
# ---------------------------------------------------------------------------
def _clear_jwt_env(monkeypatch):
    for k in ("SSO_JWT_SECRET", "SUPABASE_JWT_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_jwt_secret_missing_raises(monkeypatch):
    _clear_jwt_env(monkeypatch)
    import services.auth.session as sess

    with pytest.raises(sess.JWTSecretError):
        sess.resolve_jwt_secret()


def test_jwt_secret_too_short_raises(monkeypatch):
    _clear_jwt_env(monkeypatch)
    monkeypatch.setenv("SSO_JWT_SECRET", "short")
    import services.auth.session as sess

    with pytest.raises(sess.JWTSecretError):
        sess.resolve_jwt_secret()


@pytest.mark.parametrize("weak", [
    "super-secret-jwt-token-with-at-least-32-characters-long",
    "your-super-secret-jwt-token-with-at-least-32-characters-long",
    "secret",
    "changeme",
    "test-secret",
])
def test_jwt_secret_known_weak_raises(monkeypatch, weak):
    _clear_jwt_env(monkeypatch)
    monkeypatch.setenv("SSO_JWT_SECRET", weak)
    import services.auth.session as sess

    with pytest.raises(sess.JWTSecretError):
        sess.resolve_jwt_secret()


def test_jwt_secret_valid_resolves(monkeypatch):
    _clear_jwt_env(monkeypatch)
    good = "a-valid-random-secret-0123456789-abcdef-notweak"
    monkeypatch.setenv("SSO_JWT_SECRET", good)
    import services.auth.session as sess

    assert sess.resolve_jwt_secret() == good
    assert len(good) >= sess.MIN_JWT_SECRET_LEN


def test_jwt_secret_falls_back_to_supabase_var(monkeypatch):
    _clear_jwt_env(monkeypatch)
    good = "supabase-fallback-secret-0123456789-abcdef-notweak"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", good)
    import services.auth.session as sess

    assert sess.resolve_jwt_secret() == good


def test_jwt_secret_sso_takes_precedence_over_supabase(monkeypatch):
    _clear_jwt_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "supabase-fallback-secret-0123456789-abcdef-notweak")
    monkeypatch.setenv("SSO_JWT_SECRET", "sso-priority-secret-0123456789-abcdef-notweak")
    import services.auth.session as sess

    assert sess.resolve_jwt_secret().startswith("sso-priority")


def test_session_manager_rejects_missing_secret(monkeypatch):
    _clear_jwt_env(monkeypatch)
    import services.auth.session as sess

    sess.JWT_SECRET = ""
    with pytest.raises(sess.JWTSecretError):
        sess.SessionManager()


def test_session_manager_constructs_with_valid_secret(monkeypatch):
    _clear_jwt_env(monkeypatch)
    monkeypatch.setenv("SSO_JWT_SECRET", "manager-ok-secret-0123456789-abcdef-notweak")
    import services.auth.session as sess

    mgr = sess.SessionManager()
    s = mgr.create(user_id="u1", email="a@b.com", provider="okta")
    assert s.access_token
    claims = mgr.verify_access_token(s.access_token)
    assert claims is not None and claims["sub"] == "u1"


# ---------------------------------------------------------------------------
# cryptography fail-fast
# ---------------------------------------------------------------------------
def test_assert_cryptography_available_passes():
    from compliance.encryption import assert_cryptography_available

    # cryptography is installed in the test env.
    assert_cryptography_available()  # should not raise


def test_pii_encryptor_rejects_bad_key():
    from compliance.encryption import CryptographyUnavailableError, PIIEncryptor

    with pytest.raises(CryptographyUnavailableError):
        PIIEncryptor(key=b"not-a-valid-fernet-key")


def test_pii_encryptor_no_silent_fallback_flag():
    # The HMAC fallback pseudo-encryption must not be reachable.
    import compliance.encryption as enc

    # When cryptography is present the backend is 'fernet', never 'fallback'.
    enc._detect_backend(require=True)
    assert enc._FERNET_BACKEND == "fernet"


def test_pii_encryptor_roundtrip():
    from compliance.encryption import PIIEncryptor
    from cryptography.fernet import Fernet

    e = PIIEncryptor(key=Fernet.generate_key())
    tok = e.encrypt("secret-pii")
    assert tok != "secret-pii"
    assert e.decrypt(tok) == "secret-pii"


# ---------------------------------------------------------------------------
# SAML fail-fast
# ---------------------------------------------------------------------------
_MINIMAL_SAML = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" ID="_resp">
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_assert">
    <saml:Subject><saml:NameID>user123</saml:NameID></saml:Subject>
    <saml:AttributeStatement>
      <saml:Attribute Name="email"><saml:AttributeValue>a@b.com</saml:AttributeValue></saml:Attribute>
      <saml:Attribute Name="given_name"><saml:AttributeValue>Alice</saml:AttributeValue></saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>"""


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def test_parse_saml_response_extracts_attrs_when_verification_off():
    from services.auth.sso import parse_saml_response

    attrs = parse_saml_response(_b64(_MINIMAL_SAML), verify_signature=False)
    assert attrs["email"] == "a@b.com"
    assert attrs["given_name"] == "Alice"
    assert attrs["subject"] == "user123"
    assert attrs["signature_verified"] is False


def test_parse_saml_response_requires_python3_saml_when_missing(monkeypatch):
    # Force verification on + require the lib; in this env python3-saml is
    # absent, so it must raise.
    import services.auth.sso as sso

    monkeypatch.delenv("SAML_REQUIRE_SIGNED_RESPONSE", raising=False)
    monkeypatch.setattr(sso, "_python3_saml_available", lambda: False)
    if sso._python3_saml_available():
        pytest.skip("python3-saml is installed in this env; skip negative path")
    with pytest.raises(sso.SSOLoginError):
        parse_saml_response_b64 = sso.parse_saml_response
        parse_saml_response_b64(
            _b64(_MINIMAL_SAML),
            verify_signature=True,
            require_python3_saml=True,
        )


def test_parse_saml_response_verification_skipped_when_lib_missing_and_not_required(monkeypatch):
    import services.auth.sso as sso

    monkeypatch.setattr(sso, "_python3_saml_available", lambda: False)
    attrs = sso.parse_saml_response(
        _b64(_MINIMAL_SAML), verify_signature=True, require_python3_saml=False
    )
    assert attrs["signature_verified"] is False  # could not verify, did not raise


# ---------------------------------------------------------------------------
# Security startup gate
# ---------------------------------------------------------------------------
def test_security_startup_raises_in_strict_mode(monkeypatch):
    monkeypatch.setenv("SECURITY_STARTUP_STRICT", "1")
    _clear_jwt_env(monkeypatch)
    import compliance.security_startup as gate
    import services.auth.session as sess

    sess.JWT_SECRET = ""
    with pytest.raises(gate.SecurityStartupError):
        gate.run_security_startup_checks()


def test_security_startup_logs_in_non_strict_mode(monkeypatch):
    monkeypatch.setenv("SECURITY_STARTUP_STRICT", "0")
    _clear_jwt_env(monkeypatch)
    import compliance.security_startup as gate
    import services.auth.session as sess

    sess.JWT_SECRET = ""
    summary = gate.run_security_startup_checks()
    assert summary["strict"] is False
    assert summary["checks"]["check_jwt_secret"]["ok"] is False


def test_security_startup_passes_with_valid_config(monkeypatch):
    monkeypatch.setenv("SECURITY_STARTUP_STRICT", "1")
    monkeypatch.setenv("SSO_JWT_SECRET", "startup-ok-secret-0123456789-abcdef-notweak")
    monkeypatch.delenv("SAML_REQUIRE_SIGNED_RESPONSE", raising=False)
    import compliance.security_startup as gate

    summary = gate.run_security_startup_checks()
    assert all(c["ok"] for c in summary["checks"].values())


def test_saml_lib_check_passes_when_not_required(monkeypatch):
    monkeypatch.delenv("SAML_REQUIRE_SIGNED_RESPONSE", raising=False)
    import compliance.security_startup as gate

    assert gate.check_saml_lib() is True
