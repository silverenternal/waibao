"""Webhook 调度器 (T802).

职责:
    - 接收业务事件 → 查匹配订阅 → 异步投递
    - 失败重试 (指数退避,默认 3 次)
    - 全部失败进入死信 (内存级 + 可扩展到 Supabase)
    - 回调结果落到 DeliveryRecord (默认 in-memory,生产可注入 store)

默认 HTTP 客户端用 aiohttp (mock 模式下注入 _mock_transport).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .signer import SIGNATURE_HEADER, TIMESTAMP_HEADER, compute_signature
from .types import (
    DeliveryRecord,
    DeliveryStatus,
    WebhookConfig,
    WebhookEvent,
    WebhookPayload,
)
# v10.0 T5017 — SSRF guard (block private IP + post-DNS re-resolve check).
try:
    from services.security.ssrf import SSRFError, assert_safe_url
    _SSRF_AVAILABLE = True
except Exception:  # pragma: no cover — ssrf always importable; defensive only
    SSRFError = ValueError  # type: ignore[assignment,misc]
    assert_safe_url = None  # type: ignore[assignment]
    _SSRF_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transport: 抽象 HTTP 调用,默认实现用 aiohttp,测试可替换
# ---------------------------------------------------------------------------
TransportFn = Callable[[str, dict[str, str], bytes], Awaitable[tuple[int, str]]]


async def _default_transport(
    url: str, headers: dict[str, str], body: bytes
) -> tuple[int, str]:
    """默认 transport: 优先 aiohttp,缺包时退化到 httpx,再退化到 stub."""
    try:
        import aiohttp  # type: ignore

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(url, data=body, headers=headers) as r:
                text = await r.text()
                return r.status, text[:512]
    except ImportError:
        try:
            import httpx  # type: ignore

            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(url, content=body, headers=headers)
                return r.status_code, r.text[:512]
        except ImportError:
            logger.warning("webhook.no_http_library url=%s", url)
            return 0, "no-http-library"


@dataclass
class WebhookDispatcher:
    """Webhook 事件调度器.

    用法:
        dispatcher = WebhookDispatcher()
        dispatcher.register(WebhookConfig.new(...))
        await dispatcher.emit(WebhookPayload.make(WebhookEvent.TICKET_CREATED, ...))

    注入自定义 transport (测试 / 内部网关):
        dispatcher = WebhookDispatcher(transport=my_fn)
    """

    transport: TransportFn = field(default=_default_transport)
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    timeout_seconds: float = 10.0
    _configs: dict[str, WebhookConfig] = field(default_factory=dict)
    _records: list[DeliveryRecord] = field(default_factory=list)
    _dead_letter: list[DeliveryRecord] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Config 管理
    # ------------------------------------------------------------------
    def register(self, cfg: WebhookConfig) -> None:
        """Register a webhook config, rejecting SSRF-targeted URLs at the door.

        A tenant who can set an arbitrary callback URL must never be able to
        reach internal addresses (``169.254.169.254`` metadata, ``10.x``,
        ``127.x``).  We run the textual :func:`assert_safe_url` check here so
        the bad URL is refused before it is ever stored; :meth:`_deliver`
        re-runs the check (including DNS resolution) at fire time to defeat
        DNS-rebinding.
        """
        if _SSRF_AVAILABLE:
            try:
                assert_safe_url(cfg.url)
            except SSRFError as exc:
                logger.warning("webhook.register_blocked ssrf url=%s reason=%s", cfg.url, exc)
                raise
        self._configs[cfg.id] = cfg

    def unregister(self, config_id: str) -> bool:
        return self._configs.pop(config_id, None) is not None

    def list_configs(self, tenant_id: str | None = None) -> list[WebhookConfig]:
        return [
            c
            for c in self._configs.values()
            if tenant_id is None or c.tenant_id == tenant_id
        ]

    # ------------------------------------------------------------------
    # 事件发布
    # ------------------------------------------------------------------
    async def emit(self, payload: WebhookPayload) -> list[DeliveryRecord]:
        """发布事件,返回本次产生的全部 DeliveryRecord."""
        matched = self._match(payload)
        if not matched:
            return []
        tasks = [self._deliver(cfg, payload) for cfg in matched]
        return await asyncio.gather(*tasks)

    def _match(self, payload: WebhookPayload) -> list[WebhookConfig]:
        return [
            c
            for c in self._configs.values()
            if c.active
            and c.tenant_id == payload.tenant_id
            and payload.event in c.events
        ]

    # ------------------------------------------------------------------
    # 投递核心 (重试 + 死信)
    # ------------------------------------------------------------------
    async def _deliver(
        self, cfg: WebhookConfig, payload: WebhookPayload
    ) -> DeliveryRecord:
        import uuid
        from datetime import datetime, timezone

        record = DeliveryRecord(
            id=str(uuid.uuid4()),
            config_id=cfg.id,
            event=payload.event,
            url=cfg.url,
            status=DeliveryStatus.PENDING,
            attempt=0,
        )
        body = _json_dumps(payload.to_dict()).encode("utf-8")
        ts = datetime.now(tz=timezone.utc).isoformat()
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: compute_signature(cfg.secret, body),
            TIMESTAMP_HEADER: ts,
            "X-Waibao-Delivery": payload.delivery_id,
        }

        last_error = ""
        last_code: int | None = None
        for attempt in range(1, self.max_retries + 1):
            record.attempt = attempt
            record.last_attempt_at = datetime.now(tz=timezone.utc).isoformat()
            # v10.0 T5017 — re-verify the URL on EVERY attempt.  The host may
            # have been re-pointed at a private IP since registration (DNS
            # rebinding).  This is the canonical SSRF mitigation: validate
            # immediately before the outbound call.
            if _SSRF_AVAILABLE:
                try:
                    assert_safe_url(cfg.url)
                except SSRFError as exc:
                    last_error = f"ssrf_blocked: {exc}"
                    last_code = None
                    record.last_error = last_error
                    # SSRF is never retriable — dead-letter immediately.
                    break
            try:
                status_code, text = await self.transport(cfg.url, headers, body)
            except Exception as exc:  # 网络层异常
                last_error = f"transport: {exc!r}"
                last_code = None
                # 4xx 类特定错误可以立即死信(不浪费 retry 配额)
                if self._is_dead_letter(last_code, last_error):
                    break
            else:
                last_code = status_code
                last_error = text if status_code >= 400 else ""
                if 200 <= status_code < 300:
                    record.status = DeliveryStatus.SUCCESS
                    record.last_status_code = status_code
                    self._records.append(record)
                    logger.info(
                        "webhook.delivered config=%s event=%s status=%s",
                        cfg.id, payload.event.value, status_code,
                    )
                    return record
                # 4xx 永久失败,立即进死信
                if self._is_dead_letter(status_code, last_error):
                    break

            if attempt < self.max_retries:
                delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
                logger.warning(
                    "webhook.retry config=%s attempt=%s delay=%.1fs code=%s",
                    cfg.id, attempt, delay, last_code,
                )
                await asyncio.sleep(delay)

        # 重试耗尽后,统一进入死信队列 (T802 spec: 失败 3 次后入死信)
        record.status = (
            DeliveryStatus.FAILED_DEAD_LETTER
        )
        record.last_status_code = last_code
        record.last_error = last_error
        self._records.append(record)
        self._dead_letter.append(record)
        logger.error(
            "webhook.dead_letter config=%s event=%s code=%s",
            cfg.id, payload.event.value, last_code,
        )
        return record

    def _is_dead_letter(self, status_code: int | None, error: str) -> bool:
        # 4xx (除 408/425/429) 永久失败,直接进死信;否则可继续重试
        if status_code is None:
            return True
        if 400 <= status_code < 500 and status_code not in (408, 425, 429):
            return True
        return False

    # ------------------------------------------------------------------
    # 查询 (审计用)
    # ------------------------------------------------------------------
    def list_records(self, config_id: str | None = None) -> list[DeliveryRecord]:
        return [r for r in self._records if config_id is None or r.config_id == config_id]

    def list_dead_letters(self) -> list[DeliveryRecord]:
        return list(self._dead_letter)


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# 全局单例 (生产使用)
# ---------------------------------------------------------------------------
_global_dispatcher: WebhookDispatcher | None = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """获取全局 dispatcher (懒加载)."""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = WebhookDispatcher()
    return _global_dispatcher


def set_webhook_dispatcher(d: WebhookDispatcher) -> None:
    """注入自定义 dispatcher (测试 / 多租户隔离)."""
    global _global_dispatcher
    _global_dispatcher = d