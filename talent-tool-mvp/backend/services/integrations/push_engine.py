"""Push Engine — T1304 + T1804 实时推送引擎.

复用 v3.0 ``services.notify.dispatcher.NotifyDispatcher`` 多通道推送;
当 ``job_subscription.match_all_subscriptions`` 命中职位时,逐条推送
"新匹配职位"通知给对应候选人。

主要入口:
- ``PushEngine.on_new_job(job_posting)`` — 新职位入库后调用,触发推送.
- ``PushEngine.broadcast_existing()`` — 启动时或定时任务调用,
  对所有 enabled 订阅跑一次匹配,补推历史匹配.
- T1804 新增:
    - ``bulk_seed_subscriptions()`` — 从 seed JSONL 灌入订阅
    - ``push_with_retry()`` — 失败指数退避重试 (1s, 3s, 9s)
    - ``realtime_match_and_push()`` — 新 job 进来后 0 延迟推送
    - ``push_stats()`` — 实时推送统计 (for /api/push/stats)

所有失败被吞掉(推送失败不应阻塞主业务),但有 logger 记录.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Optional

from services.job_subscription import (
    JobPosting,
    JobSubscriptionService,
    Subscription,
    SubscriptionCriteria,
)
from services.notify.dispatcher import (
    DispatchOutcome,
    NotifyDispatcher,
    get_dispatcher,
)

logger = logging.getLogger("recruittech.services.push_engine")


@dataclass(slots=True)
class PushRecord:
    subscription_id: str
    user_id: str
    channels: list[str]
    matches: list[JobPosting]
    outcome: Optional[DispatchOutcome] = None
    success: bool = False
    error: str | None = None
    attempts: int = 1  # T1804 — retry count
    duration_ms: int = 0  # T1804 — push latency


@dataclass(slots=True)
class PushStats:
    """T1804 — 推送引擎实时统计."""
    total_pushed: int = 0
    success: int = 0
    failed: int = 0
    by_channel: dict[str, int] = field(default_factory=dict)
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pushed": self.total_pushed,
            "success": self.success,
            "failed": self.failed,
            "by_channel": dict(self.by_channel),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }


class PushEngine:
    """新职位 -> 订阅者推送."""

    def __init__(
        self,
        subscription_service: JobSubscriptionService,
        *,
        dispatcher: NotifyDispatcher | None = None,
        title_template: str | None = None,
        body_template: str | None = None,
        max_retries: int = 3,
        retry_base_delay_s: float = 1.0,
    ) -> None:
        self.svc = subscription_service
        self.dispatcher = dispatcher or get_dispatcher()
        self.title_template = title_template or (
            "[新职位匹配] {count} 个职位符合订阅「{name}」"
        )
        self.body_template = body_template or (
            "Hi,\n"
            "你订阅的「{name}」命中了 {count} 个新职位:\n\n"
            "{job_list}\n\n"
            "查看详情: {base_url}/jobseeker/subscriptions\n"
        )
        self.max_retries = max_retries
        self.retry_base_delay_s = retry_base_delay_s
        self.stats = PushStats()

    async def on_new_job(
        self, job: JobPosting, *, base_url: str = "https://app.example.com"
    ) -> list[PushRecord]:
        """当新职位入库后调用: 找出所有匹配订阅,推送."""
        if job is None:
            return []

        records: list[PushRecord] = []
        for sub in self.svc.list_all_enabled():
            matches = await self.svc.match_subscription(
                sub.criteria, jobs=[job], limit=5
            )
            if not matches:
                continue
            rec = await self._push_one(sub, matches, base_url=base_url)
            records.append(rec)
        return records

    async def realtime_match_and_push(
        self,
        job: JobPosting,
        *,
        base_url: str = "https://app.example.com",
    ) -> list[PushRecord]:
        """T1804 — 实时推送 (新职位入库即推,带重试).

        与 ``on_new_job`` 的差别:
        - 不在 dispatcher 失败时立即放弃 — 指数退避重试 (1s, 3s, 9s)
        - 推送耗时统计到 ``self.stats``
        """
        if job is None:
            return []
        records: list[PushRecord] = []
        for sub in self.svc.list_all_enabled():
            matches = await self.svc.match_subscription(
                sub.criteria, jobs=[job], limit=5
            )
            if not matches:
                continue
            rec = await self.push_with_retry(sub, matches, base_url=base_url)
            records.append(rec)
            self._record_stats(rec)
        return records

    async def broadcast_existing(
        self, jobs: list[JobPosting] | None = None, *, base_url: str = "https://app.example.com"
    ) -> list[PushRecord]:
        """对所有 enabled 订阅跑一次匹配(用于启动补推 / 定时任务)."""
        pairs = await self.svc.match_all_subscriptions(jobs=jobs)
        records: list[PushRecord] = []
        for sub, matches in pairs:
            rec = await self._push_one(sub, matches, base_url=base_url)
            records.append(rec)
            self._record_stats(rec)
        return records

    # ------------------------------------------------------------------
    # T1804 — 重试 + 灌订阅 + 统计
    # ------------------------------------------------------------------
    async def push_with_retry(
        self,
        sub: Subscription,
        matches: list[JobPosting],
        *,
        base_url: str,
    ) -> PushRecord:
        """带指数退避的重试推送."""
        last_rec: PushRecord | None = None
        for attempt in range(1, self.max_retries + 1):
            rec = await self._push_one(sub, matches, base_url=base_url)
            rec.attempts = attempt
            if rec.success:
                return rec
            last_rec = rec
            if attempt < self.max_retries:
                delay = self.retry_base_delay_s * (3 ** (attempt - 1))
                await asyncio.sleep(delay)
        return last_rec or await self._push_one(sub, matches, base_url=base_url)

    def _record_stats(self, rec: PushRecord) -> None:
        """聚合推送统计."""
        self.stats.total_pushed += 1
        if rec.success:
            self.stats.success += 1
        else:
            self.stats.failed += 1
        for ch in rec.channels:
            self.stats.by_channel[ch] = self.stats.by_channel.get(ch, 0) + 1
        # 滑动平均
        n = self.stats.total_pushed
        prev = self.stats.avg_latency_ms
        self.stats.avg_latency_ms = prev + (rec.duration_ms - prev) / n

    def push_stats(self) -> dict[str, Any]:
        return self.stats.to_dict()

    async def bulk_seed_subscriptions(
        self, jsonl_path: str | Path
    ) -> int:
        """T1804 — 从 seed JSONL 灌入订阅 (供测试 / 集成使用)."""
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning("[push-engine] bulk_seed: file not found %s", path)
            return 0

        n = 0
        with path.open("r", encoding="utf-8") as f:
            for ln, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[push-engine] JSONL parse fail line %d: %s", ln, exc)
                    continue
                crit = row.get("criteria") or {}
                if isinstance(crit, dict):
                    crit = SubscriptionCriteria.from_dict(crit)
                self.svc.create(
                    user_id=str(row.get("user_id") or "anon"),
                    name=str(row.get("name") or "subscription"),
                    criteria=crit,
                    channels=list(row.get("channels") or ["web"]),
                    enabled=bool(row.get("enabled", True)),
                )
                n += 1
        logger.info("[push-engine] bulk_seed: %d subs from %s", n, path.name)
        return n

    # ------------------------------------------------------------------
    async def _push_one(
        self,
        sub: Subscription,
        matches: list[JobPosting],
        *,
        base_url: str,
    ) -> PushRecord:
        import time

        rec = PushRecord(
            subscription_id=sub.id,
            user_id=sub.user_id,
            channels=list(sub.channels) or ["web"],
            matches=matches,
        )
        if not matches:
            rec.success = False
            rec.error = "no matches"
            return rec

        title = self.title_template.format(
            count=len(matches), name=sub.name or sub.criteria.role or "订阅"
        )
        body = self._render_body(sub, matches, base_url=base_url)

        start = time.monotonic()
        try:
            outcome = await self.dispatcher.dispatch_multi(
                channels=rec.channels,
                user_id=sub.user_id,
                title=title,
                content=body,
                payload={
                    "metadata": {
                        "subscription_id": sub.id,
                        "job_ids": [j.id for j in matches],
                        "kind": "subscription_match",
                    }
                },
            )
            rec.outcome = outcome
            rec.success = outcome.success
            if not outcome.success:
                rec.error = f"failed channels: {outcome.failed_channels}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("[push-engine] dispatch failed sub=%s", sub.id)
            rec.success = False
            rec.error = str(exc)
        finally:
            rec.duration_ms = int((time.monotonic() - start) * 1000)
        return rec

    def _render_body(
        self,
        sub: Subscription,
        matches: list[JobPosting],
        *,
        base_url: str,
    ) -> str:
        lines = []
        for i, m in enumerate(matches[:5], start=1):
            salary = f"{m.currency} {int(m.salary_min)}-{int(m.salary_max)}"
            lines.append(
                f"{i}. {m.title} @ {m.company} ({m.city}) — {salary}"
            )
        job_list = "\n".join(lines)
        return self.body_template.format(
            name=sub.name or sub.criteria.role or "订阅",
            count=len(matches),
            job_list=job_list,
            base_url=base_url,
        )


__all__ = ["PushEngine", "PushRecord"]