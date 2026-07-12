"""北森 (Beisen) client_credentials OAuth + 真实邀请/结果验证 (T1805).

默认 **跳过** — 需要以下环境变量:

    export BEISEN_APP_ID="..."
    export BEISEN_APP_SECRET="..."
    export BEISEN_TENANT_ID="..."  # 可选
    export BEISEN_ASSESSMENT_ID="..."  # 真实测评 id, 在控制台创建后填入
    pytest -m real_api backend/providers/assessment/tests/test_beisen_real.py

凭证申请: docs/ASSESSMENT_SETUP.md
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from backend.providers.assessment.beisen import BeisenProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (
            os.getenv("BEISEN_APP_ID")
            and os.getenv("BEISEN_APP_SECRET")
        ),
        reason="BEISEN_APP_ID/SECRET 未设置 — 跳过北森真实测试",
    ),
]


@pytest.fixture
def provider():
    return BeisenProvider()


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.app_id
    assert provider.app_secret


@pytest.mark.asyncio
async def test_acquire_oauth_token(provider):
    """client_credentials 模式 OAuth2 应返回 accessToken."""
    token = await provider._get_token()
    assert isinstance(token, str)
    assert len(token) > 20
    # 缓存命中
    token2 = await provider._get_token()
    assert token == token2


@pytest.mark.asyncio
async def test_send_invitation_real(provider):
    """真实创建一个测评邀请, 拿到 invite_url 给候选人."""
    assessment_id = os.getenv(
        "BEISEN_ASSESSMENT_ID",
        "demo_assessment_v1",
    )
    inv = await provider.send_invitation(
        candidate_id=os.getenv("TEST_CANDIDATE_ID", "cand_demo_001"),
        assessment_id=assessment_id,
        candidate_email=os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com"),
        candidate_name="Waibao Test Candidate",
        expires_in_hours=24,
        metadata={"channel": "t1805"},
    )
    assert inv.invitation_id
    assert inv.invite_url is not None
    assert inv.status == "pending"
    assert inv.expires_at is not None


@pytest.mark.asyncio
async def test_send_invitation_then_get_results(provider):
    """邀请发出后立刻拉结果: 通常是 pending,业务上需轮询."""
    assessment_id = os.getenv("BEISEN_ASSESSMENT_ID", "demo_assessment_v1")
    inv = await provider.send_invitation(
        candidate_id=os.getenv("TEST_CANDIDATE_ID", "cand_demo_002"),
        assessment_id=assessment_id,
        candidate_email=os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com"),
        candidate_name="Waibao Test Candidate",
        metadata={"scenario": "invite-then-poll"},
    )
    result = await provider.get_results(inv.invitation_id)
    # 北森约定: 没有结果的也算业务成功(errorCode=0),status 由具体值决定
    assert result.invitation_id == inv.invitation_id
    # status 应在 pending/submitted/scored/expired 之一
    assert result.status in ("pending", "submitted", "scored", "expired")


@pytest.mark.asyncio
async def test_get_results_unknown_invitation_returns_pending(provider):
    """未知 invitation: 应返回 pending placeholder 而不是抛异常."""
    fake_id = "inv_does_not_exist_xyz"
    result = await provider.get_results(fake_id)
    assert result.status == "pending"
    assert result.invitation_id == fake_id


@pytest.mark.asyncio
async def test_token_refresh_on_401(provider):
    """过期 token 触发自动刷新 + 重试."""
    token1 = await provider._get_token()
    provider._token_expires_at = 0.0
    provider._token = None
    token2 = await provider._get_token()
    assert token2 != token1
    assert len(token2) > 20
