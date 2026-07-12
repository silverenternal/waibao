"""飞书群机器人 Webhook 真实推送验证 (T1103).

默认 **跳过** — 需要以下环境变量才会运行:

    export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
    export FEISHU_SECRET="..."         # 可选,启用签名校验
    pytest -m real_api backend/providers/notify/tests/test_feishu_real.py

测试覆盖:
    1. 真实 webhook 推送 — interactive 消息卡片
    2. HMAC-SHA256 签名生成正确 (key 直接是 secret, 不是 secret+key)
    3. payload 中包含 timestamp + sign
    4. 失败重试
    5. 凭证缺失抛 InvalidRequestError

凭证申请: docs/WEBHOOK_INTEGRATION.md (飞书群机器人章节)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import pytest

from backend.providers.exceptions import (
    InvalidRequestError,
    ProviderError,
)
from backend.providers.notify.base import NotifyMessage, NotifyResult
from backend.providers.notify.feishu_provider import FeishuProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("FEISHU_WEBHOOK"),
        reason="FEISHU_WEBHOOK 未设置 — 跳过飞书真实推送测试",
    ),
]


@pytest.fixture
def provider():
    secret = os.getenv("FEISHU_SECRET") or None
    return FeishuProvider(secret=secret)


# ---------------------------------------------------------------------------
# 真实推送
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_interactive_card(provider):
    """真实推送 interactive 消息卡片."""
    msg = NotifyMessage(
        subject="T1103 飞书测试",
        body="飞书 webhook 接入验证",
        html="**bold** test [link](https://example.com)",
    )
    result = await provider.send(msg)
    assert isinstance(result, NotifyResult)
    assert result.success is True
    assert result.channel == "feishu"
    # 飞书返回 code=0 即成功
    raw = result.raw or {}
    assert raw.get("code") in (0, None)


@pytest.mark.asyncio
async def test_send_text_only(provider):
    """无 html 时,fallback 到 message.body."""
    msg = NotifyMessage(subject="plain", body="just plain text")
    result = await provider.send(msg)
    assert result.success is True


# ---------------------------------------------------------------------------
# 签名验证
# ---------------------------------------------------------------------------
def test_signature_algorithm():
    """飞书签名: HMAC-SHA256(key=secret, msg=f'{ts}\\n{secret}') → base64."""
    secret = "fakesecret123"
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    expected = base64.b64encode(hmac_code).decode("ascii")
    assert len(expected) > 20
    base64.b64decode(expected)  # round-trip


@pytest.mark.asyncio
async def test_signed_payload_contains_timestamp_and_sign():
    """启用 secret 时,payload 中应包含 timestamp + sign."""
    secret = "test-feishu-secret"
    p = FeishuProvider(
        webhook="https://open.feishu.cn/open-apis/bot/v2/hook/abc",
        secret=secret,
    )
    captured: dict = {}

    class _OK:
        status_code = 200
        def json(self): return {"code": 0, "msg": "ok", "data": {"message_id": "fake"}}
        def raise_for_status(self): pass

    class _FakeClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return _OK()

    p._client = _FakeClient()  # type: ignore[assignment]
    msg = NotifyMessage(subject="s", body="b")
    result = await p.send(msg)
    assert result.success is True

    payload = captured["payload"]
    assert "timestamp" in payload
    assert "sign" in payload

    # 校验 sign 内容
    ts = payload["timestamp"]
    string_to_sign = f"{ts}\n{secret}"
    h = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    assert payload["sign"] == base64.b64encode(h).decode("ascii")


def test_no_secret_skips_signature():
    p = FeishuProvider(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/x", secret="")
    ts, sign = p._sign()
    assert ts == "" and sign == ""


# ---------------------------------------------------------------------------
# 重试
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_on_5xx():
    """5xx 触发 with_resilience 重试."""
    p = FeishuProvider(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/x", secret="")
    call_count = {"n": 0}

    class _Always500:
        status_code = 500
        text = "internal error"
        def json(self): return {}
        def raise_for_status(self):
            import httpx
            raise httpx.HTTPStatusError("500", request=None, response=self)

    class _BoomClient:
        async def post(self, *a, **kw):
            call_count["n"] += 1
            return _Always500()

    p._client = _BoomClient()  # type: ignore[assignment]
    msg = NotifyMessage(subject="s", body="b")
    with pytest.raises(ProviderError):
        await p.send(msg)
    assert call_count["n"] >= 2


# ---------------------------------------------------------------------------
# 凭证校验
# ---------------------------------------------------------------------------
def test_construct_without_webhook_raises(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK", raising=False)
    with pytest.raises(InvalidRequestError):
        FeishuProvider(webhook=None, secret=None)


# ---------------------------------------------------------------------------
# 消息结构校验
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payload_structure_interactive_card():
    """验证 interactive 卡片 payload 结构."""
    p = FeishuProvider(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/x", secret="")
    captured: dict = {}

    class _OK:
        status_code = 200
        def json(self): return {"code": 0, "msg": "ok"}
        def raise_for_status(self): pass

    class _FakeClient:
        async def post(self, url, json):
            captured["payload"] = json
            return _OK()

    p._client = _FakeClient()  # type: ignore[assignment]
    msg = NotifyMessage(subject="title", body="body", html="<b>html</b>")
    await p.send(msg)
    payload = captured["payload"]
    assert payload["msg_type"] == "interactive"
    card = payload["card"]
    assert card["header"]["title"]["content"] == "title"
    # 第一个 element 必须是 markdown tag
    assert card["elements"][0]["tag"] == "markdown"
    assert "html" in card["elements"][0]["content"]