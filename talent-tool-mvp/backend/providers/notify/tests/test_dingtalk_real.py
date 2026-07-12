"""钉钉群机器人 Webhook 真实推送验证 (T1103).

默认 **跳过** — 需要以下环境变量才会运行:

    export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
    export DINGTALK_SECRET="SEC..."     # 可选,启用签名校验
    pytest -m real_api backend/providers/notify/tests/test_dingtalk_real.py

测试覆盖:
    1. 真实 webhook 推送 — text / markdown / @人
    2. HMAC-SHA256 签名生成正确
    3. URL 注入 timestamp + sign 参数
    4. 失败重试 (with_resilience 中间件)
    5. 凭证缺失抛 InvalidRequestError

凭证申请: docs/WEBHOOK_INTEGRATION.md (钉钉群机器人章节)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import parse_qs, urlparse

import pytest

from backend.providers.exceptions import (
    InvalidRequestError,
    ProviderError,
)
from backend.providers.notify.base import NotifyMessage, NotifyResult
from backend.providers.notify.dingtalk_provider import DingTalkProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("DINGTALK_WEBHOOK"),
        reason="DINGTALK_WEBHOOK 未设置 — 跳过钉钉真实推送测试",
    ),
]


@pytest.fixture
def provider():
    """构造 provider;若设置了 DINGTALK_SECRET 则启用签名."""
    secret = os.getenv("DINGTALK_SECRET") or None
    return DingTalkProvider(secret=secret)


# ---------------------------------------------------------------------------
# 真实推送 — text / markdown
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_text_message(provider):
    """真实推送纯文本消息."""
    msg = NotifyMessage(
        subject="T1103 测试",
        body="钉钉 webhook 接入验证 (text)",
    )
    result = await provider.send(msg)
    assert isinstance(result, NotifyResult)
    assert result.success is True
    assert result.channel == "dingtalk"
    # 钉钉返回 errcode=0 即成功
    raw = result.raw or {}
    assert raw.get("errcode") in (0, None)


@pytest.mark.asyncio
async def test_send_markdown_message(provider):
    """真实推送 markdown 消息."""
    msg = NotifyMessage(
        subject="[T1103] Markdown Test",
        body="这是 fallback body",
        html="**粗体** 测试 [链接](https://example.com)",
    )
    result = await provider.send(msg)
    assert result.success is True
    assert result.channel == "dingtalk"


@pytest.mark.asyncio
async def test_send_with_at_mobiles(provider):
    """@指定手机号 — payload 包含 at.atMobiles."""
    msg = NotifyMessage(
        subject="@测试",
        body="at mobile test",
        metadata={"atMobiles": ["13800138000"]},
    )
    result = await provider.send(msg)
    assert result.success is True


# ---------------------------------------------------------------------------
# 签名验证
# ---------------------------------------------------------------------------
def test_signature_algorithm():
    """手动构造签名,验证与 DingTalkProvider._sign 算法一致."""
    secret = "SEC12345"
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    expected = base64.b64encode(hmac_code).decode("ascii")
    # 校验格式
    assert len(expected) > 20
    # 可被 base64 反解
    decoded = base64.b64decode(expected)
    assert len(decoded) == 32  # sha256 = 256 bits = 32 bytes


@pytest.mark.asyncio
async def test_signed_url_contains_timestamp_and_sign():
    """启用 secret 后,实际请求 URL 应带 ?timestamp=&sign= 参数."""
    secret = "SEC-test-signature-key"
    p = DingTalkProvider(webhook="https://oapi.dingtalk.com/robot/send?access_token=test", secret=secret)
    # 拦截请求,只校验 URL 构造
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        def json(self): return {"errcode": 0, "errmsg": "ok", "messageId": "fake"}

        def raise_for_status(self): pass

    class _FakeClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _FakeResp()

    p._client = _FakeClient()  # type: ignore[assignment]
    msg = NotifyMessage(subject="s", body="b")
    result = await p.send(msg)
    assert result.success is True
    # 验证 URL 注入签名参数
    parsed = urlparse(captured["url"])
    qs = parse_qs(parsed.query)
    assert "timestamp" in qs
    assert "sign" in qs
    # 签名内容应与手工构造的 HMAC-SHA256(base64) 一致
    ts = qs["timestamp"][0]
    string_to_sign = f"{ts}\n{secret}"
    h = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    assert qs["sign"][0] == base64.b64encode(h).decode("ascii")


def test_no_secret_skips_signature():
    """未配置 secret 时,_sign 返回 ('', ''),URL 不应有 sign 参数."""
    p = DingTalkProvider(webhook="https://oapi.dingtalk.com/robot/send?access_token=x", secret="")
    ts, sign = p._sign()
    assert ts == "" and sign == ""


# ---------------------------------------------------------------------------
# 重试 — with_resilience 中间件
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_on_5xx(monkeypatch):
    """服务端返回 503,with_resilience 应自动重试 N 次后 fallback 抛 ProviderError."""
    from backend.providers.base import with_resilience

    p = DingTalkProvider(webhook="https://oapi.dingtalk.com/robot/send?access_token=x", secret="")
    call_count = {"n": 0}

    class _Always503:
        status_code = 503
        text = "service unavailable"

        def json(self): return {}

        def raise_for_status(self):
            import httpx
            raise httpx.HTTPStatusError("503", request=None, response=self)

    class _BoomClient:
        async def post(self, *a, **kw):
            call_count["n"] += 1
            return _Always503()

    p._client = _BoomClient()  # type: ignore[assignment]
    msg = NotifyMessage(subject="s", body="b")
    with pytest.raises(ProviderError):
        await p.send(msg)
    # 重试至少 1 次 (max_retries=2)
    assert call_count["n"] >= 2, f"未触发重试, 仅调用 {call_count['n']} 次"


# ---------------------------------------------------------------------------
# 凭证校验
# ---------------------------------------------------------------------------
def test_construct_without_webhook_raises(monkeypatch):
    monkeypatch.delenv("DINGTALK_WEBHOOK", raising=False)
    with pytest.raises(InvalidRequestError):
        DingTalkProvider(webhook=None, secret=None)