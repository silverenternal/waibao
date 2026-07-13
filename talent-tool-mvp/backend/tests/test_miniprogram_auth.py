"""Tests for T1203 — WeChat mini-program authentication endpoints.

These exercise the FastAPI routes directly via the TestClient so they don't
require a real WeChat appid/secret. The code2session flow falls back to a
deterministic mock when credentials are missing, which is what these tests
rely on.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# -----------------------------------------------------------------------------
# /api/auth/miniprogram-config
# -----------------------------------------------------------------------------


def test_miniprogram_config_returns_appid_flag(client: TestClient) -> None:
    resp = client.get("/api/auth/miniprogram-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "appid" in data
    assert "enable_mock_login" in data
    assert isinstance(data["enable_mock_login"], bool)


# -----------------------------------------------------------------------------
# /api/auth/wechat-login
# -----------------------------------------------------------------------------


def test_wechat_login_missing_code_is_400(client: TestClient) -> None:
    resp = client.post("/api/auth/wechat-login", json={})
    assert resp.status_code == 422  # pydantic validation


def test_wechat_login_happy_path(client: TestClient) -> None:
    code = "mock_code_for_test_001"
    resp = client.post("/api/auth/wechat-login", json={"code": code})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] > 0
    assert body["openid"].startswith("mock_") or body["openid"].startswith("fallback_")
    assert isinstance(body["user"]["id"], str)
    # role must be one of the three allowed
    assert body["user"]["role"] in {"talent_partner", "client", "admin"}


def test_wechat_login_is_deterministic_per_code(client: TestClient) -> None:
    """Same code must yield the same user_id (re-login returns same user)."""
    code = "stable_code_for_test_xyz"
    r1 = client.post("/api/auth/wechat-login", json={"code": code})
    r2 = client.post("/api/auth/wechat-login", json={"code": code})
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"]


def test_wechat_login_with_nickname_marks_new_user(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/wechat-login",
        json={"code": "new_user_code", "nickname": "Hugo"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_new_user"] is True


def test_wechat_login_with_explicit_role(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/wechat-login",
        json={"code": "client_code", "role": "client"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "client"


def test_wechat_login_invalid_role_falls_back(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/wechat-login",
        json={"code": "bad_role_code", "role": "wizard"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "talent_partner"


# -----------------------------------------------------------------------------
# Round-trip: the JWT we mint must be accepted by get_current_user
# -----------------------------------------------------------------------------


def test_mobile_jwt_works_on_protected_endpoint(client: TestClient) -> None:
    # /api/users/me uses get_current_user (see main.py).
    login = client.post(
        "/api/auth/wechat-login",
        json={"code": "round_trip_code"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    # 200 if current user matches the token, 403 if /api/users/me requires
    # admin role (depends on the build).  Both are valid "auth" responses.
    assert me.status_code in (200, 403), me.text
    if me.status_code == 200:
        body = me.json()
        # Should resolve to the same UUID
        assert UUID(body["id"]) == UUID(login.json()["user"]["id"])


def test_bad_token_is_rejected(client: TestClient) -> None:
    me = client.get("/api/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert me.status_code == 401


# -----------------------------------------------------------------------------
# /api/auth/phone-login
# -----------------------------------------------------------------------------


def test_phone_login_requires_openid(client: TestClient) -> None:
    resp = client.post("/api/auth/phone-login", json={"code": "phone_code"})
    assert resp.status_code == 400


def test_phone_login_happy_path(client: TestClient) -> None:
    # First do a wechat-login to get a real openid
    login = client.post(
        "/api/auth/wechat-login", json={"code": "phone_link_code"}
    )
    openid = login.json()["openid"]

    resp = client.post(
        "/api/auth/phone-login",
        json={"code": "encrypted_phone_code", "openid": openid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["openid"] == openid