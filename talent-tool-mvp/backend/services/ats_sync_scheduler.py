"""T1501 — ATS 同步定时调度器.

设计:
- 默认每 15 分钟拉一次 (PULL), push 频率可配
- 单进程 asyncio 任务, 注册到 FastAPI startup hook
- 使用全局 registry 实例, 避免跨事件循环泄漏
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class ATSSyncScheduler:
    """Asyncio 同步调度器."""

    def __init__(
        self,
        engine,                                # ATSSyncEngine
        integrations_loader: Callable[[], Coroutine[Any, Any, list[dict[str, Any]]]],
        provider_factory: Callable[[str, dict[str, Any]], Any],
        *,
        interval_seconds: float = 15 * 60,    # 15 分钟
        enabled: bool = True,
    ) -> None:
        self.engine = engine
        self._loader = integrations_loader
        self._factory = provider_factory
        self.interval = max(30, interval_seconds)
        self.enabled = enabled
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ats-sync-scheduler")
        logger.info("ats_sync_scheduler.started interval=%ss", self.interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        logger.info("ats_sync_scheduler.stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("ats_sync_scheduler.tick_failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        integrations = await self._loader()
        for integration in integrations:
            if not integration.get("active"):
                continue
            try:
                provider = self._factory(integration["provider"], integration)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "ats_sync.provider_init_failed integration=%s",
                    integration.get("id"),
                )
                continue
            since = None
            last = integration.get("last_synced_at")
            if isinstance(last, str):
                try:
                    since = datetime.fromisoformat(last)
                    if since.tzinfo is None:
                        since = since.replace(tzinfo=timezone.utc)
                except Exception:
                    since = None
            try:
                result = await self.engine.pull_candidates(
                    integration_id=str(integration["id"]),
                    provider=provider,
                    triggered_by="scheduler",
                    since=since,
                )
                if result.status == "ok":
                    await self.engine.pull_jobs(
                        integration_id=str(integration["id"]),
                        provider=provider,
                        triggered_by="scheduler",
                        since=since,
                    )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ats_sync.scheduler_sync_failed integration=%s",
                    integration.get("id"),
                )


__all__ = ["ATSSyncScheduler"]
