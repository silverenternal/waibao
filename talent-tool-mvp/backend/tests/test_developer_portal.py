"""Tests for the T2902 Developer Portal.

Covers:
* App registration / list / revocation
* API Key v3 mint / list / revoke (App-scoped)
* OAuth 2.0 Authorization Code flow with PKCE
* OAuth refresh token grant + rotation
* OAuth RFC 7009 revocation
* Webhook subscriptions (create / list / rotate / delete / sign)
* Service-level helpers (PKCE, HMAC, code generation, versioning interplay)
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

import pytest

from services.platform import developer_portal as dp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_service(monkeypatch):
    """Force the singleton-backed service to use an in-memory store."""
    fresh = dp.DeveloperPortalService()
    monkeypatch.setattr(dp, "_service", fresh)
    monkeypatch.setattr(dp, "get_service", lambda: fresh)
    yield
    dp.reset_singleton()


@pytest.fixture
def svc(_isolated_service) -> dp.DeveloperPortalService:
    return dp.get_service()


@pytest.fixture
def registered_app(svc):
    created = svc.create_app(
        name="Acme HR",
        organisation_id="org_acme",
        homepage_url="https://acme.example.com",
        redirect_uris=["https://acme.example.com/callback"],
        scopes=["candidates:read", "matches:write"],
        created_by="user_42",
        environment="sandbox",
        description="Acme's ATS",
    )
    return created


# ---------------------------------------------------------------------------
# PKCE helpers + secrets
# ---------------------------------------------------------------------------


def test_generate_client_id_format():
    cid = dp.generate_client_id()
    assert cid.startswith("wb_app_")
    assert len(cid) == len("wb_app_") + 16


def test_generate_client_secret_format():
    cs = dp.generate_client_secret()
    assert cs.startswith("wb_cs_")
    assert len(cs) > 32


def test_pkce_plain_verification():
    verifier = "verifier-123"
    challenge = verifier
    assert dp.verify_pkce(verifier, challenge, "plain") is True
    assert dp.verify_pkce("different", challenge, "plain") is False


def test_pkce_s256_verification():
    import base64

    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert dp.verify_pkce(verifier, challenge, "s256") is True
    assert dp.verify_pkce(secrets.token_urlsafe(8), challenge, "s256") is False


def test_pkce_empty_inputs_rejected():
    assert dp.verify_pkce("", "challenge", "plain") is False
    assert dp.verify_pkce("verifier", "", "plain") is False


def test_pkce_unsupported_method_rejected():
    assert dp.verify_pkce("v", "v", "MD5") is False


def test_webhook_signature_hmac():
    payload = b'{"event":"candidate.created"}'
    secret = "wb_wh_test_secret"
    sig = dp.compute_webhook_signature(payload, secret)
    # Manual HMAC verification
    expected = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    assert sig == expected


def test_webhook_signature_unique_per_secret():
    payload = b"hi"
    a = dp.compute_webhook_signature(payload, "alpha")
    b = dp.compute_webhook_signature(payload, "beta")
    assert a != b


# ---------------------------------------------------------------------------
# App CRUD
# ---------------------------------------------------------------------------


def test_create_app_returns_client_secret_once(svc):
    created = svc.create_app(
        name="App",
        organisation_id="org_1",
        homepage_url="https://example.com",
        redirect_uris=["https://example.com/cb"],
        scopes=["candidates:read"],
        created_by="u_1",
    )
    assert created.app.client_id
    assert created.client_secret
    assert created.app.organisation_id == "org_1"
    assert "https://example.com/cb" in created.app.redirect_uris


def test_create_app_rejects_empty_redirect_uris(svc):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_app(
            name="App",
            organisation_id="o",
            homepage_url="",
            redirect_uris=[],
            scopes=[],
            created_by="u",
        )


def test_create_app_rejects_invalid_environment(svc):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_app(
            name="x",
            organisation_id="o",
            homepage_url="",
            redirect_uris=["https://e.com/cb"],
            scopes=[],
            created_by="u",
            environment="production",
        )


def test_create_app_rejects_non_http_redirect(svc):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_app(
            name="x",
            organisation_id="o",
            homepage_url="",
            redirect_uris=["javascript:alert(1)"],
            scopes=[],
            created_by="u",
        )


def test_list_apps_filters_by_org(svc):
    svc.create_app(
        name="A",
        organisation_id="o1",
        homepage_url="",
        redirect_uris=["https://a/cb"],
        scopes=[],
        created_by="u",
    )
    svc.create_app(
        name="B",
        organisation_id="o2",
        homepage_url="",
        redirect_uris=["https://b/cb"],
        scopes=[],
        created_by="u",
    )
    assert len(svc.list_apps(organisation_id="o1")) == 1
    assert len(svc.list_apps(organisation_id="o2")) == 1
    assert len(svc.list_apps(organisation_id="missing")) == 0


def test_revoke_app_removes_it(svc, registered_app):
    assert svc.revoke_app(registered_app.app.id, organisation_id="org_acme") is True
    assert svc.get_app(registered_app.app.id, organisation_id="org_acme") is None


def test_revoke_app_unknown_returns_false(svc):
    assert svc.revoke_app("nope", organisation_id="o") is False


def test_revoke_app_other_org_is_none(svc, registered_app):
    assert svc.get_app(registered_app.app.id, organisation_id="other_org") is None
    assert svc.revoke_app(registered_app.app.id, organisation_id="other_org") is False


def test_revoke_app_cascades_tokens(svc, registered_app):
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="candidates:read",
        state="",
        user_id="u_1",
        organisation_id="org_acme",
    )
    tok = svc.exchange_code(
        code=code.code,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        redirect_uri=code.redirect_uri,
    )
    assert svc.verify_access_token(tok.access_token) is not None
    svc.revoke_app(registered_app.app.id, organisation_id="org_acme")
    assert svc.verify_access_token(tok.access_token) is None


# ---------------------------------------------------------------------------
# OAuth 2.0 — Authorization Code Grant
# ---------------------------------------------------------------------------


def test_authorize_invalid_client_id_rejected(svc):
    with pytest.raises(dp.InvalidClientError):
        svc.authorize(
            client_id="wb_app_doesnotexist",
            response_type="code",
            redirect_uri="https://x/cb",
            scope="",
            state="",
            user_id="u",
            organisation_id="o",
        )


def test_authorize_unsupported_response_type_rejected(svc, registered_app):
    with pytest.raises(dp.UnauthorizedClientError):
        svc.authorize(
            client_id=registered_app.client_id,
            response_type="token",  # implicit flow — not supported
            redirect_uri="https://acme.example.com/callback",
            scope="",
            state="",
            user_id="u",
            organisation_id="org_acme",
        )


def test_authorize_unregistered_redirect_uri_rejected(svc, registered_app):
    with pytest.raises(dp.InvalidRequestError):
        svc.authorize(
            client_id=registered_app.client_id,
            response_type="code",
            redirect_uri="https://evil.example.com/cb",
            scope="",
            state="",
            user_id="u",
            organisation_id="org_acme",
        )


def test_authorize_scope_exceeds_app_rejected(svc, registered_app):
    with pytest.raises(dp.InvalidScopeError):
        svc.authorize(
            client_id=registered_app.client_id,
            response_type="code",
            redirect_uri="https://acme.example.com/callback",
            scope="admin:*",  # not in app.scopes
            state="",
            user_id="u",
            organisation_id="org_acme",
        )


def test_authorize_challenge_without_method_rejected(svc, registered_app):
    with pytest.raises(dp.InvalidRequestError):
        svc.authorize(
            client_id=registered_app.client_id,
            response_type="code",
            redirect_uri="https://acme.example.com/callback",
            scope="",
            state="",
            code_challenge="abc",
            code_challenge_method=None,
            user_id="u",
            organisation_id="org_acme",
        )


def test_authorize_unsupported_challenge_method_rejected(svc, registered_app):
    with pytest.raises(dp.InvalidRequestError):
        svc.authorize(
            client_id=registered_app.client_id,
            response_type="code",
            redirect_uri="https://acme.example.com/callback",
            scope="",
            state="",
            code_challenge="abc",
            code_challenge_method="MD5",
            user_id="u",
            organisation_id="org_acme",
        )


def test_full_oauth_code_flow_no_pkce(svc, registered_app):
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="candidates:read",
        state="abc123",
        user_id="u_99",
        organisation_id="org_acme",
    )
    assert code.code
    tok = svc.exchange_code(
        code=code.code,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        redirect_uri=code.redirect_uri,
    )
    assert tok.access_token.startswith("wb_at_")
    assert tok.refresh_token.startswith("wb_rt_")
    assert tok.scope == "candidates:read"
    assert tok.user_id == "u_99"

    # Code is consumed — reuse must fail
    with pytest.raises(dp.InvalidGrantError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            redirect_uri=code.redirect_uri,
        )


def test_exchange_code_invalid_secret_rejected(svc, registered_app):
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="",
        state="",
        user_id="u",
        organisation_id="org_acme",
    )
    with pytest.raises(dp.InvalidClientError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret="wrong",
            redirect_uri=code.redirect_uri,
        )


def test_exchange_code_redirect_uri_must_match(svc, registered_app):
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="",
        state="",
        user_id="u",
        organisation_id="org_acme",
    )
    with pytest.raises(dp.InvalidGrantError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            redirect_uri="https://acme.example.com/DIFFERENT",
        )


def test_full_oauth_code_flow_with_pkce(svc, registered_app):
    import base64

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="candidates:read",
        state="",
        code_challenge=challenge,
        code_challenge_method="S256",
        user_id="u",
        organisation_id="org_acme",
    )
    # Without verifier → must fail
    with pytest.raises(dp.InvalidGrantError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            redirect_uri=code.redirect_uri,
        )
    # With wrong verifier → must fail
    with pytest.raises(dp.InvalidGrantError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            redirect_uri=code.redirect_uri,
            code_verifier="wrong",
        )
    # Re-create a new code (the first one was popped) — use the original challenge/verifier
    code2 = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="candidates:read",
        state="",
        code_challenge=challenge,
        code_challenge_method="S256",
        user_id="u",
        organisation_id="org_acme",
    )
    tok = svc.exchange_code(
        code=code2.code,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        redirect_uri=code2.redirect_uri,
        code_verifier=verifier,
    )
    assert tok.access_token


def test_pkce_method_must_match(svc, registered_app):
    """If code is bound to S256, verification must use S256."""
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="",
        state="",
        code_challenge="somechallenge",
        code_challenge_method="S256",
        user_id="u",
        organisation_id="org_acme",
    )
    with pytest.raises(dp.InvalidGrantError):
        svc.exchange_code(
            code=code.code,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            redirect_uri=code.redirect_uri,
            code_verifier="somechallenge",  # plain text — but method is S256
        )


# ---------------------------------------------------------------------------
# Refresh grant + revocation
# ---------------------------------------------------------------------------


def _mint_token(svc, registered_app):
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="candidates:read",
        state="",
        user_id="u",
        organisation_id="org_acme",
    )
    return svc.exchange_code(
        code=code.code,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        redirect_uri=code.redirect_uri,
    )


def test_refresh_token_grant(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    rotated = svc.refresh(
        refresh_token=tok.refresh_token,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
    )
    assert rotated.access_token != tok.access_token
    assert rotated.refresh_token != tok.refresh_token


def test_refresh_with_wrong_client_secret_rejected(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    with pytest.raises(dp.InvalidClientError):
        svc.refresh(
            refresh_token=tok.refresh_token,
            client_id=registered_app.client_id,
            client_secret="nope",
        )


def test_refresh_rotates_old_tokens(svc, registered_app):
    """Old access + refresh tokens must be invalid after rotation."""
    tok = _mint_token(svc, registered_app)
    rotated = svc.refresh(
        refresh_token=tok.refresh_token,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
    )
    # Try to rotate the old refresh token again — must fail
    with pytest.raises(dp.InvalidGrantError):
        svc.refresh(
            refresh_token=tok.refresh_token,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
        )
    assert svc.verify_access_token(tok.access_token) is None
    assert svc.verify_access_token(rotated.access_token) is not None


def test_refresh_with_narrower_scope(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    rotated = svc.refresh(
        refresh_token=tok.refresh_token,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        scope="candidates:read",  # equal to original — OK
    )
    assert rotated.scope == "candidates:read"


def test_refresh_with_scope_exceeding_app_rejected(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    with pytest.raises(dp.InvalidScopeError):
        svc.refresh(
            refresh_token=tok.refresh_token,
            client_id=registered_app.client_id,
            client_secret=registered_app.client_secret,
            scope="admin:*",
        )


def test_revoke_access_token_invalidates(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    ok = svc.revoke_token(
        token=tok.access_token,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        token_type_hint="access_token",
    )
    assert ok is True
    assert svc.verify_access_token(tok.access_token) is None


def test_revoke_refresh_token_invalidates_pair(svc, registered_app):
    tok = _mint_token(svc, registered_app)
    svc.revoke_token(
        token=tok.refresh_token,
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
        token_type_hint="refresh_token",
    )
    assert svc.verify_access_token(tok.access_token) is None


def test_revoke_unknown_token_returns_false(svc, registered_app):
    ok = svc.revoke_token(
        token="wb_at_nope",
        client_id=registered_app.client_id,
        client_secret=registered_app.client_secret,
    )
    assert ok is False  # RFC 7009 §2.2 — 200 OK either way


# ---------------------------------------------------------------------------
# Webhook subscriptions
# ---------------------------------------------------------------------------


def test_create_webhook_rejects_unknown_app(svc):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_webhook(
            app_id="does-not-exist",
            url="https://e.com/wh",
            events=["candidate.created"],
            organisation_id="o",
        )


def test_create_webhook_rejects_non_http(svc, registered_app):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_webhook(
            app_id=registered_app.app.id,
            url="ftp://nope",
            events=["candidate.created"],
            organisation_id="org_acme",
        )


def test_create_webhook_rejects_unsupported_event(svc, registered_app):
    with pytest.raises(dp.InvalidRequestError):
        svc.create_webhook(
            app_id=registered_app.app.id,
            url="https://e.com/wh",
            events=["explosion.occurred"],
            organisation_id="org_acme",
        )


def test_create_webhook_returns_secret_once(svc, registered_app):
    sub, secret = svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://acme.example.com/wh",
        events=["candidate.created", "match.created"],
        organisation_id="org_acme",
    )
    assert secret.startswith("wb_wh_")
    assert sub.url == "https://acme.example.com/wh"
    assert "candidate.created" in sub.events


def test_list_webhooks(svc, registered_app):
    svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://a/wh",
        events=["candidate.created"],
        organisation_id="org_acme",
    )
    svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://b/wh",
        events=["match.created"],
        organisation_id="org_acme",
    )
    subs = svc.list_webhooks(app_id=registered_app.app.id, organisation_id="org_acme")
    assert len(subs) == 2


def test_delete_webhook(svc, registered_app):
    sub, _ = svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://a/wh",
        events=["candidate.created"],
        organisation_id="org_acme",
    )
    ok = svc.delete_webhook(
        webhook_id=sub.id,
        app_id=registered_app.app.id,
        organisation_id="org_acme",
    )
    assert ok is True
    assert svc.list_webhooks(
        app_id=registered_app.app.id, organisation_id="org_acme"
    ) == []


def test_rotate_webhook_secret(svc, registered_app):
    sub, old = svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://a/wh",
        events=["candidate.created"],
        organisation_id="org_acme",
    )
    rotated, new = svc.rotate_webhook_secret(
        webhook_id=sub.id,
        app_id=registered_app.app.id,
        organisation_id="org_acme",
    )
    assert rotated is not None
    assert new != old
    assert new.startswith("wb_wh_")


def test_webhook_signature_helper(svc, registered_app):
    sub, _ = svc.create_webhook(
        app_id=registered_app.app.id,
        url="https://a/wh",
        events=["candidate.created"],
        organisation_id="org_acme",
    )
    payload = b'{"event":"candidate.created","id":1}'
    sig1 = svc.sign_webhook_payload(webhook_id=sub.id, payload=payload)
    sig2 = svc.sign_webhook_payload(webhook_id=sub.id, payload=payload)
    assert sig1 == sig2
    assert isinstance(sig1, str) and len(sig1) == 64


def test_webhook_signature_unknown_id(svc):
    assert svc.sign_webhook_payload(webhook_id="missing", payload=b"x") is None


def test_supported_events_constant_is_frozenset():
    assert isinstance(dp.SUPPORTED_EVENTS, frozenset)
    assert "candidate.created" in dp.SUPPORTED_EVENTS


def test_cleanup_expired_drops_old_codes(svc, registered_app, monkeypatch):
    # Mint a code, then forcibly expire it by mutating the internal store.
    code = svc.authorize(
        client_id=registered_app.client_id,
        response_type="code",
        redirect_uri="https://acme.example.com/callback",
        scope="",
        state="",
        user_id="u",
        organisation_id="org_acme",
    )
    stored = svc._codes[code.code]
    stored.expires_at = 0  # past
    dropped = svc.cleanup_expired()
    assert dropped >= 1
    assert code.code not in svc._codes


# ---------------------------------------------------------------------------
# Default access-token TTL + expiry helpers
# ---------------------------------------------------------------------------


def test_default_token_ttls():
    assert dp.DEFAULT_ACCESS_TTL == 3600
    assert dp.DEFAULT_AUTHORIZE_TTL == 600
    assert dp.DEFAULT_REFRESH_TTL > dp.DEFAULT_ACCESS_TTL


# ---------------------------------------------------------------------------
# HTTP API surface (FastAPI TestClient)
# ---------------------------------------------------------------------------


def _override_current_user(user_id="u_test"):
    """Generate a quick helper to inject a fake CurrentUser."""
    from api.auth import CurrentUser
    import uuid
    from contracts.shared import UserRole

    return CurrentUser(id=uuid.uuid4(), email="test@example.com", role=UserRole.admin)


def test_api_register_app_endpoint(monkeypatch, _isolated_service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.auth import get_current_user

    app = FastAPI()
    from api.developer_portal import router as dp_router

    app.include_router(dp_router)

    fake_user = _override_current_user()

    async def fake_dep():
        return fake_user

    app.dependency_overrides[get_current_user] = fake_dep
    with TestClient(app) as c:
        r = c.post(
            "/api/developer/apps",
            json={
                "name": "My App",
                "homepage_url": "https://my.app",
                "redirect_uris": ["https://my.app/cb"],
                "scopes": ["candidates:read"],
                "environment": "sandbox",
                "description": "test",
            },
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["client_id"].startswith("wb_app_")
        assert data["client_secret"].startswith("wb_cs_")


def test_api_token_endpoint_grant_type_validation(monkeypatch, _isolated_service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    from api.developer_portal import router as dp_router

    app.include_router(dp_router)

    with TestClient(app) as c:
        r = c.post(
            "/api/developer/oauth/token",
            data={"grant_type": "magic_link", "client_id": "x", "client_secret": "y"},
        )
        # 400 unsupported_grant_type
        assert r.status_code == 400
        body = r.json()["detail"]
        assert body["error"] == "unsupported_grant_type"


def test_api_revoke_endpoint_unknown_token_returns_200(monkeypatch, _isolated_service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    from api.developer_portal import router as dp_router

    app.include_router(dp_router)
    with TestClient(app) as c:
        r = c.post(
            "/api/developer/oauth/revoke",
            data={"token": "wb_at_doesnotexist", "client_id": "wb_app_x", "client_secret": "wb_cs_y"},
        )
        # RFC 7009 — always 200, even if unknown
        assert r.status_code == 200
        assert r.json() == {"revoked": True}


def test_api_list_apps_requires_authentication(_isolated_service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    from api.developer_portal import router as dp_router

    app.include_router(dp_router)
    with TestClient(app) as c:
        # No auth override → 401
        r = c.get("/api/developer/apps")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Versioning interplay: developer portal is NOT under /api/v1 legacy redirect
# ---------------------------------------------------------------------------


def test_developer_portal_endpoints_are_not_redirected():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.versioning import install_versioning

    app = FastAPI()
    install_versioning(app)
    with TestClient(app, follow_redirects=False) as c:
        # The developer portal namespace should not be intercepted
        r = c.get("/api/developer/openapi.json")
        # 200 from the embedded stub OR 404 — but never 308
        assert r.status_code in (200, 404)
        assert r.headers.get("location") is None
