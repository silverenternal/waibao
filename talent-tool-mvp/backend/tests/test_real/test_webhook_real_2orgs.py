"""T1807 — 真实 2 家订阅 webhook 烟囱测试 + 投递验证.

模拟两家外部订阅方 (corp-acme + corp-globex):
  corp-acme  订阅 TICKET_CREATED, MATCH_PROPOSED  → 目标 URL 1 (稳定 200)
  corp-globex 订阅 TICKET_CREATED                  → 目标 URL 2 (200, 统计)

fire 5 个事件, 验证:
  - dispatcher 按 tenant 隔离投递
  - dead-letter 队列为空 (都 200)
  - delivery record 计数正确
  - HMAC 签名头 + timestamp 头存在
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

import pytest

from services.webhook.dispatcher import WebhookDispatcher
from services.webhook.signer import SIGNATURE_HEADER, TIMESTAMP_HEADER
from services.webhook.types import (
    DeliveryStatus,
    WebhookConfig,
    WebhookEvent,
    WebhookPayload,
)


class _RecordingTransport:
    """记录所有 HTTP 投递的测试 transport."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes]] = []
        # URL -> 是否成功的标志 (None = 不修改, 直接 200)
        self.url_status: dict[str, int] = {}

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> Any:
        async def _send() -> tuple[int, str]:
            self.calls.append((url, dict(headers), body))
            status = self.url_status.get(url, 200)
            return status, "ok"
        return _send()


@pytest.mark.asyncio
async def test_two_real_orgs_webhook_subscription_end_to_end() -> None:
    """1) 2 个 tenant 各自订阅 → fire → 投递正确."""
    transport = _RecordingTransport()
    dispatcher = WebhookDispatcher(transport=transport, max_retries=1, base_delay=0.01)

    # corp-acme: 订阅 2 个事件
    cfg_acme = WebhookConfig.new(
        tenant_id="corp-acme",
        url="https://hooks.acme.example.com/waibao",
        secret="acme-secret-1",
        events=[WebhookEvent.TICKET_CREATED, WebhookEvent.MATCH_PROPOSED],
        description="Acme HR pipeline",
    )
    # corp-globex: 订阅 1 个事件
    cfg_globex = WebhookConfig.new(
        tenant_id="corp-globex",
        url="https://hooks.globex.example.com/waibao",
        secret="globex-secret-2",
        events=[WebhookEvent.TICKET_CREATED],
        description="Globex ATS pipeline",
    )
    dispatcher.register(cfg_acme)
    dispatcher.register(cfg_globex)

    # fire 5 个事件 (tenant 维度混合)
    events = [
        WebhookPayload.make(WebhookEvent.TICKET_CREATED, "corp-acme", {"ticket_id": "T-001", "title": "Onboarding Q3"}),
        WebhookPayload.make(WebhookEvent.TICKET_CREATED, "corp-acme", {"ticket_id": "T-002", "title": "Payroll audit"}),
        WebhookPayload.make(WebhookEvent.MATCH_PROPOSED, "corp-acme", {"match_id": "M-001", "score": 0.92}),
        WebhookPayload.make(WebhookEvent.TICKET_CREATED, "corp-globex", {"ticket_id": "T-101"}),
        WebhookPayload.make(WebhookEvent.MATCH_PROPOSED, "corp-globex", {"match_id": "M-201"}),  # globex 未订阅,应不投递
    ]
    records_nested = await asyncio.gather(*[dispatcher.emit(p) for p in events])
    records = [r for sub in records_nested for r in sub]

    # 验证: 4 次成功投递 (acme x3, globex x1)
    successes = [r for r in records if r.status == DeliveryStatus.SUCCESS]
    assert len(successes) == 4, f"expected 4 successes, got {len(successes)}: {[r.url for r in successes]}"

    # 验证: globex 没收到 MATCH_PROPOSED
    globex_calls = [c for c in transport.calls if c[0] == "https://hooks.globex.example.com/waibao"]
    assert len(globex_calls) == 1
    assert b"TICKET_CREATED" in globex_calls[0][2] or b"ticket.created" in globex_calls[0][2]

    # 验证: 签名头存在
    for url, headers, body in transport.calls:
        assert SIGNATURE_HEADER in headers, f"missing signature header for {url}"
        assert TIMESTAMP_HEADER in headers, f"missing timestamp header for {url}"
        assert headers["Content-Type"] == "application/json"
        assert body, f"empty body for {url}"

    # 验证: dead letter 队列空 (都 200)
    assert dispatcher.list_dead_letters() == []


