"""SendGrid SMTP 真实邮件验证 (T1701).

默认 **跳过** — 需要 SMTP 凭证:

    export SMTP_HOST=smtp.sendgrid.net
    export SMTP_PORT=587
    export SMTP_USERNAME=apikey
    export SMTP_PASSWORD="SG.xxx..."
    export SMTP_FROM="noreply@yourdomain.com"
    export TEST_EMAIL_TO="you@yourdomain.com"   # 必填,不会发送给真实用户
    pytest -m real_api backend/providers/notify/tests/test_sendgrid_real.py

凭证申请: docs/REAL_API_SETUP.md (5 Notify)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.notify.base import NotifyMessage
from backend.providers.notify.smtp_provider import SMTPProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (os.getenv("SMTP_PASSWORD") and os.getenv("SMTP_FROM") and os.getenv("TEST_EMAIL_TO")),
        reason="SMTP_PASSWORD/SMTP_FROM/TEST_EMAIL_TO 未设置 — 跳过 SendGrid 真实测试",
    ),
]


@pytest.fixture
def provider():
    return SMTPProvider(use_tls=True)


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.host
    assert provider.from_addr


@pytest.mark.asyncio
async def test_send_real_email(provider):
    """真实发送邮件到 TEST_EMAIL_TO."""
    msg = NotifyMessage(
        subject="[Waibao Test] SMTP real-api integration",
        body="This is an automated test from Waibao v4.0 test_real_api suite.",
        to=[os.getenv("TEST_EMAIL_TO")],
        metadata={"test_run_id": "smtp-001"},
    )
    result = await provider.send(msg)
    assert result.success is True
    assert result.channel == "smtp"
    assert result.error is None