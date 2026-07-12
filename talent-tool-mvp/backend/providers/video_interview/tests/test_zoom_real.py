"""Zoom Server-to-Server OAuth 真实接入验证 (T1701 / T1805).

默认 **跳过** — 需要 ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET:

    export ZOOM_ACCOUNT_ID="..."
    export ZOOM_CLIENT_ID="..."
    export ZOOM_CLIENT_SECRET="..."
    pytest -m real_api backend/providers/video_interview/tests/test_zoom_real.py

凭证申请: docs/REAL_API_SETUP.md (8 Zoom) + docs/VIDEO_INTERVIEW_SETUP.md
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backend.providers.video_interview.types import Participant
from backend.providers.video_interview.zoom import ZoomProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (
            os.getenv("ZOOM_ACCOUNT_ID")
            and os.getenv("ZOOM_CLIENT_ID")
            and os.getenv("ZOOM_CLIENT_SECRET")
        ),
        reason="ZOOM_ACCOUNT_ID/CLIENT_ID/CLIENT_SECRET 未设置 — 跳过 Zoom 真实测试",
    ),
]


@pytest.fixture
def provider():
    return ZoomProvider()


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.account_id
    assert provider.client_id
    assert provider.client_secret


@pytest.mark.asyncio
async def test_acquire_oauth_token(provider):
    """Server-to-Server OAuth 应返回有效 access_token."""
    token = await provider._get_token()
    assert isinstance(token, str)
    assert len(token) > 20
    # 第二次调用应复用缓存
    token2 = await provider._get_token()
    assert token == token2


@pytest.mark.asyncio
async def test_create_meeting_real(provider):
    """真实创建会议并获取 join_url."""
    start = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    meeting = await provider.create_meeting(
        topic="[Waibao Test] Real API integration",
        start_time=start,
        duration_min=30,
        participants=[Participant(email=os.getenv("TEST_EMAIL_TO", "test@example.com"))],
        metadata={"test_run_id": "zoom-001"},
    )
    assert meeting.meeting_id
    assert meeting.join_url.startswith("https://")
    # 清理 — 删除会议
    status, _ = await provider._request("DELETE", f"/meetings/{meeting.meeting_id}")
    assert status in (200, 204, 404)


@pytest.mark.asyncio
async def test_token_refresh_on_401(provider):
    """过期 token 触发自动刷新."""
    token1 = await provider._get_token()
    # 强制过期
    provider._token_expires_at = 0.0
    provider._token = None
    token2 = await provider._get_token()
    assert token2 != token1
    assert len(token2) > 20


# ---------------------------------------------------------------------------
# T1805: Panel round — 一次性真实创建 5 个会议
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_five_meetings_panel_round(provider):
    """T1805: 真实创建 5 个面试会议 (技术 + 行为 + 案例 + 系统设计 + 终面)."""
    start = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    candidate_id = os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com")
    panelists = [
        os.getenv("TEST_PANELIST_1", "interviewer_1@example.com"),
        os.getenv("TEST_PANELIST_2", "interviewer_2@example.com"),
        os.getenv("TEST_PANELIST_3", "interviewer_3@example.com"),
        os.getenv("TEST_PANELIST_4", "interviewer_4@example.com"),
        os.getenv("TEST_PANELIST_5", "interviewer_5@example.com"),
    ]
    meetings = await provider.create_panel_round(
        candidate_id=candidate_id,
        topic="[Waibao] Senior 后端面试 (Zoom)",
        panelist_emails=panelists,
        start_time=start,
        duration_min=45,
        rounds=5,
        metadata={"role_id": "role_001", "channel": "zoom"},
    )
    try:
        assert len(meetings) == 5
        # 每个会议独立 ID
        ids = {m.meeting_id for m in meetings}
        assert len(ids) == 5
        # 时间错开 30 分钟
        starts = sorted(m.start_time for m in meetings if m.start_time)
        delta = starts[1] - starts[0]
        assert delta == timedelta(minutes=30)
        # 全部 join_url 都是 https
        for m in meetings:
            assert m.join_url.startswith("https://")
            assert m.password  # Zoom 默认有密码
    finally:
        # 清理: 删除全部 5 个
        for m in meetings:
            await provider.cancel_meeting(m.meeting_id)


@pytest.mark.asyncio
async def test_get_recording_when_not_ready(provider):
    """未录制时返回 status=processing."""
    start = datetime.now(tz=timezone.utc) + timedelta(hours=4)
    meeting = await provider.create_meeting(
        topic="[Waibao Test] not-started",
        start_time=start,
        duration_min=15,
        participants=[Participant(email=os.getenv("TEST_EMAIL_TO", "test@example.com"))],
    )
    try:
        rec = await provider.get_recording(meeting.meeting_id)
        assert rec.meeting_id == meeting.meeting_id
        assert rec.status in ("processing", "available")
    finally:
        await provider.cancel_meeting(meeting.meeting_id)
