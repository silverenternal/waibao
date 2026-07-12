"""VideoInterview Provider 统一数据类型.

外部视频会议平台 (Zoom / 腾讯会议 / Microsoft Teams / Google Meet) 都用这一组结构暴露.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Participant:
    """视频会议参与者."""

    email: str
    name: str | None = None
    role: str = "attendee"  # host / attendee / panelist
    user_id: str | None = None  # 业务系统用户 ID
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Meeting:
    """视频会议."""

    meeting_id: str
    join_url: str
    host_url: str | None = None
    password: str | None = None
    topic: str = ""
    start_time: datetime | None = None
    duration_min: int = 30
    provider: str = "mock"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Recording:
    """会议录制结果."""

    recording_id: str
    meeting_id: str
    download_url: str | None = None
    play_url: str | None = None
    duration_seconds: int = 0
    status: str = "available"  # processing / available / failed
    created_at: datetime | None = None
    transcript_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)