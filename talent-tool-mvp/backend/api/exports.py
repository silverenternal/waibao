"""T2303 — 文档导出 API.

端点:
- GET /api/exports/candidate-report/{id}?format=docx|pptx|pdf
- GET /api/exports/funnel-report?format=...
- GET /api/exports/sla-report?format=...
- GET /api/exports/weekly?format=...
- GET /api/exports/monthly?format=...
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase
from services.platform.document_generator import (
    DocumentGenerator,
    DocFormat,
    DocTemplate,
    load_template_data,
)

logger = logging.getLogger("recruittech.api.exports")
router = APIRouter(prefix="/api/exports", tags=["exports"])

_generator: DocumentGenerator | None = None


def _get_generator() -> DocumentGenerator:
    global _generator
    if _generator is None:
        _generator = DocumentGenerator()
    return _generator


@router.get("/candidate-report/{candidate_id}")
async def export_candidate_report(
    candidate_id: UUID,
    format: str = Query("docx", pattern="^(docx|pptx|pdf)$"),
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """导出候选人报告."""
    data = load_template_data(
        DocTemplate.CANDIDATE_REPORT.value,
        supabase,
        candidate_id=str(candidate_id),
    )
    if data.get("error"):
        raise HTTPException(status_code=404, detail=data["error"])

    gen = _get_generator()
    result = gen.generate(
        template=DocTemplate.CANDIDATE_REPORT.value,
        fmt=format,
        data=data,
        title=f"候选人报告 — {data.get('name', '')}",
    )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.get("/funnel-report")
async def export_funnel_report(
    format: str = Query("docx", pattern="^(docx|pptx|pdf)$"),
    period_days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """导出漏斗分析报告."""
    data = load_template_data(
        DocTemplate.FUNNEL_REPORT.value,
        supabase,
        period_days=period_days,
    )
    gen = _get_generator()
    result = gen.generate(
        template=DocTemplate.FUNNEL_REPORT.value,
        fmt=format,
        data=data,
        title=f"漏斗分析 ({period_days} 天)",
    )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.get("/sla-report")
async def export_sla_report(
    format: str = Query("docx", pattern="^(docx|pptx|pdf)$"),
    period_days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """导出 SLA 报告."""
    data = load_template_data(
        DocTemplate.SLA_REPORT.value,
        supabase,
        period_days=period_days,
    )
    gen = _get_generator()
    result = gen.generate(
        template=DocTemplate.SLA_REPORT.value,
        fmt=format,
        data=data,
        title=f"SLA 报告 ({period_days} 天)",
    )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.get("/weekly")
async def export_weekly(
    format: str = Query("docx", pattern="^(docx|pptx|pdf)$"),
    week_offset: int = Query(0, ge=0, le=52),
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """导出招聘周报."""
    data = load_template_data(
        DocTemplate.WEEKLY_RECRUITMENT.value,
        supabase,
        week_offset=week_offset,
    )
    gen = _get_generator()
    result = gen.generate(
        template=DocTemplate.WEEKLY_RECRUITMENT.value,
        fmt=format,
        data=data,
        title="招聘周报",
    )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.get("/monthly")
async def export_monthly(
    format: str = Query("docx", pattern="^(docx|pptx|pdf)$"),
    month_offset: int = Query(0, ge=0, le=24),
    user: CurrentUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """导出招聘月报."""
    data = load_template_data(
        DocTemplate.MONTHLY_RECRUITMENT.value,
        supabase,
        month_offset=month_offset,
    )
    gen = _get_generator()
    result = gen.generate(
        template=DocTemplate.MONTHLY_RECRUITMENT.value,
        fmt=format,
        data=data,
        title="招聘月报",
    )
    return Response(
        content=result.content,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )