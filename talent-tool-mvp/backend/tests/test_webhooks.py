"""Webhook 子系统测试 (T802).

覆盖:
  - HMAC 签名计算 + 校验
  - 重试 3 次 → 进死信
  - dispatcher emit
  - fire_webhook 自定义 transport
  - 死信手动重发
  - URL 必须 https (Pydantic 校验)

不用真实 supabase / 真实网络.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock

from services.webhook import (
    WebhookDispatcher,
    WebhookEvent,
    WebhookPayload,
    fire_webhook,
    get_webhook_dispatcher,
)
from services.webhook.dispatcher import set_webhook_dispatcher
from services.webhook.signer import (
    SIGNATURE_PREFIX,
    TIMESTAMP_HEADER,
    SignatureError,
    compute_signature,
    generate_secret,
    verify_signature,
)
from services.webhook.types import (
    DeliveryRecord,
    DeliveryStatus,
    WebhookConfig,
)


# ---------------------------------------------------------------------------
# Signer
# ---------------------------------------------------------------------------


def test_compute_signature_format():
    sig = compute_signature("abc", b"hello")
    assert sig.startswith(SIGNATURE_PREFIX)
    # sha256 hex -> 64 chars after prefix
    assert len(sig) == len(SIGNATURE_PREFIX) + 64


def test_verify_signature_roundtrip():
    secret = "topsecret"
    body = b'{"hello":"world"}'
    sig = compute_signature(secret, body)
    assert verify_signature(secret, body, sig) is True


def test_verify_signature_tamper_rejected():
    secret = "topsecret"
    body = b'{"hello":"world"}'
    sig = compute_signature(secret, body)
    assert verify_signature(secret, body + b"x", sig) is False


def test_verify_signature_wrong_prefix_raises():
    with pytest.raises(SignatureError):
        verify_signature("s", b"x", "nosha256=deadbeef")


def test_verify_signature_missing_raises():
    with pytest.raises(SignatureError):
        verify_signature("s", b"x", None)


def test_generate_secret_unique():
    s1 = generate_secret(8)
    s2 = generate_secret(8)
    assert s1 != s2
    assert len(s1) == 16  # hex(nbytes=8) -> 16 chars


# ---------------------------------------------------------------------------
# Dispatcher — retry + dead letter
# ---------------------------------------------------------------------------


def _payload(event: str = "ticket.created") -> WebhookPayload:
    return WebhookPayload.make(
        event=WebhookEvent(event),
        tenant_id="org-1",
        data={"id": 1},
    )


@pytest.mark.asyncio
async def test_dispatcher_success_first_try():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.TICKET_CREATED],
    )
    called = []

    async def transport(url, headers, body):
        called.append((url, dict(headers), body))
        return 200, "ok"

    d = WebhookDispatcher(transport=transport, max_retries=3, base_delay=0.01)
    d.register(cfg)
    recs = await d.emit(_payload())
    assert len(recs) == 1
    assert recs[0].status == DeliveryStatus.SUCCESS
    assert recs[0].attempt == 1
    assert len(called) == 1
    # signature header present
    assert any("signature" in k.lower() for k in called[0][1].keys())


@pytest.mark.asyncio
async def test_dispatcher_retry_then_dead_letter_4xx():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.TICKET_CREATED],
    )
    calls = []

    async def transport(url, headers, body):
        calls.append(1)
        return 404, "not found"  # 4xx -> immediate dead-letter

    d = WebhookDispatcher(transport=transport, max_retries=3, base_delay=0.01)
    d.register(cfg)
    recs = await d.emit(_payload())
    assert recs[0].status == DeliveryStatus.FAILED_DEAD_LETTER
    # 4xx (非 408/425/429) 不再重试
    assert len(calls) == 1
    assert d.list_dead_letters()[0].id == recs[0].id


@pytest.mark.asyncio
async def test_dispatcher_retries_3_times_then_dead_letter_5xx():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.MATCH_PROPOSED],
    )
    calls = []

    async def transport(url, headers, body):
        calls.append(1)
        return 503, "service unavailable"  # 5xx -> retry-able

    d = WebhookDispatcher(
        transport=transport, max_retries=3, base_delay=0.01, max_delay=0.02
    )
    d.register(cfg)
    recs = await d.emit(_payload("match.proposed"))
    assert recs[0].status == DeliveryStatus.FAILED_DEAD_LETTER
    assert len(calls) == 3  # exactly 3 attempts
    assert recs[0].attempt == 3


@pytest.mark.asyncio
async def test_dispatcher_retries_then_succeeds():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.TICKET_CREATED],
    )
    calls = {"n": 0}

    async def transport(url, headers, body):
        calls["n"] += 1
        if calls["n"] < 2:
            return 502, "bad gateway"
        return 200, "ok"

    d = WebhookDispatcher(
        transport=transport, max_retries=3, base_delay=0.01, max_delay=0.02
    )
    d.register(cfg)
    recs = await d.emit(_payload())
    assert recs[0].status == DeliveryStatus.SUCCESS
    assert recs[0].attempt == 2
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_dispatcher_no_match_skipped():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.JD_OVERSPEC_WARNING],
    )
    async def transport(*a, **kw):
        raise AssertionError("transport shouldn't be called")

    d = WebhookDispatcher(transport=transport)
    d.register(cfg)
    recs = await d.emit(_payload("ticket.created"))
    assert recs == []


@pytest.mark.asyncio
async def test_dispatcher_signature_header_format():
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="topsecret",
        events=[WebhookEvent.TICKET_CREATED],
    )

    seen = {}

    async def transport(url, headers, body):
        seen["headers"] = dict(headers)
        seen["body"] = body
        return 200, "ok"

    d = WebhookDispatcher(transport=transport, max_retries=1)
    d.register(cfg)
    await d.emit(_payload())
    sig = seen["headers"]["X-Waibao-Signature"]
    ts = seen["headers"]["X-Waibao-Timestamp"]
    assert sig.startswith(SIGNATURE_PREFIX)
    assert "T" in ts  # ISO8601
    # Verify the body
    expected_sig = compute_signature("topsecret", seen["body"])
    assert expected_sig == sig


# ---------------------------------------------------------------------------
# Fire helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_webhook_returns_records():
    # Direct fire without supabase (no hydration)
    transport = AsyncMock(return_value=(200, "ok"))

    set_webhook_dispatcher(WebhookDispatcher(transport=transport, max_retries=1))

    cfg = WebhookConfig.new(
        tenant_id="org-fire",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.EMOTION_RISK],
    )
    get_webhook_dispatcher().register(cfg)

    records = await fire_webhook(
        WebhookEvent.EMOTION_RISK,
        "org-fire",
        {"user_id": "u1", "level": "high"},
    )
    assert len(records) == 1
    assert records[0].status == DeliveryStatus.SUCCESS
    transport.assert_awaited()


# ---------------------------------------------------------------------------
# URL HTTPS validation (Pydantic model)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_url_must_be_https():
    """API 层强制 HTTPS — 测试 Pydantic 校验."""
    # 模拟 api.webhooks.WebhookUpsert 的校验
    from pydantic import ValidationError
    # 由于不能直接跨模块,我们这里 import 该类
    try:
        from api.webhooks import WebhookUpsert
    except Exception:
        pytest.skip("api.webhooks not importable in test env")
    with pytest.raises(ValidationError):
        WebhookUpsert(
            name="t",
            url="http://insecure.example/hook",
            events=["ticket.created"],
        )
    # https 应该通过
    ok = WebhookUpsert(
        name="t",
        url="https://example.com/hook",
        events=["ticket.created"],
    )
    assert ok.url.startswith("https://")


# ---------------------------------------------------------------------------
# Dead letter manual replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_letter_replay_dispatcher_path():
    """replay 路径: dispatcher 在 worker 视角重新 emit 一次成功."""
    cfg = WebhookConfig.new(
        tenant_id="org-1",
        url="https://example.com/hook",
        secret="k",
        events=[WebhookEvent.TICKET_CREATED],
    )
    calls = {"n": 0}

    async def transport(url, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            return 503, "down"
        if calls["n"] == 2:
            return 500, "still down"
        return 200, "recovered"

    d = WebhookDispatcher(
        transport=transport, max_retries=2, base_delay=0.01, max_delay=0.02
    )
    d.register(cfg)

    # 首次:2 次 5xx 后达到 retry 上限 → dead_letter
    recs1 = await d.emit(_payload())
    assert recs1[0].status == DeliveryStatus.FAILED_DEAD_LETTER
    assert recs1[0].attempt == 2

    # replay — 重新 emit,transport 第 3 次恢复
    recs2 = await d.emit(_payload())
    assert recs2[0].status == DeliveryStatus.SUCCESS
    assert calls["n"] == 3
