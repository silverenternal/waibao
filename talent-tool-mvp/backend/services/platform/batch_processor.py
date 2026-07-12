"""T2302 — 批量操作服务.

支持的动作:
- bulk_update: 更新字段 (stage, tags, owner 等)
- bulk_email: 批量发邮件
- bulk_offer: 批量发 offer
- bulk_move_stage: 移动到下一阶段 (漏斗推进)
- bulk_archive: 软归档

特性:
- 后台异步执行 (FastAPI BackgroundTasks / 可选 Celery)
- 进度跟踪 (内存 + 可选 Redis)
- 失败重试 (指数退避)
- 任务取消
- 实时状态查询
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, Optional

logger = logging.getLogger("recruittech.services.batch")


# ---------------------------------------------------------------------------
# 枚举与常量
# ---------------------------------------------------------------------------


class BatchAction(str, Enum):
    BULK_UPDATE = "bulk_update"
    BULK_EMAIL = "bulk_email"
    BULK_OFFER = "bulk_offer"
    BULK_MOVE_STAGE = "bulk_move_stage"
    BULK_TAG = "bulk_tag"
    BULK_ARCHIVE = "bulk_archive"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"  # 部分成功


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass
class BatchProgress:
    task_id: str
    action: str
    total: int
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    status: TaskStatus = TaskStatus.PENDING
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    errors: list[dict[str, str]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 100.0
        return round(self.processed / self.total * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["percent"] = self.percent
        return d


# ---------------------------------------------------------------------------
# 进度存储 (内存 + 可选 Redis)
# ---------------------------------------------------------------------------


class ProgressStore:
    """进程内进度存储,支持 Redis fallback."""

    def __init__(self, redis_client=None):
        self._memory: dict[str, BatchProgress] = {}
        self._redis = redis_client

    def _key(self, task_id: str) -> str:
        return f"batch:progress:{task_id}"

    def save(self, progress: BatchProgress) -> None:
        progress.updated_at = datetime.now(timezone.utc).isoformat()
        self._memory[progress.task_id] = progress
        if self._redis:
            try:
                self._redis.setex(
                    self._key(progress.task_id),
                    86400,  # 24h TTL
                    json.dumps(progress.to_dict()),
                )
            except Exception as e:
                logger.warning("Redis save failed: %s", e)

    def get(self, task_id: str) -> BatchProgress | None:
        if task_id in self._memory:
            return self._memory[task_id]
        if self._redis:
            try:
                raw = self._redis.get(self._key(task_id))
                if raw:
                    data = json.loads(raw)
                    prog = BatchProgress(
                        task_id=data["task_id"],
                        action=data["action"],
                        total=data["total"],
                        processed=data["processed"],
                        succeeded=data["succeeded"],
                        failed=data["failed"],
                        status=TaskStatus(data["status"]),
                        started_at=data.get("started_at", ""),
                        updated_at=data.get("updated_at", ""),
                        completed_at=data.get("completed_at", ""),
                        errors=data.get("errors", []),
                        result=data.get("result", {}),
                    )
                    self._memory[task_id] = prog
                    return prog
            except Exception as e:
                logger.warning("Redis get failed: %s", e)
        return None

    def cancel(self, task_id: str) -> bool:
        p = self.get(task_id)
        if p and p.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            p.status = TaskStatus.CANCELLED
            self.save(p)
            return True
        return False


# ---------------------------------------------------------------------------
# 处理器定义
# ---------------------------------------------------------------------------


HandlerFn = Callable[[str, dict[str, Any], Any], Awaitable[None]]


# Stage progression rules (T2302 bulk_move_stage)
NEXT_STAGE_MAP: dict[str, str] = {
    "sourced": "screened",
    "screened": "interviewed",
    "interviewed": "offered",
    "offered": "hired",
    "applied": "screened",
    "new": "screening",
}


async def handle_bulk_update(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """更新候选人字段."""
    fields = {k: v for k, v in payload.items() if k != "candidate_ids"}
    if not fields:
        return
    supabase.table("candidates").update(fields).eq("id", candidate_id).execute()


async def handle_bulk_email(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """发送邮件 — 调用通知服务占位 (实际可走 notify service)."""
    template = payload.get("template", "default")
    subject = payload.get("subject", "")
    # 模拟延迟
    await asyncio.sleep(0.01)
    # 记录 signal
    try:
        supabase.table("signals").insert({
            "candidate_id": candidate_id,
            "event_type": "email_sent",
            "metadata": {"template": template, "subject": subject},
        }).execute()
    except Exception as e:
        logger.warning("Failed to log email signal for %s: %s", candidate_id, e)


async def handle_bulk_offer(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """发 offer — 写 offers 表."""
    supabase.table("offers").insert({
        "candidate_id": candidate_id,
        "role_id": payload.get("role_id"),
        "salary": payload.get("salary"),
        "currency": payload.get("currency", "USD"),
        "status": "sent",
        "metadata": payload.get("metadata", {}),
    }).execute()


async def handle_bulk_move_stage(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """移到下一阶段."""
    # 取当前阶段
    res = (
        supabase.table("candidates")
        .select("stage")
        .eq("id", candidate_id)
        .single()
        .execute()
    )
    current = (res.data or {}).get("stage") or "new"
    next_stage = NEXT_STAGE_MAP.get(current)
    if not next_stage:
        # 没有映射规则 → 用 payload 指定的 stage
        next_stage = payload.get("target_stage")
    if next_stage:
        supabase.table("candidates").update(
            {"stage": next_stage}
        ).eq("id", candidate_id).execute()


async def handle_bulk_tag(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """打标签 — 追加到 tags 数组."""
    tags_to_add = payload.get("tags", [])
    if not tags_to_add:
        return
    res = (
        supabase.table("candidates")
        .select("tags")
        .eq("id", candidate_id)
        .single()
        .execute()
    )
    current_tags = (res.data or {}).get("tags") or []
    merged = list(set(current_tags) | set(tags_to_add))
    supabase.table("candidates").update(
        {"tags": merged}
    ).eq("id", candidate_id).execute()


async def handle_bulk_archive(
    candidate_id: str, payload: dict[str, Any], supabase
) -> None:
    """软归档."""
    supabase.table("candidates").update(
        {"archived_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", candidate_id).execute()


HANDLERS: dict[str, HandlerFn] = {
    BatchAction.BULK_UPDATE.value: handle_bulk_update,
    BatchAction.BULK_EMAIL.value: handle_bulk_email,
    BatchAction.BULK_OFFER.value: handle_bulk_offer,
    BatchAction.BULK_MOVE_STAGE.value: handle_bulk_move_stage,
    BatchAction.BULK_TAG.value: handle_bulk_tag,
    BatchAction.BULK_ARCHIVE.value: handle_bulk_archive,
}


# ---------------------------------------------------------------------------
# 批量处理器
# ---------------------------------------------------------------------------


class BatchProcessor:
    """异步批量处理核心."""

    def __init__(
        self,
        supabase,
        progress_store: ProgressStore | None = None,
        max_concurrency: int = 10,
        max_retries: int = 3,
        retry_base_delay: float = 0.1,
    ):
        self.supabase = supabase
        self.store = progress_store or ProgressStore()
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self._cancel_flags: dict[str, bool] = {}

    async def run(
        self,
        action: str,
        candidate_ids: list[str],
        payload: dict[str, Any],
        task_id: str | None = None,
    ) -> BatchProgress:
        """执行批量任务,返回进度对象."""
        task_id = task_id or str(uuid.uuid4())
        progress = BatchProgress(
            task_id=task_id,
            action=action,
            total=len(candidate_ids),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        progress.status = TaskStatus.RUNNING
        self.store.save(progress)
        self._cancel_flags[task_id] = False

        handler = HANDLERS.get(action)
        if not handler:
            progress.status = TaskStatus.FAILED
            progress.errors.append({
                "id": "_global",
                "error": f"未知 action: {action}",
            })
            progress.completed_at = datetime.now(timezone.utc).isoformat()
            self.store.save(progress)
            return progress

        try:
            await asyncio.gather(*[
                self._process_one(progress, cid, payload, handler)
                for cid in candidate_ids
            ])
        except Exception as e:
            logger.exception("batch run failed")
            progress.errors.append({"id": "_global", "error": str(e)})

        if progress.status == TaskStatus.RUNNING:
            if progress.failed == 0:
                progress.status = TaskStatus.COMPLETED
            elif progress.succeeded == 0:
                progress.status = TaskStatus.FAILED
            else:
                progress.status = TaskStatus.PARTIAL
        progress.completed_at = datetime.now(timezone.utc).isoformat()
        self.store.save(progress)
        return progress

    async def _process_one(
        self,
        progress: BatchProgress,
        candidate_id: str,
        payload: dict[str, Any],
        handler: HandlerFn,
    ) -> None:
        async with self.semaphore:
            if self._cancel_flags.get(progress.task_id):
                progress.failed += 1
                progress.processed += 1
                progress.errors.append({
                    "id": candidate_id,
                    "error": "task cancelled",
                })
                self.store.save(progress)
                return

            for attempt in range(self.max_retries + 1):
                try:
                    await handler(candidate_id, payload, self.supabase)
                    progress.succeeded += 1
                    break
                except Exception as e:
                    if attempt >= self.max_retries:
                        progress.failed += 1
                        progress.errors.append({
                            "id": candidate_id,
                            "error": str(e)[:200],
                        })
                    else:
                        # 指数退避
                        await asyncio.sleep(
                            self.retry_base_delay * (2 ** attempt)
                            + random.random() * 0.05
                        )
            progress.processed += 1
            self.store.save(progress)

    def cancel(self, task_id: str) -> bool:
        self._cancel_flags[task_id] = True
        return self.store.cancel(task_id)

    def get_progress(self, task_id: str) -> BatchProgress | None:
        return self.store.get(task_id)