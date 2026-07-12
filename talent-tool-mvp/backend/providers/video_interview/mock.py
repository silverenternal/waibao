"""VideoInterview Provider Mock 实现."""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone

from ..base import RetryPolicy, with_resilience
from ..exceptions import InvalidRequestError
from .base import VideoInterviewProvider
from .types import Meeting, Participant, Recording


class MockVideoInterviewProvider(VideoInterviewProvider):
    """Mock 实现,内存保存会议 + 录制."""

    provider_name = "mock_video"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._meetings: dict[str, Meeting] = {}
        self._recordings: dict[str, Recording] = {}

    @with_resilience(
        provider="video_mock",
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
        meeting_id = f"mtg_mock_{secrets.token_hex(6)}"
        password = secrets.token_urlsafe(8)
        join_url = f"https://mock-video.local/j/{meeting_id}?pwd={password}"
        host_url = f"https://mock-video.local/h/{meeting_id}?pwd={password}"
        meeting = Meeting(
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
                "participant_count": str(len(participants)),
            },
        )
        with self._lock:
            self._meetings[meeting_id] = meeting
        return meeting

    @with_resilience(
        provider="video_mock",
        method="cancel_meeting",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_meeting(self, meeting_id: str) -> None:
        with self._lock:
            if meeting_id not in self._meetings:
                raise InvalidRequestError(
                    f"meeting {meeting_id} not found",
                    provider=self.provider_name,
                )
            self._meetings[meeting_id].metadata["canceled"] = "1"

    @with_resilience(
        provider="video_mock",
        method="get_recording",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_recording(self, meeting_id: str) -> Recording:
        with self._lock:
            rec = self._recordings.get(meeting_id)
            if rec is not None:
                return rec
            if meeting_id not in self._meetings:
                raise InvalidRequestError(
                    f"meeting {meeting_id} not found",
                    provider=self.provider_name,
                )
        # 默认返回 processing 状态
        return Recording(
            recording_id=f"rec_mock_{secrets.token_hex(6)}",
            meeting_id=meeting_id,
            status="processing",
            created_at=datetime.now(timezone.utc),
        )

    # ----- 测试辅助 -----
    def seed_recording(
        self,
        meeting_id: str,
        *,
        duration_seconds: int = 1800,
        with_url: bool = True,
    ) -> Recording:
        """测试前注入一条可用的录制."""
        rec = Recording(
            recording_id=f"rec_mock_{secrets.token_hex(6)}",
            meeting_id=meeting_id,
            duration_seconds=duration_seconds,
            status="available",
            download_url=f"https://mock-video.local/rec/{meeting_id}.mp4" if with_url else None,
            play_url=f"https://mock-video.local/play/{meeting_id}" if with_url else None,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._recordings[meeting_id] = rec
        return rec

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        with self._lock:
            return self._meetings.get(meeting_id)