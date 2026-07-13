"""v8.0 T3901 — Admin Insights API.

Endpoints:
- GET  /api/insights/weekly            最新/历史周报列表
- GET  /api/insights/weekly/latest     最新周报 (含异常 + 行为洞察)
- POST /api/insights/weekly/generate   手动触发生成周报
- GET  /api/insights/anomalies         当前 / 历史异常
- GET  /api/insights/behavior          用户行为分析 (popular / abandoned / low_usage)
- POST /api/insights/cycle             单次 run_cycle (异常检测 + 告警)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.insights")
router = APIRouter()


# ---------------------------------------------------------------------------
# 依赖注入 (便于测试)
# ---------------------------------------------------------------------------


def get_auto_report_svc():
    from services.platform import get_auto_report_service

    return get_auto_report_service()


def get_anomaly_detector_svc():
    from services.platform import get_anomaly_detector

    return get_anomaly_detector()


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """仅 admin 可访问; 否则 403."""
    if getattr(user, "role", None) not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="admin only")
    return user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WeeklyReportSummary(BaseModel):
    week_start: str
    week_end: str
    format: str
    filename: str
    size_bytes: int
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class GenerateRequest(BaseModel):
    fmt: str = Field("pdf", pattern="^(pdf|docx|txt)$")
    role: Optional[str] = None
    anomalies: Optional[List[dict[str, Any]]] = None


class GenerateResponse(BaseModel):
    week: str
    format: str
    size_bytes: int
    summary: dict[str, Any]
    delivery: dict[str, Any]


class AnomalyListResponse(BaseModel):
    anomalies: List[dict[str, Any]]
    behavior_insights: List[dict[str, Any]] = Field(default_factory=list)
    metrics_used: dict[str, Any] = Field(default_factory=dict)
    alert: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/api/insights/weekly", response_model=List[WeeklyReportSummary])
async def list_weekly_reports(
    limit: int = Query(8, ge=1, le=50),
    user: CurrentUser = Depends(require_admin),
):
    """列出最近 N 份周报."""
    supabase = get_supabase_admin()
    if supabase is None:
        return []
    try:
        res = (
            supabase.table("weekly_reports")
            .select("week_start,week_end,format,filename,size_bytes,summary,generated_at")
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        return [
            WeeklyReportSummary(
                week_start=r.get("week_start", ""),
                week_end=r.get("week_end", ""),
                format=r.get("format", "txt"),
                filename=r.get("filename", ""),
                size_bytes=int(r.get("size_bytes", 0)),
                summary=r.get("summary") or {},
                generated_at=r.get("generated_at", ""),
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning("list_weekly_reports failed: %s", exc)
        return []


@router.get("/api/insights/weekly/latest")
async def latest_weekly_report(user: CurrentUser = Depends(require_admin)):
    """返回最新周报 + 异常 + 行为洞察 (合并)."""
    supabase = get_supabase_admin()
    latest = None
    if supabase is not None:
        try:
            res = (
                supabase.table("weekly_reports")
                .select("*")
                .order("generated_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                latest = rows[0]
        except Exception as exc:
            logger.warning("latest_weekly_report: %s", exc)
    detector = get_anomaly_detector_svc()
    cycle = await detector.run_cycle()
    return {
        "latest_report": latest,
        "anomalies": cycle["anomalies"],
        "behavior_insights": cycle["behavior_insights"],
        "alert": cycle["alert"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/insights/weekly/generate", response_model=GenerateResponse)
async def generate_weekly_report(
    body: GenerateRequest,
    user: CurrentUser = Depends(require_admin),
):
    svc = get_auto_report_svc()
    if body.fmt == "pdf":
        report = svc.generate(fmt="pdf", anomalies=body.anomalies, persist=True)
    elif body.fmt == "docx":
        report = svc.generate(fmt="docx", anomalies=body.anomalies, persist=True)
    else:
        report = svc.generate(fmt="txt", anomalies=body.anomalies, persist=True)
    delivery = await svc.deliver(report, recipients=svc.resolve_recipients(role=body.role))
    return GenerateResponse(
        week=f"{report.week_start} ~ {report.week_end}",
        format=report.format,
        size_bytes=report.size_bytes,
        summary=report.summary,
        delivery=delivery,
    )


@router.get("/api/insights/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    limit: int = Query(20, ge=1, le=200),
    user: CurrentUser = Depends(require_admin),
):
    detector = get_anomaly_detector_svc()
    cycle = await detector.run_cycle()
    # 取历史
    supabase = get_supabase_admin()
    history: List[dict[str, Any]] = []
    if supabase is not None:
        try:
            res = (
                supabase.table("anomalies")
                .select("type,severity,metric,current,baseline,delta_pct,message,detected_at,metadata")
                .order("detected_at", desc=True)
                .limit(limit)
                .execute()
            )
            history = res.data or []
        except Exception as exc:
            logger.warning("list_anomalies history: %s", exc)
    combined = list(cycle["anomalies"]) + list(history)
    return AnomalyListResponse(
        anomalies=combined[:limit],
        behavior_insights=cycle["behavior_insights"],
        metrics_used=cycle["metrics_used"],
        alert=cycle["alert"],
    )


@router.get("/api/insights/behavior")
async def list_behavior_insights(user: CurrentUser = Depends(require_admin)):
    detector = get_anomaly_detector_svc()
    cycle = await detector.run_cycle()
    return {
        "insights": cycle["behavior_insights"],
        "metrics_used": cycle["metrics_used"],
    }


@router.post("/api/insights/cycle", response_model=AnomalyListResponse)
async def run_cycle(user: CurrentUser = Depends(require_admin)):
    detector = get_anomaly_detector_svc()
    cycle = await detector.run_cycle()
    # 持久化异常
    supabase = get_supabase_admin()
    if supabase is not None and cycle["anomalies"]:
        try:
            supabase.table("anomalies").insert(cycle["anomalies"]).execute()
        except Exception as exc:
            logger.warning("persist anomalies: %s", exc)
    return AnomalyListResponse(
        anomalies=cycle["anomalies"],
        behavior_insights=cycle["behavior_insights"],
        metrics_used=cycle["metrics_used"],
        alert=cycle["alert"],
    )
