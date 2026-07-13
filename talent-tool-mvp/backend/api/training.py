"""T3001: LoRA Fine-tuning 管理 API.

Endpoints:
    POST /api/training/jobs              — 触发一次微调 (task + 可选 records)
    POST /api/training/jobs/all          — 训练全部 3 个 LoRA
    GET  /api/training/models            — 列出已注册 adapter
    GET  /api/training/models/{model_id} — adapter 详情
    POST /api/training/models/{model_id}/promote — 设为该 task 的 active
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.training import (
    TaskKind,
    get_registry,
    run_pipeline,
    train_all,
)

logger = logging.getLogger("recruittech.api.training")
router = APIRouter()


class TrainRequest(BaseModel):
    task: str = Field(..., description="resume_scoring | bias_review | hrbp_summary")
    records: list[dict[str, Any]] | None = None
    dry_run: bool | None = Field(None, description="None=自动检测 GPU; True 强制离线")
    base_model: str | None = None


def _parse_task(task: str) -> TaskKind:
    try:
        return TaskKind(task)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown task={task}")


@router.post("/jobs")
async def create_training_job(
    body: TrainRequest,
    _user: CurrentUser = Depends(get_current_user),
):
    """触发一次 LoRA 微调 (数据准备 → 训练 → 评估 → 部署 → 注册)."""
    task = _parse_task(body.task)
    from services.training import LoRAConfig

    config = LoRAConfig(base_model=body.base_model) if body.base_model else None
    job = await run_pipeline(task, records=body.records, config=config, dry_run=body.dry_run)
    return job.to_dict()


@router.post("/jobs/all")
async def train_all_loras(
    dry_run: bool | None = Query(None),
    _user: CurrentUser = Depends(get_current_user),
):
    """训练全部 3 个内置 LoRA."""
    jobs = await train_all(dry_run=dry_run)
    return {task.value: job.to_dict() for task, job in jobs.items()}


@router.get("/models")
async def list_models(
    task: Optional[str] = Query(None),
    _user: CurrentUser = Depends(get_current_user),
):
    """列出已注册的 LoRA adapter."""
    kind = _parse_task(task) if task else None
    models = get_registry().list(task=kind)
    return {"models": [m.to_dict() for m in models], "total": len(models)}


@router.get("/models/{model_id}")
async def get_model(
    model_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """获取某 adapter 详情."""
    m = get_registry().get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"unknown model_id={model_id}")
    return m.to_dict()


@router.post("/models/{model_id}/promote")
async def promote_model(
    model_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """把某版本设为该 task 的 active (推理默认走它)."""
    try:
        m = get_registry().promote(model_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown model_id={model_id}")
    return m.to_dict()
