"""Company Review API (T2401).

Endpoints:
    GET  /api/company-review/{company_id}                — 聚合 (3 源评分 + 评价 + 面试 + 薪资)
    GET  /api/company-review/{company_id}/interviews     — 面试经验列表
    GET  /api/company-review/{company_id}/salary         — 薪资洞察
    GET  /api/company-review/search?q=                  — 公司搜索
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import CurrentUser, get_current_user
from services.platform.company_review import get_company_review_service

logger = logging.getLogger("recruittech.api.company_review")
router = APIRouter()


@router.get("/search")
async def search_companies(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
):
    """按名称模糊搜索公司 (返回基础信息 + 评分)."""
    svc = get_company_review_service()
    results = await svc.search_companies(q, limit=limit)
    return {"query": q, "results": results, "total": len(results)}


@router.get("/{company_id}")
async def get_company_review_bundle(
    company_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """获取公司评价聚合包 (3 源评分 + 评价 + 面试 + 薪资)."""
    svc = get_company_review_service()
    bundle = await svc.get_bundle(company_id)
    return bundle.to_dict()


@router.get("/{company_id}/interviews")
async def get_interview_experiences(
    company_id: str,
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(20, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
):
    """获取面试经验列表."""
    svc = get_company_review_service()
    items = await svc.get_interview_experiences(
        company_id, page=page, page_size=page_size
    )
    return {
        "company_id": company_id,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": i.id,
                "source": i.source,
                "job_title": i.job_title,
                "difficulty": i.difficulty,
                "experience": i.experience,
                "process": i.process,
                "questions": i.questions,
                "result": i.result,
                "created_at": i.created_at,
                "author": i.author,
            }
            for i in items
        ],
    }


@router.get("/{company_id}/salary")
async def get_salary_insights(
    company_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """获取公司薪资洞察 (中位数 + 分位 + 按岗位)."""
    svc = get_company_review_service()
    salary = await svc.get_salary_insights(company_id)
    return {
        "company_id": salary.company_id,
        "median_k": salary.median_k,
        "p25_k": salary.p25_k,
        "p75_k": salary.p75_k,
        "sample_size": salary.sample_size,
        "currency": salary.currency,
        "by_role": salary.by_role,
        "last_updated": salary.last_updated,
    }


@router.get("/{company_id}/reviews")
async def get_employee_reviews(
    company_id: str,
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(20, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
):
    """获取员工评价列表."""
    svc = get_company_review_service()
    items = await svc.get_employee_reviews(
        company_id, page=page, page_size=page_size
    )
    return {
        "company_id": company_id,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "source": r.source,
                "title": r.title,
                "content": r.content,
                "pros": r.pros,
                "cons": r.cons,
                "rating": r.rating,
                "job_title": r.job_title,
                "employment_status": r.employment_status,
                "created_at": r.created_at,
                "author": r.author,
                "helpful_count": r.helpful_count,
            }
            for r in items
        ],
    }