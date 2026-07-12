"""MockVideoInterviewProvider 单元测试."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.providers.exceptions import InvalidRequestError
from backend.providers.video_interview import (
    Meeting,
    Participant,
    Recording,
    VideoInterviewProvider,
)
from backend.providers.video_interview.mock import MockVideoInterviewProvider


@pytest.fixture()
def provider() -> MockVideoInterviewProvider:
    return MockVideoInterviewProvider()


def _participants() -> list[Participant]:
    return [
        Participant(email="host@example.com", role="host"),
        Participant(email="candidate@example.com", role="attendee"),
    ]


@pytest.mark.asyncio
async def test_create_meeting_returns_urls(provider: MockVideoInterviewProvider) -> None:
    meeting = await provider.create_meeting(
        topic="Senior Eng Interview",
        start_time=datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc),
        duration_min=45,
        participants=_participants(),
        host_email="host@example.com",
    )
    assert isinstance(meeting, Meeting)
    assert meeting.meeting_id.startswith("mtg_mock_")
    assert meeting.join_url.startswith("https://mock-video.local/j/")
    assert meeting.host_url is not None
    assert meeting.duration_min == 45


@pytest.mark.asyncio
async def test_create_meeting_rejects_empty(provider: MockVideoInterviewProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.create_meeting(
            topic="x",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[],
        )


@pytest.mark.asyncio
async def test_cancel_meeting(provider: MockVideoInterviewProvider) -> None:
    meeting = await provider.create_meeting(
        topic="Cancel Test",
        start_time=datetime.now(timezone.utc),
        duration_min=15,
        participants=_participants(),
    )
    await provider.cancel_meeting(meeting.meeting_id)
    stored = provider.get_meeting(meeting.meeting_id)
    assert stored is not None
    assert stored.metadata.get("canceled") == "1"

    with pytest.raises(InvalidRequestError):
        await provider.cancel_meeting("mtg_mock_does_not_exist")


@pytest.mark.asyncio
async def test_get_recording_processing_then_available(provider: MockVideoInterviewProvider) -> None:
    meeting = await provider.create_meeting(
        topic="Rec Test",
        start_time=datetime.now(timezone.utc),
        duration_min=30,
        participants=_participants(),
    )
    rec = await provider.get_recording(meeting.meeting_id)
    assert isinstance(rec, Recording)
    assert rec.status == "processing"

    provider.seed_recording(meeting.meeting_id, duration_seconds=1800)
    rec2 = await provider.get_recording(meeting.meeting_id)
    assert rec2.status == "available"
    assert rec2.duration_seconds == 1800


def test_abc_subclass_compliance() -> None:
    assert isinstance(MockVideoInterviewProvider(), VideoInterviewProvider)