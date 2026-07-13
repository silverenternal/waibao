"""T2901 — unit tests for ``services.auth.sso`` + ``services.auth.session``
+ ``services.auth.jit`` + ``api.auth_sso``.

Coverage:
  * 6 provider registry (SAML + OIDC)
  * SAML AuthnRequest construction + SAMLResponse parsing (mocked)
  * OIDC id_token claim parsing + verification
  * JIT provisioner (create / link-by-email / re-link)
  * Session manager (create / refresh rotation / revoke)
  * FastAPI routes (login / callback / refresh / me / logout)
  * Cookie wiring
  * Edge cases (state mismatch, bad signature, missing email, blacklist)

Total: 30+ tests.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time

# Add backend to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# SAML helpers
# ---------------------------------------------------------------------------

def _b64(s: bytes) -> str:
    return base64.b64encode(s).decode("ascii")


def _fake_saml_response(
    *,
    name_id: str = "user@example.com",
    email: str = "user@example.com",
    first_name: str = "Sarah",
    last_name: str = "Chen",
    groups: list[str] | None = None,
    issuer: str = "https://idp.example.com/saml/metadata",
) -> str:
    """Return a base64-encoded SAML 2.0 Response XML for tests."""
    groups_xml = "".join(
        f"<saml:AttributeValue>{g}</saml:AttributeValue>" for g in (groups or [])
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="_{int(time.time())}" Version="2.0" IssueInstant="2026-07-01T00:00:00Z"
                Destination="https://app.recruittech.com/api/auth/sso/okta/callback">
  <saml:Issuer>{issuer}</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="assertion-1" Version="2.0" IssueInstant="2026-07-01T00:00:00Z">
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"/>
    </saml:Subject>
    <saml:AttributeStatement>
      <saml:Attribute Name="Email">
        <saml:AttributeValue>{email}</saml:AttributeValue>
      </saml:Attribute>
      <saml:Attribute Name="FirstName">
        <saml:AttributeValue>{first_name}</saml:AttributeValue>
      </saml:Attribute>
      <saml:Attribute Name="LastName">
        <saml:AttributeValue>{last_name}</saml:AttributeValue>
      </saml:Attribute>
      <saml:Attribute Name="groups">
        {groups_xml}
      </saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>"""
    return _b64(xml.encode("utf-8"))