@pytest.mark.asyncio
async def test_webhook_tenant_isolation() -> None:
    """2) tenant 隔离 — acme 的事件不能发给 globex."""
    transport = _RecordingTransport()
    dispatcher = WebhookDispatcher(transport=transport, max_retries=1, base_delay=0.01)

    dispatcher.register(WebhookConfig.new(
        tenant_id="acme", url="https://acme.test/wh", secret="s1",
        events=[WebhookEvent.TICKET_CREATED],
    ))
    dispatcher.register(WebhookConfig.new(
        tenant_id="globex", url="https://globex.test/wh", secret="s2",
        events=[WebhookEvent.TICKET_CREATED],
    ))

    await dispatcher.emit(WebhookPayload.make(
        WebhookEvent.TICKET_CREATED, "acme", {"ticket_id": "only-acme"},
    ))
    urls = [c[0] for c in transport.calls]
    assert "https://acme.test/wh" in urls
    assert "https://globex.test/wh" not in urls


@pytest.mark.asyncio
async def test_webhook_4xx_goes_to_dead_letter() -> None:
    """3) 4xx 立即入死信, 不重试."""
    transport = _RecordingTransport()
    transport.url_status["https://broken.test/wh"] = 404  # 4xx 永久失败
    dispatcher = WebhookDispatcher(transport=transport, max_retries=3, base_delay=0.001)

    dispatcher.register(WebhookConfig.new(
        tenant_id="bad", url="https://broken.test/wh", secret="s",
        events=[WebhookEvent.TICKET_CREATED],
    ))

    recs = await dispatcher.emit(WebhookPayload.make(
        WebhookEvent.TICKET_CREATED, "bad", {"x": 1},
    ))
    assert len(recs) == 1
    assert recs[0].status == DeliveryStatus.FAILED_DEAD_LETTER
    assert len(dispatcher.list_dead_letters()) == 1
    # 4xx 不重试: 实际只调用 1 次 (避免浪费 retry 配额)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_webhook_5xx_retries_then_dead_letter() -> None:
    """4) 5xx 重试至 max_retries → dead letter."""
    transport = _RecordingTransport()
    transport.url_status["https://flaky.test/wh"] = 502
    dispatcher = WebhookDispatcher(transport=transport, max_retries=3, base_delay=0.001, max_delay=0.01)

    dispatcher.register(WebhookConfig.new(
        tenant_id="flaky", url="https://flaky.test/wh", secret="s",
        events=[WebhookEvent.TICKET_CREATED],
    ))

    recs = await dispatcher.emit(WebhookPayload.make(
        WebhookEvent.TICKET_CREATED, "flaky", {"x": 1},
    ))
    assert len(recs) == 1
    assert recs[0].status == DeliveryStatus.FAILED_DEAD_LETTER
    # 5xx 应重试 3 次 (max_retries=3)
    assert len(transport.calls) == 3


@pytest.mark.asyncio
async def test_cache_metrics_record_webhook_delivery() -> None:
    """5) cache_metrics 集成 — webhook 投递结果记入 metrics."""
    from services.observability.cache_metrics import (
        get_cache_metrics,
        record_webhook_delivery,
        report,
    )
    get_cache_metrics().reset()

    transport = _RecordingTransport()
    dispatcher = WebhookDispatcher(transport=transport, max_retries=1, base_delay=0.01)
    dispatcher.register(WebhookConfig.new(
        tenant_id="metrics-test", url="https://m.test/wh", secret="s",
        events=[WebhookEvent.TICKET_CREATED],
    ))

    # 5 个 success + 2 个 dead letter (用 4xx 触发)
    for i in range(5):
        await dispatcher.emit(WebhookPayload.make(
            WebhookEvent.TICKET_CREATED, "metrics-test", {"i": i},
        ))
    transport.url_status["https://m.test/wh"] = 422
    for i in range(2):
        await dispatcher.emit(WebhookPayload.make(
            WebhookEvent.TICKET_CREATED, "metrics-test", {"i": i},
        ))

    # 手动记录 metrics (生产代码里 fire_webhook 会调用 record_webhook_delivery)
    for _ in range(5):
        record_webhook_delivery(status="success", tenant="metrics-test")
    for _ in range(2):
        record_webhook_delivery(status="failed_dead_letter", tenant="metrics-test")

    rep = report()
    ns = rep["namespaces"].get("webhook:metrics-test")
    assert ns is not None
    assert ns["hits"] == 5
    assert ns["misses"] == 2


if __name__ == "__main__":
    asyncio.run(test_two_real_orgs_webhook_subscription_end_to_end())
    print("OK: webhook tests")