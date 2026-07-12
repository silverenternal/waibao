"""Checkr Basic Auth + 真实背调发起 + Webhook 验证 (T1805).

默认 **跳过** — 需要以下环境变量:

    export CHECKR_API_KEY="acct_..."                    # 生产/staging api key
    export CHECKR_WEBHOOK_SECRET="whsec_..."           # 可选, 用于 webhook 签名校验
    export TEST_CANDIDATE_EMAIL="candidate@example.com" # 可选
    pytest -m real_api backend/providers/background_check/tests/test_checkr_real.py

凭证申请: docs/BACKGROUND_CHECK_SETUP.md

注意: Checkr 测试桩账户(sandbox + 真账户)都能跑这个测试集,
但 **发起的是真报告**,需要为每个候选人付钱。
请控制测试频率; 或使用 Checkr 的 sandbox 区域 (api.checkr-staging.com).
"""
from __future__ import annotations

import json
import os
import time

import pytest

from backend.providers.background_check.checkr import (
    CheckrProvider,
    CheckrWebhookVerifier,
    handle_webhook_event,
    parse_webhook_event,
)
from backend.providers.background_check.types import CheckType


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("CHECKR_API_KEY"),
        reason="CHECKR_API_KEY 未设置 — 跳过 Checkr 真实测试",
    ),
]


@pytest.fixture
def provider():
    return CheckrProvider()


# ---------------------------------------------------------------------------
# Real API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.api_key


@pytest.mark.asyncio
async def test_basic_auth_header_format(provider):
    auth = provider._auth_header()
    assert auth.startswith("Basic ")
    # 解码回来必须是 api_key + ':'
    import base64 as _b64

    decoded = _b64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
    assert decoded.endswith(":")
    assert decoded[:-1] == provider.api_key


@pytest.mark.asyncio
async def test_initiate_check_real(provider):
    """真实发起背景调查 → 创建候选人 + 创报告."""
    check = await provider.initiate_check(
        candidate_id=os.getenv("TEST_CANDIDATE_ID", "cand_checkr_real_001"),
        check_types=[
            CheckType(code="criminal", required=True),
            CheckType(code="employment", required=True),
        ],
        candidate_email=os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com"),
        candidate_name="Waibao Test",
        metadata={"triggered_by": "t1805", "scenario": "real-api"},
    )
    assert check.check_id
    assert check.status == "pending"
    assert set(check.check_types) == {"criminal", "employment"}
    assert check.report_url is not None


@pytest.mark.asyncio
async def test_get_status_real(provider):
    """发起后立刻查 status: 应该 clear / pending / in_progress 之一."""
    check = await provider.initiate_check(
        candidate_id=os.getenv("TEST_CANDIDATE_ID", "cand_checkr_real_002"),
        check_types=[CheckType(code="criminal", required=True)],
        candidate_email=os.getenv("TEST_CANDIDATE_EMAIL", "candidate@example.com"),
        candidate_name="Waibao Test",
    )
    status = await provider.get_status(check.check_id)
    assert status.check_id == check.check_id
    assert status.status in ("pending", "in_progress", "clear", "consider")
    # 至少应该有 progress_pct
    assert 0.0 <= status.progress_pct <= 100.0


# ---------------------------------------------------------------------------
# Webhook verifier — 不需要真实报告, 跑单元测试覆盖签名/解析
# ---------------------------------------------------------------------------


def test_webhook_verifier_accepts_valid_signature():
    """有效签名 + 当前 timestamp → 验证通过."""
    secret = "whsec_testsecret123"
    verifier = CheckrWebhookVerifier(secret=secret)
    body = json.dumps({"type": "report.completed", "data": {"id": "rep_abc"}}).encode()
    headers = verifier.sign_test_payload(body)
    ok, reason = verifier.verify(
        raw_body=body,
        signature=headers["signature"],
        timestamp=headers["timestamp"],
    )
    assert ok
    assert reason == "ok"


def test_webhook_verifier_rejects_bad_signature():
    verifier = CheckrWebhookVerifier(secret="whsec_testsecret123")
    body = json.dumps({"type": "report.updated"}).encode()
    ok, reason = verifier.verify(
        raw_body=body,
        signature="0" * 64,
        timestamp=str(int(time.time())),
    )
    assert not ok
    assert "signature" in reason or "mismatch" in reason


def test_webhook_verifier_rejects_expired_timestamp():
    verifier = CheckrWebhookVerifier(secret="whsec_x", tolerance_sec=60)
    body = b"{}"
    headers = verifier.sign_test_payload(body, timestamp=int(time.time()) - 7200)
    ok, reason = verifier.verify(
        raw_body=body,
        signature=headers["signature"],
        timestamp=headers["timestamp"],
    )
    assert not ok
    assert "timestamp" in reason


def test_webhook_verifier_skip_when_no_secret():
    """dev mode: 不配置 secret 时跳过校验, 用于本地 mock webhook."""
    verifier = CheckrWebhookVerifier(secret=None)
    ok, reason = verifier.verify(raw_body=b"{}", signature="anything", timestamp="0")
    assert ok
    assert reason == "no-secret-skip"


def test_parse_webhook_event_normalizes():
    body = json.dumps({
        "type": "report.completed",
        "data": {
            "id": "rep_abc",
            "status": "clear",
            "candidate_id": "can_xyz",
            "report_url": "https://dashboard.checkr.com/reports/rep_abc",
        },
    }).encode()
    evt = parse_webhook_event(body)
    assert evt["type"] == "report.completed"
    assert evt["object_id"] == "rep_abc"
    assert evt["status"] == "clear"
    assert evt["candidate_id"] == "can_xyz"


def test_handle_webhook_event_to_business_status():
    body = json.dumps({
        "type": "report.completed",
        "data": {"id": "rep_q", "status": "consider", "candidate_id": "can_z"},
    }).encode()
    evt = parse_webhook_event(body)
    out = handle_webhook_event(evt)
    assert out["check_id"] == "rep_q"
    assert out["status"] == "consider"
    assert out["action"] == "completed"


def test_handle_webhook_event_invokes_callback():
    captured = []

    def cb(check_id, status, progress, raw):
        captured.append((check_id, status, progress))

    body = json.dumps({
        "type": "report.updated",
        "data": {"id": "rep_c", "status": "in_progress"},
    }).encode()
    evt = parse_webhook_event(body)
    out = handle_webhook_event(evt, on_status_update=cb)
    assert out["status"] == "in_progress"
    assert captured == [("rep_c", "in_progress", 50.0)]