def _fake_id_token(
    *,
    sub: str = "user-123",
    email: str = "user@example.com",
    name: str = "Sarah Chen",
    given_name: str = "Sarah",
    family_name: str = "Chen",
    iss: str = "https://accounts.google.com",
    aud: str = "google-client",
    nonce: str | None = None,
    email_verified: bool = True,
    groups: list[str] | None = None,
) -> str:
    """Build a *fake* (unsigned) JWT-shaped id_token. The HS256 signature
    is garbage — Authlib is optional and the SSO service degrades to a
    claim-only path when the JWK fetch is unavailable.
    """
    header = {"alg": "RS256", "typ": "JWT"}
    payload: dict = {
        "iss": iss,
        "sub": sub,
        "aud": aud,
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "given_name": given_name,
        "family_name": family_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    if nonce:
        payload["nonce"] = nonce
    if groups:
        payload["groups"] = groups

    def _b64u(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{_b64u(header)}.{_b64u(payload)}.fake-signature"


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def test_all_six_providers_registered(self):
        from services.auth.providers import PROVIDER_REGISTRY
        expected = {"okta", "azure_ad", "google", "dingtalk", "feishu", "wecom"}
        assert set(PROVIDER_REGISTRY.keys()) == expected

    def test_okta_is_saml(self):
        from services.auth.providers import get_provider_config, SSOProtocol
        assert get_provider_config("okta").protocol is SSOProtocol.SAML2

    def test_oidc_providers(self):
        from services.auth.providers import get_provider_config, SSOProtocol
        for slug in ("azure_ad", "google", "dingtalk", "feishu", "wecom"):
            assert get_provider_config(slug).protocol is SSOProtocol.OIDC, slug

    def test_unknown_provider_raises(self):
        from services.auth.providers import get_provider_config
        with pytest.raises(KeyError):
            get_provider_config("not-a-real-idp")

    def test_public_dict_has_no_secrets(self):
        from services.auth.providers import get_provider_config
        d = get_provider_config("okta").public_dict()
        for forbidden in ("client_secret", "clientSecret", "x509_cert"):
            assert forbidden not in d

    def test_email_whitelist_match(self):
        from services.auth.providers import get_provider_config
        # okta whitelist is opt-in via env; default is no whitelist
        cfg = get_provider_config("okta")
        assert cfg.validate_email_domain("anyone@anywhere.com") is True

    def test_email_blacklist(self, monkeypatch):
        from services.auth import providers
        # Build a fake config with a blacklist
        from dataclasses import replace
        from services.auth.providers import get_provider_config, ProviderCategory, SSOProtocol
        cfg = replace(
            get_provider_config("google"),
            email_domain_blacklist=["spam.com"],
        )
        assert cfg.validate_email_domain("good@gmail.com") is True
        assert cfg.validate_email_domain("bad@spam.com") is False

    def test_email_malformed(self):
        from services.auth.providers import get_provider_config
        cfg = get_provider_config("google")
        assert cfg.validate_email_domain("not-an-email") is False
        assert cfg.validate_email_domain("") is False

    def test_list_enabled_providers(self):
        from services.auth.providers import list_enabled_providers
        providers = list_enabled_providers()
        assert len(providers) == 6
        for p in providers:
            assert p.enabled is True


# ---------------------------------------------------------------------------
# SAML building & parsing
# ---------------------------------------------------------------------------

class TestSAMLHelpers:
    def test_build_saml_authn_request_returns_url(self):
        from services.auth.sso import build_saml_authn_request
        url, b64 = build_saml_authn_request(
            issuer="https://app.recruittech.com/saml/metadata",
            idp_sso_url="https://example.okta.com/sso/saml",
            acs_url="https://app.recruittech.com/api/auth/sso/okta/callback",
            state="abc123",
        )
        assert "SAMLRequest=" in url
        assert "RelayState=abc123" in url
        assert b64  # base64-deflated request

    def test_parse_saml_response_extracts_attrs(self):
        from services.auth.sso import parse_saml_response
        saml = _fake_saml_response(
            name_id="alice@example.com",
            email="alice@example.com",
            first_name="Alice",
            last_name="Wong",
            groups=["eng", "platform"],
        )
        attrs = parse_saml_response(saml)
        assert attrs["subject"] == "alice@example.com"
        assert attrs["email"] == "alice@example.com"
        assert attrs["given_name"] == "Alice"
        assert attrs["family_name"] == "Wong"
        assert "eng" in attrs["groups"]
        assert "platform" in attrs["groups"]

    def test_parse_saml_response_empty(self):
        from services.auth.sso import parse_saml_response, SSOLoginError
        with pytest.raises(SSOLoginError):
            parse_saml_response("")

    def test_parse_saml_response_garbage(self):
        from services.auth.sso import parse_saml_response, SSOLoginError
        with pytest.raises(SSOLoginError):
            parse_saml_response(_b64(b"not valid xml"))

    def test_parse_saml_response_no_assertion(self):
        from services.auth.sso import parse_saml_response, SSOLoginError
        bad = _b64(b"""<?xml version="1.0"?><samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"/>""")
        with pytest.raises(SSOLoginError):
            parse_saml_response(bad)


# ---------------------------------------------------------------------------
# OIDC helpers
# ---------------------------------------------------------------------------

class TestOIDCHelpers:
    def test_parse_id_token_claims(self):
        from services.auth.sso import parse_id_token_claims
        token = _fake_id_token(email="eve@x.com", sub="sub-1")
        claims = parse_id_token_claims(token)
        assert claims["email"] == "eve@x.com"
        assert claims["sub"] == "sub-1"
        assert claims["email_verified"] is True

    def test_parse_malformed_token(self):
        from services.auth.sso import parse_id_token_claims, SSOLoginError
        with pytest.raises(SSOLoginError):
            parse_id_token_claims("not-a-jwt")

    def test_verify_id_token_issuer_mismatch(self):
        from services.auth.sso import verify_oidc_id_token, SSOLoginError
        token = _fake_id_token(iss="https://wrong.example.com")
        with pytest.raises(SSOLoginError):
            verify_oidc_id_token(token, issuer="https://right.example.com", audience="client")

    def test_verify_id_token_nonce_mismatch(self):
        from services.auth.sso import verify_oidc_id_token, SSOLoginError
        token = _fake_id_token(nonce="nonce-a")
        with pytest.raises(SSOLoginError):
            verify_oidc_id_token(
                token, issuer="https://accounts.google.com", audience="aud", nonce="nonce-b"
            )

    def test_verify_id_token_audience_mismatch(self):
        from services.auth.sso import verify_oidc_id_token, SSOLoginError
        token = _fake_id_token(aud="wrong")
        with pytest.raises(SSOLoginError):
            verify_oidc_id_token(
                token, issuer="https://accounts.google.com", audience="right"
            )

    def test_verify_id_token_happy_path(self):
        from services.auth.sso import verify_oidc_id_token
        token = _fake_id_token(iss="https://accounts.google.com", aud="right")
        claims = verify_oidc_id_token(
            token, issuer="https://accounts.google.com", audience="right"
        )
        assert claims["email"]


# ---------------------------------------------------------------------------
# SSO service flow
# ---------------------------------------------------------------------------

class TestSSOService:
    def setup_method(self):
        from services.auth.sso import SSOService
        self.svc = SSOService(
            sp_acs_url="http://localhost:8000/api/auth/sso/{provider}/callback",
            sp_entity_id="https://app.recruittech.com/saml/metadata",
        )

    def test_begin_login_okta_redirect(self):
        r = self.svc.begin_login("okta")
        assert r.provider == "okta"
        assert "SAMLRequest" in r.url
        assert r.method == "GET"
        assert r.state

    def test_begin_login_google_oidc(self):
        r = self.svc.begin_login("google")
        assert r.provider == "google"
        assert "openid" in r.url
        assert "response_type=code" in r.url
        assert "scope=openid" in r.url or "scope=" in r.url

    def test_begin_login_dingtalk(self):
        r = self.svc.begin_login("dingtalk")
        assert "api.dingtalk.com" in r.url

    def test_begin_login_feishu(self):
        r = self.svc.begin_login("feishu")
        assert "open.feishu.cn" in r.url

    def test_begin_login_wecom(self):
        r = self.svc.begin_login("wecom")
        assert "login.work.weixin.qq.com" in r.url

    def test_begin_login_unknown_provider(self):
        from services.auth.sso import SSOLoginError
        with pytest.raises(SSOLoginError):
            self.svc.begin_login("not-real")

    def test_handle_saml_callback_happy(self):
        saml = _fake_saml_response(email="alice@okta.example.com")
        claims = self.svc.handle_callback("okta", saml_response=saml, state="s")
        assert claims.email == "alice@okta.example.com"
        assert claims.given_name == "Sarah"
        assert "eng" not in claims.groups  # groups empty
        assert claims.protocol.value == "saml2"

    def test_handle_oidc_callback_happy(self):
        token = _fake_id_token(email="bob@google.example.com", aud="google-client")
        claims = self.svc.handle_callback(
            "google", id_token=token, state="s", nonce=None
        )
        assert claims.email == "bob@google.example.com"
        assert claims.display_name == "Sarah Chen"
        assert claims.protocol.value == "oidc"

    def test_handle_callback_state_mismatch(self):
        from services.auth.sso import SSOLoginError
        with pytest.raises(SSOLoginError):
            self.svc.handle_callback(
                "google", id_token=_fake_id_token(), state="bad", expected_state="good"
            )

    def test_handle_callback_missing_code_and_id_token(self):
        from services.auth.sso import SSOLoginError
        with pytest.raises(SSOLoginError):
            self.svc.handle_callback("google")

    def test_handle_callback_missing_email(self):
        from services.auth.sso import SSOLoginError
        token = _fake_id_token(email="")
        with pytest.raises(SSOLoginError):
            self.svc.handle_callback("google", id_token=token)

    def test_list_providers_returns_six(self):
        out = self.svc.list_providers()
        assert len(out) == 6
        slugs = {p["slug"] for p in out}
        assert slugs == {"okta", "azure_ad", "google", "dingtalk", "feishu", "wecom"}


# ---------------------------------------------------------------------------
# JIT provisioner
# ---------------------------------------------------------------------------

class TestJITProvisioner:
    def setup_method(self):
        from services.auth.jit import InMemoryUserStore, JITProvisioner
        from services.auth.sso import SSOCallbackClaims, SSOProtocol
        self.store = InMemoryUserStore()
        self.prov = JITProvisioner(self.store, default_org_slug="acme", default_org_name="Acme")
        self._claims = lambda **kw: SSOCallbackClaims(
            provider=kw.get("provider", "okta"),
            subject=kw.get("subject", "saml-sub-1"),
            email=kw.get("email", "alice@acme.com"),
            email_verified=kw.get("email_verified", True),
            given_name="Alice",
            family_name="Wong",
            display_name="Alice Wong",
            picture=None,
            groups=kw.get("groups", []),
            protocol=SSOProtocol.SAML2,
        )

    def test_create_new_user(self):
        result = self.prov.provision(self._claims())
        assert result.created is True
        assert result.user["email"] == "alice@acme.com"
        assert result.organisation["slug"] == "acme"
        assert self.store.stats()["users"] == 1
        assert self.store.stats()["organisations"] == 1
        assert self.store.stats()["memberships"] == 1

    def test_idempotent_re_login(self):
        c = self._claims()
        first = self.prov.provision(c)
        # Second login with the same (provider, subject) should hit the
        # SSO identity lookup directly — it should not be flagged as an
        # email-link because the user was found by SSO identity, not email.
        result2 = self.prov.provision(c)
        assert result2.created is False
        assert result2.linked_by_email is False
        assert self.store.stats()["users"] == 1
        # Identity is the same row
        assert result2.user["id"] == first.user["id"]

    def test_link_by_email_existing_account(self):
        # Seed an existing user with the same email (different provider)
        existing = self.store.insert_user({
            "email": "alice@acme.com",
            "display_name": "Alice (legacy)",
            "role": "client",
            "is_active": True,
        })
        result = self.prov.provision(self._claims(provider="google"))
        assert result.user["id"] == existing["id"]
        assert result.linked_by_email is True
        # Profile fields should be refreshed
        assert result.user["given_name"] == "Alice"

    def test_disable_link_by_email(self):
        from services.auth.jit import JITProvisioner
        prov = JITProvisioner(self.store, link_by_email=False)
        self.store.insert_user({"email": "alice@acme.com", "display_name": "x", "role": "client", "is_active": True})
        result = prov.provision(self._claims())
        assert result.created is True  # new user, not linked

    def test_groups_propagated(self):
        c = self._claims(groups=["eng", "platform"])
        result = self.prov.provision(c)
        assert set(result.groups) == {"eng", "platform"}

    def test_default_org_reused(self):
        self.prov.provision(self._claims())
        result2 = self.prov.provision(self._claims(subject="another-sub"))
        assert result2.organisation["id"] == self.prov.provision(self._claims()).organisation["id"]


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def setup_method(self):
        from services.auth.session import SessionManager
        self.mgr = SessionManager()

    def test_create_session(self):
        s = self.mgr.create(user_id="u1", email="u1@x.com", provider="okta")
        assert s.access_token
        assert s.refresh_token
        assert s.access_token_expires_at > time.time()
        assert s.refresh_token_expires_at > s.access_token_expires_at

    def test_refresh_rotates_tokens(self):
        from services.auth.session import SessionStore
        s = self.mgr.create(user_id="u1", email="u1@x.com", provider="google")
        old_refresh = s.refresh_token
        old_access = s.access_token
        new = self.mgr.refresh(old_refresh)
        assert new is not None
        assert new.refresh_token != old_refresh
        assert new.access_token != old_access
        # Old refresh token should no longer work
        assert self.mgr.refresh(old_refresh) is None

    def test_revoke_session(self):
        s = self.mgr.create(user_id="u1", email="u1@x.com", provider="okta")
        self.mgr.revoke(s.refresh_token)
        assert self.mgr.refresh(s.refresh_token) is None

    def test_verify_access_token_round_trip(self):
        from services.auth.session import JWT_SECRET, JWT_ALG, JWT_ISSUER
        s = self.mgr.create(user_id="u1", email="u1@x.com", provider="okta")
        claims = self.mgr.verify_access_token(s.access_token)
        assert claims is not None
        assert claims["sub"] == "u1"
        assert claims["email"] == "u1@x.com"
        assert claims["provider"] == "okta"
        assert claims["iss"] == JWT_ISSUER

    def test_verify_access_token_garbage(self):
        assert self.mgr.verify_access_token("not-a-jwt") is None

    def test_refresh_with_unknown_token(self):
        assert self.mgr.refresh("garbage") is None


# ---------------------------------------------------------------------------
# API endpoints (FastAPI TestClient)
# ---------------------------------------------------------------------------

class TestSSOAPI:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from api.auth_sso import router
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)
        # Cookies on TestClient are HttpOnly by default but TestClient's
        # under-the-hood httpx client still forwards them. The deprecated
        # `cookies=...` kwarg on `.get()` is the issue — instead we
        # pre-populate the client cookies.
        c.cookies = c.cookies  # ensure attribute exists
        return c

    def test_providers_endpoint(self, client):
        r = client.get("/api/auth/sso/providers")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 6
        slugs = {p["slug"] for p in body["providers"]}
        assert "okta" in slugs and "google" in slugs and "wecom" in slugs

    def test_login_endpoint_okta(self, client):
        r = client.get("/api/auth/sso/okta/login")
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "okta"
        assert "SAMLRequest" in body["url"]
        assert body["state"]

    def test_login_endpoint_google(self, client):
        r = client.get("/api/auth/sso/google/login")
        assert r.status_code == 200
        body = r.json()
        assert "openid" in body["url"]
        assert "response_type=code" in body["url"]

    def test_login_unknown_provider(self, client):
        r = client.get("/api/auth/sso/not-a-real-idp/login")
        assert r.status_code == 404

    def test_callback_saml_sets_cookies(self, client):
        saml = _fake_saml_response(email="alice@okta.com")
        r = client.post(
            "/api/auth/sso/okta/callback",
            json={"SAMLResponse": saml, "state": "abc"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["provider"] == "okta"
        assert body["user"]["email"] == "alice@okta.com"
        assert "at" in r.cookies
        assert "rt" in r.cookies

    def test_callback_oidc_happy(self, client):
        token = _fake_id_token(email="bob@google.com", aud="google-client")
        r = client.post(
            "/api/auth/sso/google/callback",
            json={"id_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["email"] == "bob@google.com"
        assert body["provider"] == "google"

    def test_refresh_endpoint(self, client):
        # First, do a callback to obtain a session
        saml = _fake_saml_response(email="alice@okta.com")
        r = client.post(
            "/api/auth/sso/okta/callback",
            json={"SAMLResponse": saml, "state": "x"},
        )
        assert r.status_code == 200
        # Sync cookies from the callback response onto the client so the
        # next request sends them.
        client.cookies.update(r.cookies)
        assert client.cookies.get("rt")

        # Refresh using the cookie
        r2 = client.post("/api/auth/sso/refresh")
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "access_token" in body and "refresh_token" in body

    def test_refresh_missing_token_returns_401(self, client):
        # Clear any cookies on the client to test the unauthenticated path
        client.cookies.clear()
        r = client.post("/api/auth/sso/refresh")
        assert r.status_code == 401

    def test_logout_clears_cookies(self, client):
        saml = _fake_saml_response(email="alice@okta.com")
        r = client.post(
            "/api/auth/sso/okta/callback",
            json={"SAMLResponse": saml, "state": "x"},
        )
        client.cookies.update(r.cookies)
        r2 = client.post("/api/auth/sso/logout")
        assert r2.status_code == 200

    def test_me_with_cookie(self, client):
        saml = _fake_saml_response(email="alice@okta.com")
        r = client.post(
            "/api/auth/sso/okta/callback",
            json={"SAMLResponse": saml, "state": "x"},
        )
        client.cookies.update(r.cookies)
        r2 = client.get("/api/auth/sso/me")
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["email"] == "alice@okta.com"
        assert body["provider"] == "okta"

    def test_me_without_cookie_returns_401(self, client):
        client.cookies.clear()
        r = client.get("/api/auth/sso/me")
        assert r.status_code == 401

    def test_redirect_route(self, client):
        r = client.get("/api/auth/sso/google/redirect", follow_redirects=False)
        assert r.status_code == 302
        assert "accounts.google.com" in r.headers["location"]


# ---------------------------------------------------------------------------
# End-to-end smoke: SAML → JIT → session → refresh
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_full_flow(self):
        from fastapi import FastAPI
        from api.auth_sso import router

        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)

        # Use a unique email + subject so the JIT provisioner (which is
        # a module-level singleton) starts from a clean slate for this
        # end-to-end test.
        unique_id = int(time.time())
        unique_email = f"e2e-{unique_id}@enterprise.com"
        unique_subject = f"nameid-{unique_id}"
        # 1) Login with Okta (SAML)
        saml = _fake_saml_response(
            name_id=unique_subject,
            email=unique_email, first_name="Alice", last_name="Wong",
            groups=["platform"]
        )
        r = c.post("/api/auth/sso/okta/callback", json={"SAMLResponse": saml, "state": "x"})
        assert r.status_code == 200
        first = r.json()
        assert first["created"] is True
        assert first["user"]["email"] == unique_email
        assert first["provider"] == "okta"

        c.cookies.update(r.cookies)
        assert c.cookies.get("at") and c.cookies.get("rt")

        # 2) /me reflects the session
        r2 = c.get("/api/auth/sso/me")
        assert r2.status_code == 200
        assert r2.json()["email"] == unique_email

        # 3) Refresh rotates tokens
        r3 = c.post("/api/auth/sso/refresh")
        assert r3.status_code == 200
        new = r3.json()
        assert new["refresh_token"] != first["refresh_token"]

        # 4) Logout
        r4 = c.post("/api/auth/sso/logout")
        assert r4.status_code == 200
