"""A/B 实验管理 API — T805.

CRUD experiment / 查看显著性结果 / 启停实验.
所有路由前缀 /api/admin/ab,需 admin 角色.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.ab_test import (
    BUILTIN_METRICS,
    Experiment,
    Variant,
    assign_variant,
    compute_significance,
    get_hash_salt,
    record_metric,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class VariantPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    weight: int = Field(..., ge=0, le=10000)
    config: dict[str, Any] = Field(default_factory=dict)


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    primary_metric: str = "match.score"
    variants: list[VariantPayload] = Field(..., min_length=2, max_length=8)


class ExperimentUpdate(BaseModel):
    description: Optional[str] = None
    primary_metric: Optional[str] = None
    variants: Optional[list[VariantPayload]] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class RecordMetricPayload(BaseModel):
    experiment_id: str
    variant: str
    metric_name: str
    value: float
    user_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_to_experiment(row: dict[str, Any]) -> Experiment:
    variants = [Variant(**v) for v in (row.get("variants") or [])]
    started = row.get("started_at")
    ended = row.get("ended_at")
    created = row.get("created_at") or datetime.now(timezone.utc).isoformat()
    updated = row.get("updated_at") or created
    if isinstance(started, str):
        started = datetime.fromisoformat(started.replace("Z", "+00:00"))
    if isinstance(ended, str):
        ended = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    return Experiment(
        id=row["id"],
        name=row["name"],
        description=row.get("description") or "",
        variants=variants,
        status=row.get("status") or "draft",
        started_at=started,
        ended_at=ended,
        primary_metric=row.get("primary_metric") or "match.score",
        created_at=created if isinstance(created, datetime)
        else datetime.fromisoformat(created.replace("Z", "+00:00")),
        updated_at=updated if isinstance(updated, datetime)
        else datetime.fromisoformat(updated.replace("Z", "+00:00")),
        metadata=row.get("metadata") or {},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/metrics")
async def list_builtin_metrics(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """A/B 实验内置指标清单,前端配置 variant / charts 时用."""
    return {"metrics": BUILTIN_METRICS, "hash_salt_preview": get_hash_salt()[:6] + "***"}


@router.post("/experiments", status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """创建一个新实验,初始状态 draft."""
    supabase = get_supabase_admin()
    body = {
        "name": payload.name,
        "description": payload.description,
        "primary_metric": payload.primary_metric,
        "variants": [v.model_dump() for v in payload.variants],
        "status": "draft",
    }
    res = supabase.table("experiments").insert(body).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create experiment")
    return {"data": res.data[0]}


@router.get("/experiments")
async def list_experiments(
    status: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """列出所有实验,可选按状态过滤."""
    supabase = get_supabase_admin()
    q = supabase.table("experiments").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return {"data": res.data or []}


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    res = (
        supabase.table("experiments").select("*").eq("id", experiment_id).single().execute()
    )
    if not res.data:
        raise HTTPException(404, "Experiment not found")
    return {"data": res.data}


@router.patch("/experiments/{experiment_id}")
async def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    body: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.description is not None:
        body["description"] = payload.description
    if payload.primary_metric is not None:
        body["primary_metric"] = payload.primary_metric
    if payload.variants is not None:
        body["variants"] = [v.model_dump() for v in payload.variants]
    if payload.status is not None:
        body["status"] = payload.status
    if payload.metadata is not None:
        body["metadata"] = payload.metadata
    res = (
        supabase.table("experiments")
        .update(body)
        .eq("id", experiment_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Experiment not found")
    return {"data": res.data[0]}


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """启动实验 (status=running, 记录 started_at)."""
    supabase = get_supabase_admin()
    res = (
        supabase.table("experiments")
        .update(
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", experiment_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Experiment not found")
    return {"data": res.data[0]}


@router.post("/experiments/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """停止实验 — 设置 status=stopped + ended_at, 不删除数据."""
    supabase = get_supabase_admin()
    res = (
        supabase.table("experiments")
        .update(
            {
                "status": "stopped",
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", experiment_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Experiment not found")
    return {"data": res.data[0]}


@router.delete("/experiments/{experiment_id}")
async def delete_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    supabase = get_supabase_admin()
    res = supabase.table("experiments").delete().eq("id", experiment_id).execute()
    return {"deleted": len(res.data or [])}


@router.get("/experiments/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    metric_name: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """计算并返回某实验在指定 metric 上的显著性结果.

    metric_name 不传时用实验的 primary_metric.
    """
    supabase = get_supabase_admin()
    exp_res = (
        supabase.table("experiments").select("*").eq("id", experiment_id).single().execute()
    )
    if not exp_res.data:
        raise HTTPException(404, "Experiment not found")
    experiment = _row_to_experiment(exp_res.data)
    metric = metric_name or experiment.primary_metric

    # 优先读 Supabase 持久化的指标 (生产环境使用)
    samples = []
    try:
        from datetime import datetime, timedelta
        since = datetime.now(timezone.utc) - timedelta(days=90)
        ms = (
            supabase.table("experiment_metrics")
            .select("variant,value")
            .eq("experiment_id", experiment_id)
            .eq("metric_name", metric)
            .gte("recorded_at", since.isoformat())
            .execute()
        )
        samples = ms.data or []
    except Exception:  # noqa: BLE001
        samples = []

    # 兼容内存 MetricStore (例如测试环境)
    if not samples:
        from services.ab_test import get_metric_store
        store = get_metric_store()
        for s in store.list(experiment_id=experiment_id, metric_name=metric):
            samples.append({"variant": s.variant, "value": s.value})

    by_variant: dict[str, list[float]] = {}
    for row in samples:
        by_variant.setdefault(row["variant"], []).append(float(row["value"]))

    # 用 compute_significance 形式的结果,补足 in-memory 计算路径
    if not by_variant:
        # 全部 variant 都构造 0 行,前端仍能看到完整 labels
        by_variant = {v.name: [] for v in experiment.variants}

    baseline = experiment.variants[0].name if experiment.variants else None
    results = _compute_inplace(baseline, by_variant)
    return {
        "data": {
            "experiment_id": experiment_id,
            "metric_name": metric,
            "baseline": baseline,
            **results,
        }
    }


def _compute_inplace(baseline: str | None, by_variant: dict[str, list[float]]) -> dict[str, Any]:
    """便利函数:复刻 compute_significance 的输出结构但跳过 store 依赖."""
    if not by_variant:
        return {
            "variants": [],
            "confidence": 0.0,
            "significant": False,
            "n_total": 0,
        }
    if baseline is None:
        baseline = sorted(by_variant.keys())[0]

    import math
    from services.ab_test import _norm_sf  # type: ignore

    def _stat(values):
        n = len(values)
        if n == 0:
            return 0.0, 0.0, 0
        mean = sum(values) / n
        if n < 2:
            return mean, 0.0, n
        var = sum((x - mean) ** 2 for x in values) / (n - 1)
        return mean, var, n

    base_mean, base_var, base_n = _stat(by_variant.get(baseline, []))
    variants: list[dict[str, Any]] = []
    best_p = 1.0
    n_total = 0
    for variant in sorted(by_variant.keys()):
        values = by_variant[variant]
        n_total += len(values)
        mean, var, n = _stat(values)
        if variant == baseline:
            lift = 0.0
            p_value = 1.0
        else:
            lift = (mean - base_mean) / base_mean if base_mean else 0.0
            if base_n >= 2 and n >= 2:
                se2 = (base_var / base_n) + (var / n)
                t = ((mean - base_mean) / math.sqrt(se2)) if se2 > 0 else 0.0
                p_value = min(2.0 * (1.0 - _norm_sf(-abs(t))), 1.0) if se2 > 0 else 1.0
            else:
                p_value = 1.0
        stddev = math.sqrt(var) if var > 0 else 0.0
        variants.append(
            {
                "name": variant,
                "mean": mean,
                "stddev": stddev,
                "n": n,
                "lift_vs_baseline": lift,
                "p_value": p_value,
                "is_baseline": variant == baseline,
            }
        )
        if variant != baseline and p_value < best_p:
            best_p = p_value
    return {
        "variants": variants,
        "confidence": max(0.0, 1.0 - best_p),
        "significant": (1.0 - best_p) >= 0.95,
        "n_total": n_total,
    }


@router.post("/record-metric", status_code=202)
async def post_record_metric(
    payload: RecordMetricPayload,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """手动注入一条指标样本 (供 pipeline 写不进去时手动补)."""
    record_metric(
        experiment_id=payload.experiment_id,
        variant=payload.variant,
        metric_name=payload.metric_name,
        value=payload.value,
    )
    return {"recorded": True}


@router.post("/assign-preview")
async def preview_assignment(
    payload: dict[str, Any],
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """根据传入的实验元数据 + user_id 预览 variant 分配 (前端 variants 编辑器调试)."""
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id required")
    variants = [Variant(**v) for v in payload.get("variants", [])]
    if not variants:
        raise HTTPException(400, "variants required")
    exp = Experiment(
        id="preview",
        name=payload.get("name") or "preview",
        description="",
        variants=variants,
        status=payload.get("status", "running"),
        primary_metric="match.score",
    )
    variant_name = assign_variant(exp, user_id)
    return {"user_id": user_id, "variant": variant_name}
