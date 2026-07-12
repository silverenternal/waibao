"""Subscriptions API — T1304 候选人订阅.

Endpoints:
    POST   /api/subscriptions             创建订阅
    GET    /api/subscriptions             列出当前用户全部订阅
    GET    /api/subscriptions/{id}        获取单条
    PATCH  /api/subscriptions/{id}        更新
    DELETE /api/subscriptions/{id}        删除
    GET    /api/subscriptions/{id}/matches 立即匹配(预览)
    POST   /api/subscriptions/{id}/refresh 主动刷新并推送(可选)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.job_subscription import (
    JobSubscriptionService,
    SubscriptionCriteria,
)

logger = logging.getLogger("recruittech.api.subscriptions")
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------
class CriteriaBody(BaseModel):
    role: str = ""
    city: str = ""
    salary_min: float = 0.0
    currency: str = "CNY"
    skills: list[str] = Field(default_factory=list)
    seniority: str = ""
    remote_policy: str = ""


class SubscriptionBody(BaseModel):
    name: str
    criteria: CriteriaBody
    channels: list[str] = Field(default_factory=lambda: ["web"])


class SubscriptionUpdateBody(BaseModel):
    name: Optional[str] = None
    criteria: Optional[CriteriaBody] = None
    channels: Optional[list[str]] = None
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _get_service() -> JobSubscriptionService:
    return JobSubscriptionService(get_supabase_admin())


def _criteria_to_dict(c: CriteriaBody) -> dict[str, Any]:
    return c.model_dump()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", summary="创建订阅")
async def create_subscription(
    body: SubscriptionBody, user: CurrentUser = Depends(get_current_user)
):
    svc = _get_service()
    sub = svc.create(
        user_id=str(user.id),
        name=body.name,
        criteria=_criteria_to_dict(body.criteria),
        channels=body.channels,
    )
    return sub.to_dict()


@router.get("", summary="列出我的订阅")
async def list_subscriptions(user: CurrentUser = Depends(get_current_user)):
    svc = _get_service()
    return {"subscriptions": [s.to_dict() for s in svc.list_for_user(str(user.id))]}


@router.get("/{sub_id}", summary="获取单条订阅")
async def get_subscription(
    sub_id: str, user: CurrentUser = Depends(get_current_user)
):
    svc = _get_service()
    sub = svc.get(sub_id, user_id=str(user.id))
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub.to_dict()


@router.patch("/{sub_id}", summary="更新订阅")
async def update_subscription(
    sub_id: str,
    body: SubscriptionUpdateBody,
    user: CurrentUser = Depends(get_current_user),
):
    svc = _get_service()
    sub = svc.update(
        sub_id,
        user_id=str(user.id),
        name=body.name,
        criteria=_criteria_to_dict(body.criteria) if body.criteria else None,
        channels=body.channels,
        enabled=body.enabled,
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub.to_dict()


@router.delete("/{sub_id}", summary="删除订阅")
async def delete_subscription(
    sub_id: str, user: CurrentUser = Depends(get_current_user)
):
    svc = _get_service()
    ok = svc.delete(sub_id, user_id=str(user.id))
    if not ok:
        raise HTTPException(status_code=404, detail="subscription not found")
    return {"ok": True, "id": sub_id}


# ---------------------------------------------------------------------------
# 匹配预览
# ---------------------------------------------------------------------------
@router.get("/{sub_id}/matches", summary="预览订阅匹配")
async def get_subscription_matches(
    sub_id: str,
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
):
    svc = _get_service()
    sub = svc.get(sub_id, user_id=str(user.id))
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    matches = await svc.match_subscription(sub.criteria, limit=limit)
    return {
        "subscription_id": sub_id,
        "matches": [m.to_dict() for m in matches],
        "count": len(matches),
    }


__all__ = ["router"]