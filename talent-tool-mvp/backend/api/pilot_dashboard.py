"""T3801 — Pilot 实时 Dashboard API.

Endpoints:
- GET  /api/pilot/dashboard               每家 partner 的 30 天 KPI (供 admin 前端)
- GET  /api/pilot/dashboard/summary       总览 (program 总数 / 平均 NPS / 续约概率)
- GET  /api/pilot/dashboard/stream        SSE 实时事件流 (60s 刷新)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.auth import CurrentUser, get_current_user, require_role
from contracts.shared import UserRole
from services.integrations.pilot_monitoring import (
    get_org_summary,
    get_partner_dashboard,
)

logger = logging.getLogger("recruittech.api.pilot_dashboard")
router = APIRouter()


@router.get("/api/pilot/dashboard", summary="Pilot 合作方实时 Dashboard")
async def dashboard(
    days: int = Query(30, ge=1, le=180),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_role(user, [UserRole.ADMIN])
    rows = get_partner_dashboard(days=days)
    summary = get_org_summary(days=days)
    return {"summary": summary, "partners": rows}


@router.get("/api/pilot/dashboard/summary", summary="Pilot Dashboard 总览")
async def dashboard_summary(
    days: int = Query(30, ge=1, le=180),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    require_role(user, [UserRole.ADMIN])
    return get_org_summary(days=days)


@router.get("/api/pilot/dashboard/stream", summary="Pilot Dashboard SSE 流")
async def dashboard_stream(
    interval: int = Query(60, ge=5, le=600),
    user: CurrentUser = Depends(get_current_user),
):
    require_role(user, [UserRole.ADMIN])

    async def event_gen():
        while True:
            payload = {
                "summary": get_org_summary(),
                "partners": get_partner_dashboard(),
                "ts": int(time.time()),
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(event_gen(), media_type="text/event-stream")