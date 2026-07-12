"""腾讯会议 VideoInterview Provider (T1305).

对接腾讯会议开放平台 REST API:
  https://cloud.tencent.com/document/product/1095

鉴权: 应用密钥 + OAuth2 客户端凭证 (client_credentials)
  https://meeting.tencent.com/open-apis/auth

能力:
  - 创建预约会议  POST /v1/meetings
  - 取消会议      DELETE /v1/meetings/{meeting_id}
  - 查询录制       GET /v1/records?meeting_id={meeting_id}

环境变量:
  TENCENT_MEETING_PROVIDER=true
  TENCENT_MEETING_APP_ID
  TENCENT_MEETING_APP_SECRET
  TENCENT_MEETING_BASE_URL   缺省 https://api.meeting.qq.com
  TENCENT_MEETING_USERID     host 用户 id
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

_TM_DEFAULT_BASE = "https://api.meeting.qq.com"


class TencentMeetingProvider(VideoInterviewProvider):
    """腾讯会议 video interview provider."""

    provider_name = "tencent_meeting"

    def __init__(self) -> None:
        self.app_id = os.getenv("TENCENT_MEETING_APP_ID") or ""
        self.app_secret = os.getenv("TENCENT_MEETING_APP_SECRET") or ""
        self.userid = os.getenv("TENCENT_MEETING_USERID") or ""
        self.base_url = (
            os.getenv("TENCENT_MEETING_BASE_URL") or _TM_DEFAULT_BASE
        ).rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    def _configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _ensure_config(self) -> None:
        if not self._configured():
            raise UpstreamUnavailableError(
                "Tencent Meeting credentials missing "
                "(TENCENT_MEETING_APP_ID / TENCENT_MEETING_APP_SECRET)",
                provider=self.provider_name,
            )

    async def _get_token(self) -> str:
        """客户端凭证模式换 access_token;有效期内缓存."""
        async with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - 60:
                return self._token
            self._ensure_config()
            payload = {
                "app_id": self.app_id,
                "sdk_id": self.app_id,
                "secret": self.app_secret,
                "grant_type": "client_credentials",
                "userid": self.userid or "default",
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/oauth/token",
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"tencent_meeting oauth timeout: {exc}",
                    provider=self.provider_name,
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"tencent_meeting oauth network error: {exc}",
                    provider=self.provider_name,
                ) from exc
            if resp.status_code in (401, 403):
                raise AuthError(
                    f"tencent_meeting oauth unauthorized: {resp.text}",
                    provider=self.provider_name,
                )
            if resp.status_code >= 500:
                raise UpstreamUnavailableError(
                    f"tencent_meeting oauth {resp.status_code}",
                    provider=self.provider_name,
                )
            try:
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                raise UpstreamUnavailableError(
                    f"tencent_meeting oauth invalid json: {exc}",
                    provider=self.provider_name,
                ) from exc
            # 腾讯返回结构: { error_code, error_msg, access_token, expires_in }
            if data.get("error_code") not in (0, None, ""):
                raise AuthError(
                    f"tencent_meeting oauth error: "
                    f"{data.get('error_code')} {data.get('error_msg')}",
                    provider=self.provider_name,
                )
            self._token = data["access_token"]
            self._token_expires_at = now + float(data.get("expires_in", 7200))
            return self._token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "AppId": self.app_id,
            "UserId": self.userid or "default",
        }

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
                f"tencent_meeting {method} {path} timeout: {exc}",
                provider=self.provider_name,
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"tencent_meeting {method} {path} network error: {exc}",
                provider=self.provider_name,
            ) from exc

        # 401 token 失效 → 强制刷新一次
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
                    f"tencent_meeting {method} {path} retry network error: {exc}",
                    provider=self.provider_name,
                ) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"tencent_meeting rate-limited: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"tencent_meeting {method} {path} auth failed: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code == 404:
            return 404, None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"tencent_meeting {method} {path} {resp.status_code}",
                provider=self.provider_name,
            )
        try:
            data: Any = resp.json() if resp.text else {}
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data

    # ------------------------------------------------------------------
    # abstract methods
    # ------------------------------------------------------------------
    @with_resilience(
        provider="tencent_meeting",
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
        # 腾讯会议时间格式: YYYY-MM-DD HH:MM:SS (北京时间)
        local_start = start_time.astimezone().replace(tzinfo=None)
        start_str = local_start.strftime("%Y-%m-%d %H:%M:%S")
        payload: dict[str, Any] = {
            "userid": self.userid or (host_email or "host"),
            "instanceid": 1,
            "subject": topic,
            "type": 0,
            "start_time": start_str,
            "duration": duration_min,
            "attendees": [
                {"userid": p.email, "name": p.name or p.email}
                for p in participants
            ],
            "settings": {
                "mute_enable": True,
                "waiting_room": True,
            },
        }
        status, data = await self._request(
            "POST", "/v1/meetings", json=payload,
        )
        if status >= 400 or not isinstance(data, dict):
            raise UpstreamUnavailableError(
                f"tencent_meeting create error {status}: {data}",
                provider=self.provider_name,
            )
        # 0 表示业务成功
        err_code = data.get("error_code")
        if err_code not in (0, None):
            raise UpstreamUnavailableError(
                f"tencent_meeting create error {err_code}: "
                f"{data.get('error_msg')}",
                provider=self.provider_name,
                details={"response": data},
            )

        meeting_id = str(
            data.get("meeting_id") or data.get("meeting_number") or
            f"tm_{secrets.token_hex(6)}"
        )
        join_url = (
            data.get("join_url")
            or (data.get("meeting_info") or {}).get("join_url")
            or f"https://meeting.tencent.com/j/{meeting_id}"
        )
        host_url = (
            data.get("host_url")
            or (data.get("meeting_info") or {}).get("host_url")
            or f"https://meeting.tencent.com/h/{meeting_id}"
        )
        password = str(data.get("password") or secrets.token_urlsafe(8))

        return Meeting(
            meeting_id=meeting_id,
            join_url=join_url,
            host_url=host_url,
            password=password,
            topic=topic,
            start_time=start_time,
            duration_min=duration_min,
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "host_email": host_email or "",
                "host_userid": str(data.get("userid") or self.userid or ""),
                "meeting_number": str(
                    data.get("meeting_number") or meeting_id
                ),
            },
        )

    @with_resilience(
        provider="tencent_meeting",
        method="cancel_meeting",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_meeting(self, meeting_id: str) -> None:
        status, data = await self._request(
            "DELETE",
            f"/v1/meetings/{meeting_id}",
            params={"userid": self.userid or "host"},
        )
        if status == 404:
            return
        if status >= 400:
            raise UpstreamUnavailableError(
                f"tencent_meeting cancel {status}: {data}",
                provider=self.provider_name,
            )
        if isinstance(data, dict) and data.get("error_code") not in (0, None):
            raise UpstreamUnavailableError(
                f"tencent_meeting cancel error "
                f"{data.get('error_code')}: {data.get('error_msg')}",
                provider=self.provider_name,
            )

    @with_resilience(
        provider="tencent_meeting",
        method="get_recording",
        retry=RetryPolicy(max_retries=3),
    )
    async def get_recording(self, meeting_id: str) -> Recording:
        status, data = await self._request(
            "GET",
            "/v1/records",
            params={"meeting_id": meeting_id},
        )
        if status == 404 or not data:
            return Recording(
                recording_id=f"rec_tm_{secrets.token_hex(6)}",
                meeting_id=meeting_id,
                status="processing",
                created_at=datetime.now(timezone.utc),
                metadata={"provider": self.provider_name},
            )
        record_items = data.get("record_meeting") or data.get("records") or []
        if isinstance(record_items, dict):
            record_items = [record_items]
        first = record_items[0] if record_items else {}
        download_url = first.get("download_url") or first.get("record_url")
        play_url = first.get("play_url") or first.get("view_url")
        duration_sec = int(first.get("duration") or 0)
        rec_id = str(
            first.get("record_id") or f"rec_tm_{secrets.token_hex(6)}"
        )
        start_str = first.get("start_time")
        created_at = None
        if start_str:
            try:
                created_at = datetime.fromisoformat(str(start_str))
            except Exception:
                created_at = None
        return Recording(
            recording_id=rec_id,
            meeting_id=meeting_id,
            download_url=download_url,
            play_url=play_url,
            duration_seconds=duration_sec,
            status="available" if download_url else "processing",
            created_at=created_at,
            metadata={
                "meeting_number": str(first.get("meeting_number") or ""),
                "subject": str(first.get("subject") or ""),
                "raw_error_code": str(data.get("error_code") or ""),
                "provider": self.provider_name,
            },
        )
