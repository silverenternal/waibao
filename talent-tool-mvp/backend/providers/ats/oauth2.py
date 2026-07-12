"""T1806 — OAuth2 Token Store for ATS providers (Greenhouse + Lever).

ATS 提供商有两种认证:
1. Basic Auth  (api_key:``) — 长期凭证
2. OAuth2      — 短期 access_token (1h/2h) + refresh_token

Greenhouse 不支持 OAuth2 (用 Basic Auth + On-Behalf-Of token 代替),
Lever 不支持 OAuth2 (用 Basic Auth).

但 v3.0 ATS 扩展性要求: 给 Bullhorn/Workable/iCIMS 等 ATS 留 OAuth2 接口。
本模块提供统一的 OAuth2 Token 管理:
    - 自动过期前 60s 刷新
    - 多 tenant 隔离
    - 线程安全 (asyncio.Lock)

使用:
    store = InMemoryOAuth2TokenStore()
    token = await store.get_or_refresh(
        tenant="acme",
        client_id="...",
        client_secret="...",
        token_url="https://auth.bullhorn.com/oauth/token",
    )
    headers = {"Authorization": f"Bearer {token.access_token}"}
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OAuth2Token:
    """OAuth2 凭证."""

    access_token: str
    refresh_token: str | None
    expires_at: float  # epoch seconds
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def is_expired(self) -> bool:
        # 提前 60 秒视为过期, 避免边界情况
        return time.time() >= self.expires_at - 60.0

    def to_header(self) -> str:
        return f"{self.token_type} {self.access_token}"


class HTTPClient(Protocol):
    """asyncio HTTP client 抽象 — 可注入 httpx/aiohttp/test mock."""

    async def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> tuple[int, dict[str, Any]]: ...


class HttpxOAuth2Client:
    """默认 httpx 实现的 OAuth2 client."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owns = client is None
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> tuple[int, dict[str, Any]]:
        resp = await self._client.post(url, data=data, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:512]}
        return resp.status_code, body

    async def aclose(self) -> None:
        if self._owns:
            await self._client.aclose()


class OAuth2TokenStore(Protocol):
    """Token 存储接口 — 实现方可选 Redis / Supabase / 内存."""

    async def get(self, tenant: str) -> OAuth2Token | None: ...
    async def put(self, tenant: str, token: OAuth2Token) -> None: ...
    async def clear(self, tenant: str) -> None: ...


class InMemoryOAuth2TokenStore:
    """线程安全的内存实现, 适合单进程部署 + 测试."""

    def __init__(self) -> None:
        self._tokens: dict[str, OAuth2Token] = {}
        self._lock = asyncio.Lock()

    async def get(self, tenant: str) -> OAuth2Token | None:
        async with self._lock:
            return self._tokens.get(tenant)

    async def put(self, tenant: str, token: OAuth2Token) -> None:
        async with self._lock:
            self._tokens[tenant] = token

    async def clear(self, tenant: str) -> None:
        async with self._lock:
            self._tokens.pop(tenant, None)


# ---------------------------------------------------------------------------
# Token refresh 引擎
# ---------------------------------------------------------------------------


class OAuth2TokenManager:
    """管理 OAuth2 token 自动刷新 — 多租户安全.

    用法:
        mgr = OAuth2TokenManager(store, http_client)
        token = await mgr.get_or_refresh(
            tenant="acme",
            client_id="cid",
            client_secret="sec",
            token_url="https://auth.example.com/oauth/token",
            scope="read write",
        )
    """

    def __init__(
        self,
        store: OAuth2TokenStore | None = None,
        http_client: HTTPClient | None = None,
    ) -> None:
        self._store = store or InMemoryOAuth2TokenStore()
        self._http = http_client or HttpxOAuth2Client()
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _lock_for(self, tenant: str) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(tenant)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[tenant] = lock
            return lock

    async def get_or_refresh(
        self,
        *,
        tenant: str,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> OAuth2Token:
        """返回有效 token. 必要时用 refresh_token 续期或重新获取."""
        lock = await self._lock_for(tenant)
        async with lock:
            current = await self._store.get(tenant)
            if current and not current.is_expired:
                return current

            # 有 refresh_token 优先用
            if current and current.refresh_token:
                try:
                    refreshed = await self._refresh(
                        token_url=token_url,
                        refresh_token=current.refresh_token,
                        client_id=client_id,
                        client_secret=client_secret,
                    )
                    await self._store.put(tenant, refreshed)
                    logger.info("oauth2.refreshed tenant=%s", tenant)
                    return refreshed
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "oauth2.refresh_failed tenant=%s err=%s — fall back to client_credentials",
                        tenant, exc,
                    )

            # 回退: client_credentials
            fresh = await self._client_credentials(
                token_url=token_url,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
                extra_params=extra_params or {},
            )
            await self._store.put(tenant, fresh)
            logger.info("oauth2.issued tenant=%s expires_at=%.0f", tenant, fresh.expires_at)
            return fresh

    async def _client_credentials(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        extra_params: dict[str, str],
    ) -> OAuth2Token:
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            data["scope"] = scope
        data.update(extra_params)
        status, body = await self._http.post(token_url, data=data)
        if status >= 400:
            raise OAuth2Error(f"client_credentials failed: {status} {body}")
        return _token_from_response(body)

    async def _refresh(
        self,
        *,
        token_url: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> OAuth2Token:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        status, body = await self._http.post(token_url, data=data)
        if status >= 400:
            raise OAuth2Error(f"refresh failed: {status} {body}")
        return _token_from_response(body)


def _token_from_response(body: dict[str, Any]) -> OAuth2Token:
    """从 OAuth2 token endpoint 响应构造 OAuth2Token."""
    if "access_token" not in body:
        raise OAuth2Error(f"missing access_token in response: {body}")
    expires_in = float(body.get("expires_in") or 3600)
    return OAuth2Token(
        access_token=str(body["access_token"]),
        refresh_token=body.get("refresh_token"),
        expires_at=time.time() + expires_in,
        token_type=body.get("token_type", "Bearer"),
        scope=body.get("scope", ""),
    )


class OAuth2Error(Exception):
    """OAuth2 流程异常."""


__all__ = [
    "OAuth2Token",
    "OAuth2TokenStore",
    "InMemoryOAuth2TokenStore",
    "OAuth2TokenManager",
    "HttpxOAuth2Client",
    "HTTPClient",
    "OAuth2Error",
]