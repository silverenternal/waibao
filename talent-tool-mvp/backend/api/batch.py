"""T2302 — 批量操作 API.

端点:
- POST /api/batch/candidates/{action}      启动批量任务
- GET  /api/batch/tasks/{task_id}           查询进度
- POST /api/batch/tasks/{task_id}/cancel    取消任务
- GET  /api/batch/tasks                     列出我的任务
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase
from services.platform.batch_processor import (
    BatchAction,
    BatchProgress,
    BatchProcessor,
)

logger = logging.getLogger("recruittech.api.batch")
router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchRequest(BaseModel):
    candidate_ids: list[str] = Field(..., min_length=1, max_length=1000)
    payload: dict = Field(default_factory=dict)


# 全局 processor 缓存 (按 supabase 实例)
_processors: dict[int, BatchProcessor] = {}


def _get_processor(supabase) -> BatchProcessor:
    key = id(supabase)
    if key not in _processors:
        _processors[key] = BatchProcessor(supabase)
    return _processors[key]


@router.post("/candidates/{action}")
async def bulk_action(
    action: str,
    req: BatchRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """启动批量任务.

    action ∈ bulk_update | bulk_email | bulk_offer | bulk_move_stage | bulk_tag | bulk_archive
    """
    if action not in {a.value for a in BatchAction}:
        raise HTTPException(status_code=400, detail=f"未知 action: {action}")

    processor = _get_processor(supabase)
    task_id = None

    async def _run():
        await processor.run(
            action=action,
            candidate_ids=req.candidate_ids,
            payload=req.payload,
            task_id=task_id,
        )

    # 先占位创建 progress,再后台跑
    from services.platform.batch_processor import ProgressStore
    store = processor.store
    initial = BatchProgress(
        task_id="pending",
        action=action,
        total=len(req.candidate_ids),
    )
    # 创建 task_id 后再启动
    import uuid as _uuid
    task_id = str(_uuid.uuid4())
    initial.task_id = task_id
    initial.status = "pending"
    store.save(initial)

    background_tasks.add_task(_run)
    return {
        "task_id": task_id,
        "status": "pending",
        "total": len(req.candidate_ids),
        "action": action,
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    processor = _get_processor(supabase)
    progress = processor.get_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="任务未找到")
    return progress.to_dict()


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    processor = _get_processor(supabase)
    ok = processor.cancel(task_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="任务不可取消 (已完成/失败/未找到)",
        )
    return {"task_id": task_id, "status": "cancelled"}


@router.get("/tasks")
async def list_tasks(
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """列出内存中的所有任务 (调试用)."""
    processor = _get_processor(supabase)
    tasks = [
        p.to_dict() for p in processor.store._memory.values()
    ]
    return {"tasks": tasks, "count": len(tasks)}