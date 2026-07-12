"""LiveKit API — T2204.

Endpoints
---------
- POST /api/livekit/rooms                  create a LiveKit room (host)
- POST /api/livekit/token                  issue an access token for a participant
- GET  /api/livekit/rooms/{room_name}      get room metadata
- GET  /api/livekit/recordings/{room_id}   get recording for a room
- POST /api/livekit/webhook                LiveKit server → us (verified)

设计:
  - 全部需要登录 (get_current_user)
  - Webhook 不需要登录 (用 JWT 签名校验)
  - Host 创建房间时返回 host_token + host_url
  - Participant 通过 /token 拿自己的 token
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from providers.video_interview.livekit import (
    LIVEKIT_WEBHOOK_EVENTS,
    LiveKitProvider,
    verify_webhook,
)
from providers.video_interview.types import Participant

logger = logging.getLogger("recruittech.api.livekit")
router = APIRouter()


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------
def _provider() -> LiveKitProvider:
    """每次取一个新实例(无状态)."""
    return LiveKitProvider()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class CreateRoomBody(BaseModel):
    topic: str = Field(..., description="会议主题")
    start_time: str | None = None
    duration_min: int = 30
    participants: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, str] | None = None


class TokenBody(BaseModel):
    room_name: str
    identity: str
    name: str | None = None
    ttl_seconds: int = 3600
    is_host: bool = False
    metadata: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/rooms")
async def create_room(
    body: CreateRoomBody, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """创建 LiveKit 房间 (host)."""
    p = _provider()
    try:
        start_time = (
            datetime.fromisoformat(body.start_time.replace("Z", "+00:00"))
            if body.start_time else datetime.utcnow()
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid start_time: {e}")

    participants = [
        Participant(
            email=str(p.get("email", "anon@example.com")),
            name=p.get("name"),
            role=p.get("role", "attendee"),
            user_id=p.get("user_id"),
            metadata=p.get("metadata") or {},
        )
        for p in body.participants
    ]

    meeting = await p.create_meeting(
        topic=body.topic,
        start_time=start_time,
        duration_min=body.duration_min,
        participants=participants or [Participant(email=user.email, name=user.email, role="host")],
        host_email=user.email,
        metadata=body.metadata,
    )

    return {
        "room_name": meeting.meeting_id,
        "livekit_url": meeting.metadata.get("livekit_url"),
        "host_token": meeting.metadata.get("host_token"),
        "host_url": meeting.host_url,
        "join_url": meeting.join_url,
        "topic": meeting.topic,
        "start_time": meeting.start_time.isoformat() if meeting.start_time else None,
        "duration_min": meeting.duration_min,
        "participants": body.participants,
        "expires_at": meeting.metadata.get("token_expires_at"),
    }


@router.post("/token")
async def issue_token(
    body: TokenBody, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """为参与者签发 LiveKit token."""
    p = _provider()
    try:
        tok = p.issue_token(
            room_name=body.room_name,
            identity=body.identity or f"user_{user.id}"[:64],
            name=body.name or user.email,
            ttl_seconds=body.ttl_seconds,
            is_host=body.is_host,
            metadata=body.metadata,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LiveKit not configured: {e}")
    return {
        "token": tok.token,
        "room_name": tok.room_name,
        "identity": tok.identity,
        "expires_at": tok.expires_at,
        "permissions": tok.permissions,
        "livekit_url": os.getenv("LIVEKIT_URL") or "ws://localhost:7880",
    }


@router.get("/rooms/{room_name}")
async def get_room(
    room_name: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    p = _provider()
    room = p.get_room(room_name)
    if room is None:
        raise HTTPException(status_code=404, detail=f"room {room_name} not found")
    return room.to_dict()


@router.get("/recordings/{room_id}")
async def get_recording(
    room_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    p = _provider()
    rec = await p.get_recording(room_id)
    return {
        "recording_id": rec.recording_id,
        "meeting_id": rec.meeting_id,
        "download_url": rec.download_url,
        "play_url": rec.play_url,
        "duration_seconds": rec.duration_seconds,
        "status": rec.status,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "transcript_url": rec.transcript_url,
        "metadata": rec.metadata,
    }


@router.post("/webhook")
async def webhook(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """LiveKit server → backend webhook.

    标准事件:
      - room_started / room_finished
      - participant_joined / participant_left
      - track_published / track_unpublished
      - recording_finished / egress_finished
    """
    body = await request.body()
    api_key = os.getenv("LIVEKIT_API_KEY") or "APIwXkjY8N7qGRtVzmHp9DTr4cKLbn"
    api_secret = os.getenv("LIVEKIT_API_SECRET") or "secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD"

    try:
        event = verify_webhook(
            api_key, api_secret, body=body, authorization_header=authorization
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"livekit webhook verify failed: {e}")
        raise HTTPException(status_code=401, detail=f"webhook auth failed: {e}")

    event_name = event.get("event") or event.get("type", "unknown")
    if event_name not in LIVEKIT_WEBHOOK_EVENTS:
        logger.debug(f"unknown livekit event: {event_name}")

    # 业务侧: 根据事件触发后续动作 (录制完成 → 转写/分析)
    try:
        from eventbus import emit
        if event_name == "recording_finished":
            emit(
                "video.recording_finished",
                {
                    "room_name": event.get("room", {}).get("name") or event.get("room_name"),
                    "egress_id": event.get("egress", {}).get("egress_id") or event.get("egress_id"),
                    "duration_seconds": event.get("egress", {}).get("duration", 0),
                },
                source="livekit.webhook",
            )
        elif event_name == "participant_joined":
            emit(
                "video.participant_joined",
                {
                    "room_name": event.get("room", {}).get("name"),
                    "participant_identity": event.get("participant", {}).get("identity"),
                },
                source="livekit.webhook",
            )
        elif event_name == "participant_left":
            emit(
                "video.participant_left",
                {
                    "room_name": event.get("room", {}).get("name"),
                    "participant_identity": event.get("participant", {}).get("identity"),
                },
                source="livekit.webhook",
            )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"eventbus publish failed: {e}")

    return {"ok": True, "event": event_name}