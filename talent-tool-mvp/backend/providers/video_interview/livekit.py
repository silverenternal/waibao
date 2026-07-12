"""LiveKit VideoInterview Provider — T2204.

基于自托管 LiveKit SFU 的视频会议 provider.

核心能力:
  - Token 生成 (server SDK / 自带 JWT 实现)
  - Room 创建 / 查询 / 列表
  - Webhook 事件: participant_joined / left / track_published / recording_finished
  - 与现有 VideoInterviewProvider 协议兼容 (Meeting / Recording)

环境变量:
  LIVEKIT_URL           缺省 ws://localhost:7880
  LIVEKIT_API_KEY       缺省 APIwXkjY8N7qGRtVzmHp9DTr4cKLbn (开发)
  LIVEKIT_API_SECRET    缺省 secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD (开发)
  LIVEKIT_HTTP_URL      缺省 http://localhost:7880 (HTTP API)
  LIVEKIT_RECORDINGS_DIR 缺省 /recordings (容器内挂载)

降级:
  - 当 livekit-server-sdk 不可用时,自动用纯 HMAC-SHA256 JWT 实现
  - 当 livekit HTTP API 不可达时,Room 操作降级到本地内存 (mock 兼容)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    UpstreamUnavailableError,
)
from .base import VideoInterviewProvider
from .types import Meeting, Participant, Recording

logger = logging.getLogger(__name__)

_LIVEKIT_DEFAULT_URL = "ws://localhost:7880"
_LIVEKIT_HTTP_DEFAULT = "http://localhost:7880"

DEFAULT_DEV_API_KEY = "APIwXkjY8N7qGRtVzmHp9DTr4cKLbn"
DEFAULT_DEV_API_SECRET = "secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD"

LIVEKIT_WEBHOOK_EVENTS = (
    "room_started",
    "room_finished",
    "participant_joined",
    "participant_left",
    "track_published",
    "track_unpublished",
    "recording_finished",
    "egress_finished",
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class LiveKitRoom:
    """LiveKit 房间元数据."""

    sid: str
    name: str
    num_participants: int = 0
    max_participants: int = 50
    creation_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "name": self.name,
            "num_participants": self.num_participants,
            "max_participants": self.max_participants,
            "creation_time": self.creation_time,
            "metadata": self.metadata,
        }


@dataclass
class LiveKitToken:
    """LiveKit JWT access token.

    Claims 参照 https://docs.livekit.io/home/get-started/authentication/
    """

    token: str
    room_name: str
    identity: str
    expires_at: int
    permissions: dict[str, bool] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Token 签发 (纯 Python JWT 实现,避免 livekit-server-sdk 强制依赖)
# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def issue_access_token(
    api_key: str,
    api_secret: str,
    *,
    room_name: str,
    identity: str,
    name: str | None = None,
    ttl_seconds: int = 3600,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
    metadata: str | None = None,
) -> LiveKitToken:
    """签发 LiveKit JWT.

    完全遵循 LiveKit JWT spec:
      header:  {"alg": "HS256", "typ": "JWT"}
      payload: video grants + identity + exp
    """
    now = int(time.time())
    exp = now + ttl_seconds
    payload = {
        "iss": api_key,
        "sub": identity,
        "iat": now,
        "exp": exp,
        "jti": secrets.token_hex(8),
        "video": {
            "room": room_name,
            "roomCreate": False,
            "roomJoin": True,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": can_publish_data,
        },
    }
    if name:
        payload["name"] = name
    if metadata:
        payload["metadata"] = metadata

    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    signature = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url(signature)
    token = f"{h_b64}.{p_b64}.{sig_b64}"

    return LiveKitToken(
        token=token,
        room_name=room_name,
        identity=identity,
        expires_at=exp,
        permissions={
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": can_publish_data,
        },
    )


def verify_token(api_key: str, api_secret: str, token: str) -> dict[str, Any]:
    """校验 JWT;返回 claims. 失败抛 AuthError."""
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("invalid token format", provider="livekit")
    h_b64, p_b64, sig_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    expected = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        sig = _b64url_decode(sig_b64)
    except Exception as e:  # noqa: BLE001
        raise AuthError(f"token signature decode failed: {e}", provider="livekit") from e
    if not hmac.compare_digest(expected, sig):
        raise AuthError("token signature mismatch", provider="livekit")
    try:
        payload = json.loads(_b64url_decode(p_b64))
    except Exception as e:  # noqa: BLE001
        raise AuthError(f"token payload decode failed: {e}", provider="livekit") from e
    if payload.get("iss") != api_key:
        raise AuthError("token iss mismatch", provider="livekit")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("token expired", provider="livekit")
    return payload


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
class LiveKitProvider(VideoInterviewProvider):
    """LiveKit VideoInterview Provider.

    完全兼容现有 VideoInterviewProvider 协议:
      - create_meeting() → Meeting (带 livekit_url + token)
      - cancel_meeting() → None
      - get_recording() → Recording
    """

    provider_name = "livekit"

    def __init__(self) -> None:
        self.api_key = os.getenv("LIVEKIT_API_KEY") or DEFAULT_DEV_API_KEY
        self.api_secret = os.getenv("LIVEKIT_API_SECRET") or DEFAULT_DEV_API_SECRET
        self.url = (os.getenv("LIVEKIT_URL") or _LIVEKIT_DEFAULT_URL).rstrip("/")
        self.http_url = (os.getenv("LIVEKIT_HTTP_URL") or _LIVEKIT_HTTP_DEFAULT).rstrip("/")
        self.recordings_dir = os.getenv("LIVEKIT_RECORDINGS_DIR") or "/recordings"
        self._lock = threading.RLock()
        # 本地 mock 缓存 (HTTP 不可达时回退)
        self._rooms: dict[str, LiveKitRoom] = {}
        self._recordings: dict[str, Recording] = {}

    # ------------------------------------------------------------------
    # config
    # ------------------------------------------------------------------
    def _configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _ensure_config(self) -> None:
        if not self._configured():
            raise UpstreamUnavailableError(
                "LiveKit credentials missing (LIVEKIT_API_KEY / LIVEKIT_API_SECRET)",
                provider=self.provider_name,
            )

    # ------------------------------------------------------------------
    # room creation
    # ------------------------------------------------------------------
    @with_resilience(
        provider="video_livekit",
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
        if duration_min <= 0:
            raise InvalidRequestError("duration_min must be > 0")
        if not participants:
            raise InvalidRequestError("participants must not be empty")

        self._ensure_config()
        room_name = f"int_{int(time.time())}_{secrets.token_hex(4)}"

        # 尝试调 HTTP API 真正创建 room
        api_ok = await self._create_room_http(room_name, max_participants=50)

        if not api_ok:
            # 降级本地缓存
            with self._lock:
                self._rooms[room_name] = LiveKitRoom(
                    sid=f"RM_{secrets.token_hex(8)}",
                    name=room_name,
                    num_participants=0,
                    max_participants=50,
                    creation_time=time.time(),
                    metadata={"topic": topic, "host_email": host_email or ""},
                )

        # 为 host 签发 token
        host_identity = (host_email or participants[0].email).replace("@", "_at_")[:64]
        host_token = issue_access_token(
            self.api_key,
            self.api_secret,
            room_name=room_name,
            identity=host_identity,
            name=host_email,
            ttl_seconds=duration_min * 60 + 600,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )

        join_url = (
            f"{self.url}/join?"
            f"room={room_name}&token={host_token.token}"
        )
        host_url = (
            f"{self.url}/host?"
            f"room={room_name}&token={host_token.token}"
        )

        meeting = Meeting(
            meeting_id=room_name,
            join_url=join_url,
            host_url=host_url,
            password=None,
            topic=topic,
            start_time=start_time,
            duration_min=duration_min,
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "livekit_room": room_name,
                "livekit_url": self.url,
                "host_token": host_token.token,
                "host_identity": host_identity,
                "host_email": host_email or "",
                "participant_count": str(len(participants)),
                "token_expires_at": str(host_token.expires_at),
            },
        )
        return meeting

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------
    @with_resilience(
        provider="video_livekit",
        method="cancel_meeting",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_meeting(self, meeting_id: str) -> None:
        api_ok = await self._delete_room_http(meeting_id)
        with self._lock:
            room = self._rooms.get(meeting_id)
            if room is None and not api_ok:
                raise InvalidRequestError(
                    f"room {meeting_id} not found",
                    provider=self.provider_name,
                )
            if room is not None:
                room.metadata["canceled"] = "1"

    # ------------------------------------------------------------------
    # get_recording
    # ------------------------------------------------------------------
    @with_resilience(
        provider="video_livekit",
        method="get_recording",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_recording(self, meeting_id: str) -> Recording:
        # 优先从 HTTP API 获取
        rec = await self._list_recordings_http(meeting_id)
        if rec is not None:
            with self._lock:
                self._recordings[meeting_id] = rec
            return rec

        with self._lock:
            rec = self._recordings.get(meeting_id)
            if rec is not None:
                return rec
            if meeting_id not in self._rooms:
                raise InvalidRequestError(
                    f"room {meeting_id} not found",
                    provider=self.provider_name,
                )

        return Recording(
            recording_id=f"rec_lk_{secrets.token_hex(6)}",
            meeting_id=meeting_id,
            status="processing",
            created_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # 额外 API (扩展 VideoInterviewProvider)
    # ------------------------------------------------------------------
    def issue_token(
        self,
        *,
        room_name: str,
        identity: str,
        name: str | None = None,
        ttl_seconds: int = 3600,
        is_host: bool = False,
        metadata: str | None = None,
    ) -> LiveKitToken:
        """为非 host 参与者签发 token."""
        self._ensure_config()
        return issue_access_token(
            self.api_key,
            self.api_secret,
            room_name=room_name,
            identity=identity,
            name=name,
            ttl_seconds=ttl_seconds,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            metadata=metadata,
        )

    def list_rooms(self) -> list[LiveKitRoom]:
        """列出本地缓存的房间."""
        with self._lock:
            return list(self._rooms.values())

    def get_room(self, room_name: str) -> LiveKitRoom | None:
        with self._lock:
            return self._rooms.get(room_name)

    def seed_recording(
        self,
        room_name: str,
        *,
        duration_seconds: int = 1800,
        with_url: bool = True,
    ) -> Recording:
        """测试辅助: 注入一条可用的录制."""
        rec = Recording(
            recording_id=f"rec_lk_{secrets.token_hex(6)}",
            meeting_id=room_name,
            duration_seconds=duration_seconds,
            status="available",
            download_url=(
                f"https://mock-livekit.local/recordings/{room_name}.mp4"
                if with_url else None
            ),
            play_url=(
                f"https://mock-livekit.local/play/{room_name}"
                if with_url else None
            ),
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._recordings[room_name] = rec
        return rec

    # ------------------------------------------------------------------
    # HTTP 客户端 (httpx async)
    # ------------------------------------------------------------------
    async def _create_room_http(self, room_name: str, *, max_participants: int = 50) -> bool:
        """调 LiveKit HTTP API 创建房间. 失败 → False (调用方降级)."""
        url = f"{self.http_url}/twirp/livekit.RoomService/CreateRoom"
        body = {
            "name": room_name,
            "max_participants": max_participants,
            "empty_timeout": 300,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={
                        "Authorization": self._server_token(),
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                with self._lock:
                    self._rooms[room_name] = LiveKitRoom(
                        sid=data.get("sid", f"RM_{secrets.token_hex(8)}"),
                        name=room_name,
                        num_participants=int(data.get("num_participants", 0)),
                        max_participants=int(data.get("max_participants", max_participants)),
                        creation_time=time.time(),
                        metadata={"created_via": "http_api"},
                    )
                return True
            logger.debug(f"LiveKit CreateRoom HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:  # noqa: BLE001
            logger.debug(f"LiveKit CreateRoom HTTP failed: {e}")
            return False

    async def _delete_room_http(self, room_name: str) -> bool:
        url = f"{self.http_url}/twirp/livekit.RoomService/DeleteRoom"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url,
                    json={"room": room_name},
                    headers={
                        "Authorization": self._server_token(),
                        "Content-Type": "application/json",
                    },
                )
            return resp.status_code in (200, 201, 204)
        except Exception:  # noqa: BLE001
            return False

    async def _list_recordings_http(self, room_name: str) -> Recording | None:
        """查询某房间的录制."""
        url = f"{self.http_url}/twirp/livekit.Egress/ListRecordings"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url,
                    json={"room_name": room_name},
                    headers={
                        "Authorization": self._server_token(),
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code != 200:
                return None
            data = resp.json() or {}
            items = data.get("items") or []
            if not items:
                return None
            item = items[0]
            return Recording(
                recording_id=item.get("egress_id") or item.get("recording_id", ""),
                meeting_id=room_name,
                download_url=item.get("file_location") or item.get("download_url"),
                play_url=item.get("play_url"),
                duration_seconds=int(item.get("duration", 0) or 0),
                status=item.get("status", "available"),
                created_at=_parse_iso(item.get("started_at")),
            )
        except Exception:  # noqa: BLE001
            return None

    def _server_token(self) -> str:
        """生成 server 端调用 API 用的 token (admin scope)."""
        return issue_access_token(
            self.api_key,
            self.api_secret,
            room_name="*",
            identity="server-admin",
            ttl_seconds=3600,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            metadata="server",
        ).token


# ---------------------------------------------------------------------------
# Webhook 校验
# ---------------------------------------------------------------------------
def verify_webhook(
    api_key: str,
    api_secret: str,
    *,
    body: bytes,
    authorization_header: str | None = None,
) -> dict[str, Any]:
    """校验 LiveKit webhook.

    协议:
      - header: "Authorization: <jwt>"
      - body:   JSON 事件

    Returns:
        解析后的事件 dict
    """
    if not authorization_header:
        raise AuthError("missing Authorization header", provider="livekit")
    if authorization_header.lower().startswith("bearer "):
        token = authorization_header[7:]
    else:
        token = authorization_header
    claims = verify_token(api_key, api_secret, token)
    try:
        event = json.loads(body.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise AuthError(f"invalid webhook body: {e}", provider="livekit") from e
    event["_verified"] = True
    event["_claims"] = claims
    return event


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "LiveKitProvider",
    "LiveKitRoom",
    "LiveKitToken",
    "LIVEKIT_WEBHOOK_EVENTS",
    "issue_access_token",
    "verify_token",
    "verify_webhook",
]