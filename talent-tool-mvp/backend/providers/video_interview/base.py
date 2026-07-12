"""VideoInterview Provider 抽象基类.

T1305 — 接入 Zoom / 腾讯会议 / Microsoft Teams / Google Meet.
业务层负责传 participants 与时间,供应商返回 join_url + host_url.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Meeting, Participant, Recording


class VideoInterviewProvider(ABC):
    """视频会议供应商抽象."""

    provider_name: str = "abstract"

    @abstractmethod
    async def create_meeting(
        self,
        topic: str,
        start_time: datetime,
        duration_min: int,
        participants: list["Participant"],
        *,
        host_email: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "Meeting":
        """创建会议,返回 join_url / host_url."""

    @abstractmethod
    async def cancel_meeting(self, meeting_id: str) -> None:
        """取消会议."""

    @abstractmethod
    async def get_recording(self, meeting_id: str) -> "Recording":
        """获取会议录制(可能尚未生成,此时 status='processing')."""