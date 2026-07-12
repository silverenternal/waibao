"""T2304 用户通知偏好 API (前端拉取 / 保存).

端点:
- GET  /api/notifications/prefs         —— 拉取当前用户全部 prefs
- POST /api/notifications/prefs         —— 单条 upsert
- POST /api/notifications/prefs/bulk    —— 整页批量 upsert
- DELETE /api/notifications/prefs       —— 删除单条 (恢复默认)
- GET  /api/notifications/categories    —— 元数据 (类别 / 优先级 / 通道 / 频率枚举)
- GET  /api/notifications/digests       —— 历史摘要
- GET  /api/notifications/suggestions   —— 列出 pending 建议
- POST /api/notifications/suggestions/generate —— 重新生成建议
- POST /api/notifications/suggestions/{id}/apply    —— 应用
- POST /api/notifications/suggestions/{id}/dismiss  —— 忽略
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.platform.notification_prefs import (
    VALID_CATEGORIES,
    VALID_CHANNELS,
    VALID_FREQUENCIES,
    VALID_PRIORITIES,
    get_prefs_service,
)
from services.platform.notification_suggester import get_suggester

logger = logging.getLogger("recruittech.api.notification_prefs")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PrefUpsertIn(BaseModel):
    category: str = Field(..., description="matching/ticket/emotion/system/recruiting")
    priority: str = Field(default="medium", description="high/medium/low")
    channel: str = Field(..., description="smtp/dingtalk/feishu/im/web")
    frequency: str = Field(default="realtime")
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    enabled: bool = True


class PrefBulkIn(BaseModel):
    prefs: list[PrefUpsertIn]


class PrefOut(BaseModel):
    id: str | None = None
    category: str
    priority: str
    channel: str
    frequency: str
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    enabled: bool
    created_at: str | None = None
    updated_at: str | None = None


class PrefListOut(BaseModel):
    prefs: list[PrefOut]


class DigestOut(BaseModel):
    id: str
    period: str
    content: dict[str, Any]
    window_start: str
    window_end: str
    sent_at: str


class DigestListOut(BaseModel):
    digests: list[DigestOut]


class SuggestionOut(BaseModel):
    id: str
    type: str
    description: str
    suggestion: dict[str, Any]
    confidence: float
    status: str
    created_at: str


class SuggestionListOut(BaseModel):
    suggestions: list[SuggestionOut]


class GenerateOut(BaseModel):
    created: int
    suggestions: list[SuggestionOut]


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/categories")
async def list_metadata(user: CurrentUser = Depends(get_current_user)):
    """返回前端所需的枚举 + 默认矩阵."""
    return {
        "categories": list(VALID_CATEGORIES),
        "priorities": list(VALID_PRIORITIES),
        "channels": list(VALID_CHANNELS),
        "frequencies": list(VALID_FREQUENCIES),
        "category_labels": {
            "matching": "匹配",
            "ticket": "工单",
            "emotion": "情绪",
            "system": "系统",
            "recruiting": "招聘",
        },
        "channel_labels": {
            "smtp": "邮件",
            "dingtalk": "钉钉",
            "feishu": "飞书",
            "im": "IM",
            "web": "Web",
        },
        "frequency_labels": {
            "realtime": "实时",
            "hourly": "小时摘要",
            "daily": "天摘要",
            "weekly": "周摘要",
        },
        "priority_labels": {
            "high": "高",
            "medium": "中",
            "low": "低",
        },
    }


# ---------------------------------------------------------------------------
# 偏好 CRUD
# ---------------------------------------------------------------------------


@router.get("/prefs", response_model=PrefListOut)
async def list_prefs(user: CurrentUser = Depends(get_current_user)):
    svc = get_prefs_service()
    prefs = await svc.get_prefs(str(user.id))
    return {
        "prefs": [
            {
                "id": p.id,
                "category": p.category,
                "priority": p.priority,
                "channel": p.channel,
                "frequency": p.frequency,
                "quiet_hours_start": p.quiet_hours_start,
                "quiet_hours_end": p.quiet_hours_end,
                "enabled": p.enabled,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in prefs
        ]
    }


@router.post("/prefs", response_model=PrefOut)
async def upsert_pref(
    payload: PrefUpsertIn,
    user: CurrentUser = Depends(get_current_user),
):
    svc = get_prefs_service()
    try:
        pref = await svc.set_prefs(
            str(user.id),
            category=payload.category,
            priority=payload.priority,
            channel=payload.channel,
            frequency=payload.frequency,
            quiet_hours_start=payload.quiet_hours_start,
            quiet_hours_end=payload.quiet_hours_end,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PrefOut(
        id=pref.id,
        category=pref.category,
        priority=pref.priority,
        channel=pref.channel,
        frequency=pref.frequency,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        enabled=pref.enabled,
        created_at=pref.created_at,
        updated_at=pref.updated_at,
    )


@router.post("/prefs/bulk", response_model=PrefListOut)
async def bulk_set(
    payload: PrefBulkIn,
    user: CurrentUser = Depends(get_current_user),
):
    svc = get_prefs_service()
    try:
        prefs = await svc.bulk_set(
            str(user.id),
            [p.model_dump() for p in payload.prefs],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "prefs": [
            {
                "id": p.id,
                "category": p.category,
                "priority": p.priority,
                "channel": p.channel,
                "frequency": p.frequency,
                "quiet_hours_start": p.quiet_hours_start,
                "quiet_hours_end": p.quiet_hours_end,
                "enabled": p.enabled,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in prefs
        ]
    }


@router.delete("/prefs")
async def delete_pref(
    category: str = Query(...),
    priority: str = Query(default="medium"),
    channel: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
):
    svc = get_prefs_service()
    ok = await svc.delete_pref(str(user.id), category, priority, channel)
    return {"deleted": ok}


# ---------------------------------------------------------------------------
# 摘要
# ---------------------------------------------------------------------------


@router.get("/digests", response_model=DigestListOut)
async def list_digests(
    period: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    svc = get_prefs_service()
    rows = await svc.list_digests(str(user.id), period=period, limit=limit)
    return {
        "digests": [
            DigestOut(
                id=r["id"],
                period=r["period"],
                content=r.get("content") or {},
                window_start=r["window_start"],
                window_end=r["window_end"],
                sent_at=r["sent_at"],
            )
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# 智能建议
# ---------------------------------------------------------------------------


@router.get("/suggestions", response_model=SuggestionListOut)
async def list_suggestions(user: CurrentUser = Depends(get_current_user)):
    suggester = get_suggester()
    rows = await suggester.list_pending(str(user.id))
    return {
        "suggestions": [
            SuggestionOut(
                id=r["id"],
                type=r["type"],
                description=r["description"],
                suggestion=r.get("suggestion") or {},
                confidence=r.get("confidence") or 0.5,
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
    }


@router.post("/suggestions/generate", response_model=GenerateOut)
async def regenerate_suggestions(
    days: int = Query(default=7, ge=1, le=30),
    user: CurrentUser = Depends(get_current_user),
):
    suggester = get_suggester()
    stats = await suggester.analyze_usage(str(user.id), days=days)
    suggestions = await suggester.generate_suggestions(str(user.id), days=days)
    ids = await suggester.save_suggestions(
        str(user.id), suggestions, based_on=stats
    )

    # 回读 pending 给前端
    pending = await suggester.list_pending(str(user.id))
    by_id = {r["id"]: r for r in pending}

    out: list[SuggestionOut] = []
    for sid, sug in zip(ids, suggestions):
        row = by_id.get(sid) or {}
        out.append(
            SuggestionOut(
                id=sid,
                type=sug.type,
                description=sug.description,
                suggestion=sug.suggestion,
                confidence=sug.confidence,
                status=row.get("status", "pending"),
                created_at=row.get("created_at", ""),
            )
        )

    return GenerateOut(created=len(out), suggestions=out)


@router.post("/suggestions/{suggestion_id}/apply")
async def apply_suggestion(
    suggestion_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    suggester = get_suggester()
    ok = await suggester.apply_suggestion(str(suggestion_id), str(user.id))
    return {"applied": ok}


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(
    suggestion_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    suggester = get_suggester()
    ok = await suggester.dismiss_suggestion(str(suggestion_id), str(user.id))
    return {"dismissed": ok}