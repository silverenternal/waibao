"""腾讯会议 client_credentials OAuth + 真实 API 接入验证 (T1805).

默认 **跳过** — 需要 TENCENT_MEETING_APP_ID / TENCENT_MEETING_APP_SECRET:

    export TENCENT_MEETING_APP_ID="..."
    export TENCENT_MEETING_APP_SECRET="..."
    pytest -m real_api backend/providers/video_interview/tests/test_tencent_meeting_real.py

凭证申请: docs/VIDEO_INTERVIEW_SETUP.md (腾讯会议章节)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backend.providers.video_interview.tencent_meeting import TencentMeetingProvider
from backend.providers.video_interview.types import Participant


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (
            os.getenv("TENCENT_MEETING_APP_ID")
            and os.getenv("TENCENT_MEETING_APP_SECRET")
        ),
        reason="TENCENT_MEETING_APP_ID/SECRET 未设置 — 跳过腾讯会议真实测试",
    ),
]


@pytest.fixture
def provider():
    return TencentMeetingProvider()


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.app_id
    assert provider.app_secret


@pytest.mark.asyncio
async def test_acquire_oauth_token(provider):
    """client_credentials OAuth 应返回有效 access_token."""
    token = await provider._get_token()
    assert isinstance(token, str)
    assert len(token) > 20
    # 第二次调用应复用缓存
    token2 = await provider._get_token()
    assert token == token2


@pytest.mark.asyncio
async def test_create_single_meeting_real(provider):
    """真实创建一个会议,验证 join_url + meeting_id 正常."""
    start = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    meeting = await provider.create_meeting(
        topic="[Waibao Test] TM real integration",
        start_time=start,
        duration_min=30,
        participants=[
            Participant(email=os.getenv("TEST_EMAIL_TO", "test@example.com"))
        ],
        metadata={"test_run_id": "tm-001"},
    )
    assert meeting.meeting_id
    assert meeting.join_url.startswith("https://")
    # 清理 — 尝试取消
    await provider.cancel_meeting(meeting.meeting_id)


@pytest.mark.asyncio
async def test_create_three_meetings_panel_round(provider):
    """T1805: 一次 panel 自动生成 3 个会议 (默认 3 轮)."""
    start = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    candidate_id = os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com")
    panel = [
        os.getenv("TEST_PANELIST_1", "tech_lead@example.com"),
        os.getenv("TEST_PANELIST_2", "hr_partner@example.com"),
        os.getenv("TEST_PANELIST_3", "director@example.com"),
    ]
    meetings = await provider.create_panel_round(
        candidate_id=candidate_id,
        topic="[Waibao] Senior 后端面试 (腾讯)",
        panelist_userids=panel,
        start_time=start,
        duration_min=60,
        rounds=3,
        metadata={"role_id": "role_001", "channel": "tencent"},
    )
    assert len(meetings) == 3
    ids = {m.meeting_id for m in meetings}
    assert len(ids) == 3, "每个轮次应得到独立的 meeting_id"

    # 验证时间错开 45 分钟
    starts = sorted(m.start_time for m in meetings if m.start_time)
    assert starts[1] - starts[0] == timedelta(minutes=45)
    assert starts[2] - starts[1] == timedelta(minutes=45)

    # 清理
    for m in meetings:
        await provider.cancel_meeting(m.meeting_id)


@pytest.mark.asyncio
async def test_get_recording_when_no_recording_yet(provider):
    """未录制时返回 status=processing, 不抛异常."""
    start = datetime.now(tz=timezone.utc) + timedelta(hours=4)
    meeting = await provider.create_meeting(
        topic="[Waibao Test] no-recording",
        start_time=start,
        duration_min=15,
        participants=[Participant(email=os.getenv("TEST_EMAIL_TO", "test@example.com"))],
    )
    try:
        rec = await provider.get_recording(meeting.meeting_id)
        # 没开始会议时返回 processing placeholder
        assert rec.meeting_id == meeting.meeting_id
        assert rec.status in ("processing", "available")
    finally:
        await provider.cancel_meeting(meeting.meeting_id)


@pytest.mark.asyncio
async def test_token_refresh_on_401(provider):
    """过期 token 触发自动刷新."""
    token1 = await provider._get_token()
    provider._token_expires_at = 0.0
    provider._token = None
    token2 = await provider._get_token()
    assert token2 != token1
    assert len(token2) > 20
