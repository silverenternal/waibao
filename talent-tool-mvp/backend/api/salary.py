"""Salary Insights API (T2402).

Endpoints:
    GET /api/salary/insights?role=&city=&seniority=
    GET /api/salary/percentiles?role=&city=&seniority=
    GET /api/salary/trends?role=&city=&period=
    POST /api/salary/locate (body: {role, city, seniority, offer_k})
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from services.platform.salary_report import get_salary_report_service

logger = logging.getLogger("recruittech.api.salary")
router = APIRouter()


class LocateRequest(BaseModel):
    role: str
    city: str
    seniority: str = "mid"
    offer_k: float


@router.get("/insights")
async def get_salary_insights(
    role: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    seniority: str = Query("mid"),
    _user: CurrentUser = Depends(get_current_user),
):
    """获取完整薪资洞察 (分布 + 趋势 + 我的定位)."""
    svc = get_salary_report_service()
    dist = svc.compute_salary_distribution(role, city, seniority)
    trend = svc.compute_trend(role, city, period="monthly", months=12)
    return {
        "distribution": dist.to_dict(),
        "trend": trend.to_dict(),
    }


@router.get("/percentiles")
async def get_percentiles(
    role: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    seniority: str = Query("mid"),
    _user: CurrentUser = Depends(get_current_user),
):
    """获取百分位分布 (P10/P25/P50/P75/P90)."""
    svc = get_salary_report_service()
    dist = svc.compute_salary_distribution(role, city, seniority)
    return dist.to_dict()


@router.get("/trends")
async def get_trends(
    role: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    period: str = Query("monthly", pattern="^(monthly|quarterly|yearly)$"),
    months: int = Query(12, ge=1, le=36),
    _user: CurrentUser = Depends(get_current_user),
):
    """获取薪资趋势 (按 period 聚合)."""
    svc = get_salary_report_service()
    trend = svc.compute_trend(role, city, period=period, months=months)
    return trend.to_dict()


@router.post("/locate")
async def locate_offer(
    body: LocateRequest,
    _user: CurrentUser = Depends(get_current_user),
):
    """定位我的 offer 在行业分布中的位置."""
    svc = get_salary_report_service()
    pos = svc.locate_offer(body.role, body.city, body.seniority, body.offer_k)
    return pos.to_dict()