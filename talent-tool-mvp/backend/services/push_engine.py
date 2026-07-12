"""Push Engine — T1304 主动推送引擎.

复用 v3.0 ``services.notify.dispatcher.NotifyDispatcher`` 多通道推送;
当 ``job_subscription.match_all_subscriptions`` 命中职位时,逐条推送
"新匹配职位"通知给对应候选人。

主要入口:
- ``PushEngine.on_new_job(job_posting)`` — 新职位入库后调用,触发推送.
- ``PushEngine.broadcast_existing()`` — 启动时或定时任务调用,
  对所有 enabled 订阅跑一次匹配,补推历史匹配.

所有失败被吞掉(推送失败不应阻塞主业务),但有 logger 记录.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Optional

from services.job_subscription import (
    JobPosting,
    JobSubscriptionService,
    Subscription,
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


class PushEngine:
    """新职位 -> 订阅者推送."""

    def __init__(
        self,
        subscription_service: JobSubscriptionService,
        *,
        dispatcher: NotifyDispatcher | None = None,
        title_template: str | None = None,
        body_template: str | None = None,
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

    async def broadcast_existing(
        self, jobs: list[JobPosting] | None = None, *, base_url: str = "https://app.example.com"
    ) -> list[PushRecord]:
        """对所有 enabled 订阅跑一次匹配(用于启动补推 / 定时任务)."""
        pairs = await self.svc.match_all_subscriptions(jobs=jobs)
        records: list[PushRecord] = []
        for sub, matches in pairs:
            rec = await self._push_one(sub, matches, base_url=base_url)
            records.append(rec)
        return records

    # ------------------------------------------------------------------
    async def _push_one(
        self,
        sub: Subscription,
        matches: list[JobPosting],
        *,
        base_url: str,
    ) -> PushRecord:
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