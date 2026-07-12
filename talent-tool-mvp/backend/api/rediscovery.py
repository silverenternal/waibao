"""Rediscovery API (T2406).

Endpoints:
    GET  /api/rediscovery/candidates        — 沉睡候选人列表 (HR 主动激活面板)
    GET  /api/rediscovery/candidates/{id}/preview — 单个候选人激活预览
    POST /api/rediscovery/{candidate_id}/activate  — 发送激活消息
    GET  /api/rediscovery/stats             — 激活转化率
    GET  /api/rediscovery/strategies        — 策略档位
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.integrations.candidate_rediscovery import (
    DORMANT_THRESHOLD_DAYS,
    ActivationStrategy,
    HeuristicLLMJudge,
    STRATEGY_THRESHOLDS,
    get_rediscovery_service,
)

logger = logging.getLogger("recruittech.api.rediscovery")
router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ActivateRequest(BaseModel):
    strategy: str = Field("standard", description="conservative/standard/aggressive")
    channel: str = Field("im", description="im/email/sms/dingtalk")
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Mock data (真实场景从 DB 取)
# ---------------------------------------------------------------------------

SAMPLE_CANDIDATES = [
    {
        "id": "cand-001",
        "name": "赵明 (前端工程师)",
        "email": "zhao@example.com",
        "last_active_at": "2025-09-10T00:00:00+00:00",
        "job_titles": ["前端工程师", "高级前端"],
        "skills": ["React", "TypeScript", "Next.js", "Tailwind"],
        "city": "上海",
        "seniority": "senior",
        "salary_expect": 45000,
    },
    {
        "id": "cand-002",
        "name": "孙丽 (后端架构)",
        "email": "sun@example.com",
        "last_active_at": "2025-08-01T00:00:00+00:00",
        "job_titles": ["后端工程师", "技术负责人"],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Kubernetes"],
        "city": "北京",
        "seniority": "lead",
        "salary_expect": 60000,
    },
    {
        "id": "cand-003",
        "name": "周强 (产品经理)",
        "email": "zhou@example.com",
        "last_active_at": "2025-11-20T00:00:00+00:00",
        "job_titles": ["产品经理"],
        "skills": ["需求分析", "Axure", "数据驱动"],
        "city": "深圳",
        "seniority": "senior",
        "salary_expect": 35000,
    },
    {
        "id": "cand-004",
        "name": "吴芳 (UI 设计师)",
        "email": "wu@example.com",
        "last_active_at": "2026-06-15T00:00:00+00:00",  # 活跃
        "job_titles": ["UI 设计师"],
        "skills": ["Figma", "设计系统"],
        "city": "杭州",
        "seniority": "mid",
        "salary_expect": 25000,
    },
]

SAMPLE_NEW_ROLES = [
    {
        "id": "role-1",
        "title": "高级前端工程师",
        "required_skills": ["React", "TypeScript", "Next.js"],
    },
    {
        "id": "role-2",
        "title": "资深后端架构师",
        "required_skills": ["Python", "FastAPI", "PostgreSQL"],
    },
    {
        "id": "role-3",
        "title": "产品经理 (AI 方向)",
        "required_skills": ["需求分析", "数据驱动"],
    },
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/candidates")
async def list_sleepy(
    strategy: str = Query("standard", description="conservative/standard/aggressive"),
    user: CurrentUser = Depends(get_current_user),
):
    """HR 主动激活面板: 沉睡候选人列表."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    if strategy not in STRATEGY_THRESHOLDS:
        raise HTTPException(status_code=400, detail=f"unknown strategy: {strategy}")

    svc = get_rediscovery_service(judge=HeuristicLLMJudge())
    sleepy = svc.find_dormant(SAMPLE_CANDIDATES, SAMPLE_NEW_ROLES, strategy=strategy)
    return {
        "strategy": strategy,
        "threshold_days": DORMANT_THRESHOLD_DAYS,
        "count": len(sleepy),
        "candidates": sleepy,
    }


@router.get("/candidates/{candidate_id}/preview")
async def preview_candidate(
    candidate_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """单个候选人激活预览 — 含消息草稿."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_rediscovery_service(judge=HeuristicLLMJudge())
    # 找到该候选人
    candidate = next((c for c in SAMPLE_CANDIDATES if c["id"] == candidate_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate not found")
    sleepy = svc.find_dormant([candidate], SAMPLE_NEW_ROLES, strategy="aggressive")
    if not sleepy:
        raise HTTPException(status_code=404, detail="candidate is not dormant")
    c = sleepy[0]
    top = c.get("recommended_roles", [{}])[0] if c.get("recommended_roles") else None
    message = svc.build_activation_message(c, top)
    return {
        "candidate": c,
        "preview_message": message,
        "suggested_strategy": svc.strategy_for(c["rediscover_potential"]),
    }


@router.post("/{candidate_id}/activate")
async def activate_candidate(
    candidate_id: str,
    body: ActivateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """发送激活消息."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_rediscovery_service(judge=HeuristicLLMJudge())

    candidate_data = next((c for c in SAMPLE_CANDIDATES if c["id"] == candidate_id), None)
    if not candidate_data:
        raise HTTPException(status_code=404, detail="candidate not found")

    # 计算候选人画像
    sleepy = svc.find_dormant([candidate_data], SAMPLE_NEW_ROLES, strategy="aggressive")
    if not sleepy:
        raise HTTPException(status_code=404, detail="candidate is not dormant")
    c = sleepy[0]
    log = svc.build_activation_log(
        candidate_id=candidate_id,
        triggered_by=user.id,
        strategy=body.strategy,
        channel=body.channel,
        candidate=c,
        message=body.message,
    )
    logger.info(
        "rediscovery.activate candidate=%s strategy=%s channel=%s",
        candidate_id,
        body.strategy,
        body.channel,
    )
    return {"status": "queued", "log": log}


@router.get("/stats")
async def stats(
    user: CurrentUser = Depends(get_current_user),
):
    """激活转化率统计."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_rediscovery_service()
    # Demo 历史日志
    logs = [
        {"strategy": "conservative", "converted": True, "channel": "im"},
        {"strategy": "conservative", "converted": True, "channel": "im"},
        {"strategy": "conservative", "converted": False, "channel": "email"},
        {"strategy": "standard", "converted": True, "channel": "im"},
        {"strategy": "standard", "converted": False, "channel": "im"},
        {"strategy": "standard", "converted": False, "channel": "email"},
        {"strategy": "aggressive", "converted": False, "channel": "im"},
        {"strategy": "aggressive", "converted": False, "channel": "sms"},
        {"strategy": "aggressive", "converted": True, "channel": "dingtalk"},
        {"strategy": "aggressive", "converted": False, "channel": "im"},
    ]
    return svc.compute_stats(logs)


@router.get("/strategies")
async def list_strategies():
    """3 档策略说明."""
    return {
        "strategies": [
            {
                "name": "conservative",
                "threshold": STRATEGY_THRESHOLDS["conservative"],
                "description": "仅对高潜力候选人激活, 转化率最高但覆盖率低",
            },
            {
                "name": "standard",
                "threshold": STRATEGY_THRESHOLDS["standard"],
                "description": "平衡策略: 中高潜力候选人 (默认)",
            },
            {
                "name": "aggressive",
                "threshold": STRATEGY_THRESHOLDS["aggressive"],
                "description": "全量激活: 高覆盖, 适合需要补充候选人库的岗位",
            },
        ]
    }
