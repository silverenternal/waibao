"""Attrition API (T2403).

Endpoints:
    GET  /api/attrition/risk/{user_id}
    GET  /api/attrition/risk/team/{org_id}
    POST /api/attrition/retrain (管理员)
    POST /api/attrition/care (发关怀消息)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from services.platform.attrition_model import get_attrition_model

logger = logging.getLogger("recruittech.api.attrition")
router = APIRouter()


class CareRequest(BaseModel):
    user_id: str
    message: str
    channel: str = "im"  # im / email / dingtalk


class RetrainRequest(BaseModel):
    notes: str = ""


@router.get("/risk/{user_id}")
async def get_user_risk(
    user_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """获取单个用户的离职风险."""
    model = get_attrition_model()
    risk = model.predict(user_id)
    return risk.to_dict()


@router.get("/risk/team/{org_id}")
async def get_team_risk(
    org_id: str,
    user_ids: list[str] = Query(..., description="comma-separated user IDs"),
    _user: CurrentUser = Depends(get_current_user),
):
    """HR 视角: 团队离职风险聚合 (热力图数据)."""
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids is required")
    model = get_attrition_model()
    return model.predict_team(org_id, user_ids)


@router.post("/retrain")
async def retrain_model(
    body: RetrainRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """管理员: 触发模型再训练.

    当前 stub — 真实训练 pipeline 在 T2403 后续迭代接入.
    """
    if user.role.value not in ("admin", "hr"):
        raise HTTPException(status_code=403, detail="admin/hr role required")
    logger.info("attrition.retrain_requested by=%s notes=%s", user.id, body.notes)
    return {
        "status": "queued",
        "notes": body.notes,
        "message": "模型再训练已加入队列 (T2403 当前 stub)",
    }


@router.post("/care")
async def send_care_message(
    body: CareRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """一键关怀 (发消息给高风险用户)."""
    if user.role.value not in ("admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="insufficient role")
    logger.info(
        "attrition.care_sent by=%s to=%s channel=%s",
        user.id,
        body.user_id,
        body.channel,
    )
    return {
        "status": "queued",
        "user_id": body.user_id,
        "channel": body.channel,
        "message_preview": body.message[:50],
    }