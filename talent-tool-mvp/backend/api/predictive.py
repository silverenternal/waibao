"""Predictive Analytics API (T2803) — LightGBM / Prophet endpoints.

Endpoints:
    GET  /api/predictive/attrition/{user_id}            单用户离职风险
    GET  /api/predictive/attrition/team/{org_id}        团队聚合 (HR 热力图)
    GET  /api/predictive/hire-success/{candidate_id}    候选人入职成功概率
    GET  /api/predictive/forecast                       时间序列预测
    POST /api/predictive/retrain                        手动触发重训 (admin)
    GET  /api/predictive/models                         列出已加载模型
    GET  /api/predictive/health                         端点 + 模型状态

Inference target: < 100ms per request (in-process LightGBM/Prophet).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import CurrentUser, get_current_user
from services.platform.predictive import (
    AttritionModel,
    HireSuccessModel,
    ProphetModel,
    get_attrition_model,
    get_hire_success_model,
    train_all_synthetic,
)

logger = logging.getLogger("recruittech.api.predictive")
router = APIRouter()


# ---------------------------------------------------------------------------
# Attrition
# ---------------------------------------------------------------------------
@router.get("/attrition/{user_id}", summary="单用户离职风险")
async def get_attrition(
    user_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    model = get_attrition_model()
    risk = model.predict(user_id)
    return risk.to_dict()


@router.get("/attrition/team/{org_id}", summary="团队聚合热力图")
async def get_team_attrition(
    org_id: str,
    user_ids: str = Query(..., description="comma-separated user IDs"),
    _user: CurrentUser = Depends(get_current_user),
):
    uids = [u for u in user_ids.split(",") if u]
    if not uids:
        raise HTTPException(status_code=400, detail="user_ids is required")
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids is required")
    model = get_attrition_model()
    out: list[dict] = []
    for uid in uids[:500]:  # cap
        out.append(model.predict(uid).to_dict())
    high = sum(1 for r in out if r["risk_level"] == "high")
    med = sum(1 for r in out if r["risk_level"] == "medium")
    low = sum(1 for r in out if r["risk_level"] == "low")
    return {
        "org_id": org_id,
        "n": len(out),
        "high": high,
        "medium": med,
        "low": low,
        "users": out,
    }


# ---------------------------------------------------------------------------
# Hire success
# ---------------------------------------------------------------------------
@router.get(
    "/hire-success/{candidate_id}",
    summary="候选人入职后成功概率",
)
async def get_hire_success(
    candidate_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    model = get_hire_success_model()
    score = model.predict(candidate_id)
    return score.to_dict()


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------
@router.get("/forecast", summary="时间序列预测")
async def get_forecast(
    metric: str = Query(default="candidate_inflow"),
    horizon_days: int = Query(default=30, ge=1, le=180),
    history_days: int = Query(default=90, ge=14, le=730),
    seed: str = Query(default="default"),
    _user: CurrentUser = Depends(get_current_user),
):
    pm = ProphetModel()
    result = pm.forecast(
        metric=metric,
        horizon_days=horizon_days,
        history_days=history_days,
        seed=seed,
    )
    return result.to_dict()


# ---------------------------------------------------------------------------
# Models / retrain / health
# ---------------------------------------------------------------------------
@router.get("/models", summary="已加载模型")
async def list_models(_user: CurrentUser = Depends(get_current_user)):
    am = get_attrition_model()
    hm = get_hire_success_model()
    return {
        "attrition": {
            "loaded": am.model is not None,
            "path": str(am._loaded_from) if am._loaded_from else None,
        },
        "hire_success": {
            "loaded": hm.model is not None,
        },
        "prophet_metric": ProphetModel().metric or None,
    }


@router.post("/retrain", summary="手动触发重训 (admin/hr)")
async def retrain(
    n: int = Query(default=2000, ge=100, le=20000),
    user: CurrentUser = Depends(get_current_user),
):
    if user.role.value not in ("admin", "hr", "talent_partner"):
        raise HTTPException(status_code=403, detail="admin/hr/talent_partner role required")
    t0 = time.time()
    result = train_all_synthetic(n=n)
    return {
        "status": "ok",
        "duration_seconds": round(time.time() - t0, 2),
        "metrics": result,
    }


@router.get("/health", summary="端点健康 + 模型状态")
async def health(_user: CurrentUser = Depends(get_current_user)):
    am = get_attrition_model()
    hm = get_hire_success_model()
    return {
        "ok": True,
        "attrition_loaded": am.model is not None,
        "hire_success_loaded": hm.model is not None,
        "models_dir": str(am._loaded_from.parent) if am._loaded_from else None,
    }
