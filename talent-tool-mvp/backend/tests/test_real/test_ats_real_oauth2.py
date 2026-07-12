"""T1806 — OAuth2 TokenManager 测试 + build_real_provider 工厂测试."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest

from providers.ats.greenhouse import GreenhouseProvider
from providers.ats.lever import LeverProvider
from providers.ats.oauth2 import (
    HttpxOAuth2Client,
    InMemoryOAuth2TokenStore,
    OAuth2Error,
    OAuth2Token,
    OAuth2TokenManager,
)
from services.ats_sync import build_real_provider


# ---------------------------------------------------------------------------
# OAuth2 TokenManager
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_oauth2_manager_first_issue_via_client_credentials() -> None:
    store = InMemoryOAuth2TokenStore()

    class FakeClient:
        async def post(self, url: str, *, data: dict[str, str] | None = None, timeout: float = 30.0):
            assert data and data["grant_type"] == "client_credentials"
            return 200, {
                "access_token": "tok-A",
                "refresh_token": "ref-A",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": data.get("scope", ""),
            }

    mgr = OAuth2TokenManager(store, http_client=FakeClient())  # type: ignore[arg-type]
    tok = await mgr.get_or_refresh(
        tenant="acme", client_id="cid", client_secret="sec",
        token_url="https://auth.example.com/oauth/token",
        scope="candidates.read",
    )
    assert tok.access_token == "tok-A"
    assert tok.refresh_token == "ref-A"
    assert not tok.is_expired
    # 第二次取应返回缓存,不调用 http
    class CountingClient(FakeClient):
        calls = 0
        async def post(self, url, *, data=None, timeout=30.0):
            CountingClient.calls += 1
            return 200, {"access_token": "should-not-be-used", "expires_in": 3600}
    mgr2 = OAuth2TokenManager(store, http_client=CountingClient())  # type: ignore[arg-type]
    tok2 = await mgr2.get_or_refresh(
        tenant="acme", client_id="cid", client_secret="sec",
        token_url="https://auth.example.com/oauth/token",
    )
    assert tok2.access_token == "tok-A"
    assert CountingClient.calls == 0


@pytest.mark.asyncio
async def test_oauth2_manager_refresh_when_expired() -> None:
    store = InMemoryOAuth2TokenStore()
    # 预存一个已过期 token
    await store.put("acme", OAuth2Token(
        access_token="old-tok",
        refresh_token="ref-1",
        expires_at=time.time() - 100,
    ))

    class RefreshClient:
        async def post(self, url: str, *, data: dict[str, str] | None = None, timeout: float = 30.0):
            assert data["grant_type"] == "refresh_token"
            assert data["refresh_token"] == "ref-1"
            return 200, {
                "access_token": "new-tok",
                "refresh_token": "ref-2",
                "expires_in": 3600,
                "token_type": "Bearer",
            }

    mgr = OAuth2TokenManager(store, http_client=RefreshClient())  # type: ignore[arg-type]
    tok = await mgr.get_or_refresh(
        tenant="acme", client_id="cid", client_secret="sec",
        token_url="https://auth.example.com/oauth/token",
    )
    assert tok.access_token == "new-tok"
    assert tok.refresh_token == "ref-2"


@pytest.mark.asyncio
async def test_oauth2_manager_refresh_fails_falls_back_to_client_credentials() -> None:
    store = InMemoryOAuth2TokenStore()
    await store.put("acme", OAuth2Token(
        access_token="old-tok",
        refresh_token="ref-bad",
        expires_at=time.time() - 100,
    ))

    class MixedClient:
        async def post(self, url: str, *, data: dict[str, str] | None = None, timeout: float = 30.0):
            if data and data.get("grant_type") == "refresh_token":
                return 400, {"error": "invalid_grant"}
            return 200, {
                "access_token": "fresh-via-cc",
                "expires_in": 3600,
                "token_type": "Bearer",
            }

    mgr = OAuth2TokenManager(store, http_client=MixedClient())  # type: ignore[arg-type]
    tok = await mgr.get_or_refresh(
        tenant="acme", client_id="cid", client_secret="sec",
        token_url="https://auth.example.com/oauth/token",
    )
    assert tok.access_token == "fresh-via-cc"


@pytest.mark.asyncio
async def test_oauth2_token_about_to_expire_is_treated_as_expired() -> None:
    """提前 60 秒视为过期."""
    tok = OAuth2Token(access_token="x", refresh_token=None, expires_at=time.time() + 30)
    assert tok.is_expired is True
    tok2 = OAuth2Token(access_token="x", refresh_token=None, expires_at=time.time() + 600)
    assert tok2.is_expired is False


# ---------------------------------------------------------------------------
# build_real_provider 工厂
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_build_real_provider_greenhouse_basic() -> None:
    p = build_real_provider(provider_name="greenhouse", api_key="k")
    assert isinstance(p, GreenhouseProvider)
    assert p._api_key == "k"


@pytest.mark.asyncio
async def test_build_real_provider_lever_oauth2() -> None:
    p = build_real_provider(
        provider_name="lever",
        api_key="ignored",
        oauth2_manager=OAuth2TokenManager(),
        oauth2_tenant="acme",
        oauth2_client_id="cid",
        oauth2_client_secret="sec",
        oauth2_token_url="https://auth.lever.co/oauth/token",
    )
    assert isinstance(p, LeverProvider)
    assert p._oauth2_tenant == "acme"


@pytest.mark.asyncio
async def test_build_real_provider_unknown_falls_back_to_registry() -> None:
    """未知 provider → 退化到 registry (mock_ats)."""
    p = build_real_provider(provider_name="mock_ats", api_key="k")
    assert p.provider_name == "mock_ats"


if __name__ == "__main__":
    asyncio.run(test_oauth2_token_about_to_expire_is_treated_as_expired())
    print("OK: oauth2 tests")