"""Zoom VideoInterview Provider (T1305).

Zoom Server-to-Server OAuth:
  https://developers.zoom.us/docs/internal-apps/s2s-oauth/

API base: https://api.zoom.us/v2
  - POST   /users/me/meetings         创建会议
  - DELETE /meetings/{meetingId}      取消
  - GET    /meetings/{meetingId}/recordings   获取录制

环境变量:
  ZOOM_PROVIDER=true               # 启用本 provider,缺省/mock
  ZOOM_ACCOUNT_ID                  # Server-to-Server account id
  ZOOM_CLIENT_ID                   # OAuth client id
  ZOOM_CLIENT_SECRET               # OAuth client secret
  ZOOM_HOST_USER_ID=me             # 缺省 me (=master account)
  ZOOM_API_BASE                    # 缺省 https://api.zoom.us/v2

真实 API 调用使用 httpx.AsyncClient; 不可用或异常 → 由上层 fallback。
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    RateLimitError,
    TimeoutError,
    UpstreamUnavailableError,
)
from .base import VideoInterviewProvider
from .types import Meeting, Participant, Recording

logger = logging.getLogger(__name__)

_ZOOM_DEFAULT_BASE = "https://api.zoom.us/v2"
_TOKEN_URL = "https://zoom.us/oauth/token"


class ZoomProvider(VideoInterviewProvider):
    """Zoom 视频会议 Provider.

    使用 Server-to-Server OAuth 自动换取 access token,无需 user interaction.
    """

    provider_name = "zoom"

    def __init__(self) -> None:
        self.account_id = os.getenv("ZOOM_ACCOUNT_ID") or ""
        self.client_id = os.getenv("ZOOM_CLIENT_ID") or ""
        self.client_secret = os.getenv("ZOOM_CLIENT_SECRET") or ""
        self.host_user_id = os.getenv("ZOOM_HOST_USER_ID") or "me"
        self.base_url = (os.getenv("ZOOM_API_BASE") or _ZOOM_DEFAULT_BASE).rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # config validation
    # ------------------------------------------------------------------
    def _configured(self) -> bool:
        return bool(self.account_id and self.client_id and self.client_secret)

    def _ensure_config(self) -> None:
        if not self._configured():
            raise UpstreamUnavailableError(
                "Zoom credentials missing (ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET)",
                provider=self.provider_name,
            )

    # ------------------------------------------------------------------
    # OAuth token cache (server-to-server)
    # ------------------------------------------------------------------
    async def _get_token(self) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - 30:
                return self._token
            self._ensure_config()
            auth = (self.client_id, self.client_secret)
            data = {
                "grant_type": "account_credentials",
                "account_id": self.account_id,
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        _TOKEN_URL,
                        auth=auth,
                        data=data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"zoom oauth timeout: {exc}", provider=self.provider_name
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"zoom oauth network error: {exc}", provider=self.provider_name
                ) from exc
            if resp.status_code in (401, 403):
                raise AuthError(
                    f"zoom oauth unauthorized: {resp.text}",
                    provider=self.provider_name,
                    status_code=resp.status_code,
                )
            if resp.status_code >= 500:
                raise UpstreamUnavailableError(
                    f"zoom oauth {resp.status_code}: {resp.text}",
                    provider=self.provider_name,
                )
            if resp.status_code >= 400:
                raise InvalidRequestError(
                    f"zoom oauth {resp.status_code}: {resp.text}",
                    provider=self.provider_name,
                    status_code=resp.status_code,
                )
            payload = resp.json()
            self._token = payload["access_token"]
            # access_token 默认 1 小时
            self._token_expires_at = now + float(payload.get("expires_in", 3600))
            return self._token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # request helpers
    # ------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        headers = await self._auth_headers()
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"zoom {method} {path} timeout: {exc}", provider=self.provider_name
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"zoom {method} {path} network error: {exc}",
                provider=self.provider_name,
            ) from exc

        # 处理 auth 失效: 401 → 强制刷新一次
        if resp.status_code == 401 and self._token is not None:
            self._token = None
            self._token_expires_at = 0.0
            headers = await self._auth_headers()
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                        params=params,
                    )
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"zoom {method} {path} retry network error: {exc}",
                    provider=self.provider_name,
                ) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"zoom rate-limited: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"zoom {method} {path} auth failed: {resp.text}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code == 404:
            return 404, None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"zoom {method} {path} {resp.status_code}: {resp.text}",
                provider=self.provider_name,
            )
        # 2xx / 4xx 让上层解析
        try:
            data: Any = resp.json() if resp.text else {}
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data

    # ------------------------------------------------------------------
    # 抽象方法
    # ------------------------------------------------------------------
    @with_resilience(
        provider="zoom",
        method="create_meeting",
        retry=RetryPolicy(max_retries=2),
    )
    async def create_meeting(
        self,
        topic: str,
        start_time: datetime,
        duration_min: int,
        participants: list[Participant],
        *,
        host_email: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Meeting:
        if not participants:
            raise InvalidRequestError("participants must not be empty")
        if duration_min <= 0:
            raise InvalidRequestError("duration_min must be > 0")
        payload = {
            "topic": topic,
            "type": 2,  # scheduled meeting
            "start_time": start_time.astimezone(timezone.utc).isoformat(),
            "duration": duration_min,
            "timezone": "UTC",
            "settings": {
                "join_before_host": False,
                "waiting_room": True,
                "mute_upon_entry": True,
                "approval_type": 0,
            },
        }
        status, data = await self._request(
            "POST",
            f"/users/{self.host_user_id}/meetings",
            json=payload,
        )
        if status >= 400 or not isinstance(data, dict) or "id" not in data:
            raise UpstreamUnavailableError(
                f"zoom create_meeting unexpected response status={status}",
                provider=self.provider_name,
                details={"body": data},
            )

        meeting_id = str(data["id"])
        join_url = data.get("join_url") or ""
        password = data.get("password") or secrets.token_urlsafe(8)
        return Meeting(
            meeting_id=meeting_id,
            join_url=join_url,
            host_url=f"{join_url}&uname=host" if join_url else None,
            password=password,
            topic=topic,
            start_time=start_time,
            duration_min=duration_min,
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "host_email": host_email or "",
                "host_id": str(data.get("host_id") or ""),
                "participants": ",".join(p.email for p in participants),
                "uuid": str(data.get("uuid") or ""),
            },
        )

    @with_resilience(
        provider="zoom",
        method="cancel_meeting",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_meeting(self, meeting_id: str) -> None:
        status, data = await self._request(
            "DELETE",
            f"/meetings/{meeting_id}",
        )
        # 404 视为已取消
        if status == 404:
            logger.info("zoom.cancel.404 meeting_id=%s", meeting_id)
            return
        if status >= 400:
            raise UpstreamUnavailableError(
                f"zoom cancel_meeting {status}: {data}",
                provider=self.provider_name,
            )

    @with_resilience(
        provider="zoom",
        method="get_recording",
        retry=RetryPolicy(max_retries=3),
    )
    async def get_recording(self, meeting_id: str) -> Recording:
        status, data = await self._request(
            "GET",
            f"/meetings/{meeting_id}/recordings",
        )
        if status == 404 or not data:
            return Recording(
                recording_id=f"rec_zoom_{secrets.token_hex(6)}",
                meeting_id=meeting_id,
                status="processing",
                created_at=datetime.now(timezone.utc),
                metadata={"provider": self.provider_name},
            )
        # 优先取第一个 mp4
        rec_files = data.get("recording_files") or []
        mp4 = next(
            (f for f in rec_files if (f.get("file_type") or "").lower() == "mp4"),
            rec_files[0] if rec_files else None,
        )
        download_url = mp4.get("download_url") if mp4 else None
        play_url = mp4.get("play_url") if mp4 else None
        duration_ms = int(mp4.get("duration") or 0) if mp4 else 0
        start = data.get("start_time")
        completed_at = None
        if start:
            try:
                completed_at = datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                )
            except Exception:
                completed_at = None

        status_str = "available" if download_url else "processing"
        return Recording(
            recording_id=str(data.get("uuid") or f"rec_zoom_{secrets.token_hex(6)}"),
            meeting_id=meeting_id,
            download_url=download_url,
            play_url=play_url,
            duration_seconds=duration_ms // 1000 if duration_ms else 0,
            status=status_str,
            created_at=completed_at,
            metadata={
                "account_id": str(data.get("account_id") or ""),
                "host_id": str(data.get("host_id") or ""),
                "topic": str(data.get("topic") or ""),
                "provider": self.provider_name,
            },
        )
