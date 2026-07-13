"""T2801 — Analytics v2 API (ClickHouse + 多维度下钻).

设计目标:
  - 99% 查询 < 100ms (走 ClickHouse 列存 + 预聚合)
  - 多维度下钻: 时间 / 渠道 / 地区 / 行业 / 业务线
  - 不阻塞主 OLTP 库
  - 缓存热点 (in-process LRU + 后续可换 Redis)

Endpoints:
  GET /api/analytics-v2/health                            ClickHouse 健康
  GET /api/analytics-v2/funnel                            招聘漏斗 (全公司)
  GET /api/analytics-v2/funnel/by-channel                 按渠道拆
  GET /api/analytics-v2/funnel/by-country                 按地区拆
  GET /api/analytics-v2/matches/trend                     匹配量 + 转化趋势
  GET /api/analytics-v2/matches/top-jobs                  Top 招聘最快关闭的岗位
  GET /api/analytics-v2/candidates/cohort                 候选人 cohort 留存
  GET /api/analytics-v2/sla/daily                         每日 SLA (用 AggregatingMergeTree)
  GET /api/analytics-v2/sla/breakdown                     按优先级拆
  GET /api/analytics-v2/admin/etl/status                  调度状态
  POST /api/analytics-v2/admin/etl/run                    立即触发一次 ETL
"""
from __future__ import annotations

import functools
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user, require_admin
from services.warehouse import (
    ClickHouseClient,
    ETLScheduler,
    get_clickhouse_client,
    get_scheduler,
)

logger = logging.getLogger("waibao.api.analytics_v2")
router = APIRouter(prefix="/api/analytics-v2", tags=["analytics-v2"])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
class TimedResult(BaseModel):
    """统一返回结构, 包含耗时, 方便客户端监控."""
    took_ms: float
    row_count: int
    data: list[dict[str, Any]]


def timed_query(fn: Callable[..., list[dict[str, Any]]]) -> Callable[..., TimedResult]:
    """包装器: 测耗时, 限制最大返回行数, 异常时返回 5xx."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> TimedResult:
        t0 = time.perf_counter()
        try:
            rows = fn(*args, **kwargs) or []
        except HTTPException:
            raise  # 让 FastAPI 自己处理 (4xx 是客户端问题, 不该是 5xx)
        except Exception as e:  # noqa: BLE001
            logger.exception("analytics-v2 query failed")
            raise HTTPException(status_code=503, detail=f"warehouse unavailable: {e}") from e
        took = (time.perf_counter() - t0) * 1000
        return TimedResult(took_ms=round(took, 2), row_count=len(rows), data=rows)
    return wrapper


def _ch() -> ClickHouseClient:
    return get_clickhouse_client()


# 强制管理员
def _admin(user: CurrentUser = Depends(require_admin)) -> CurrentUser:
    return user


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@router.get("/health")
def health() -> dict[str, Any]:
    info = _ch().health()
    info["scheduler"] = get_scheduler().status()
    return info


# ---------------------------------------------------------------------------
# 1) 漏斗
# ---------------------------------------------------------------------------
FUNNEL_STAGES = ["applied", "screened", "interviewed", "offered", "hired"]


@router.get("/funnel", response_model=TimedResult)
@timed_query
def funnel_overall(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
) -> list[dict[str, Any]]:
    """招聘漏斗: 30 天默认. 用 application 的 stage 累计."""
    sql = """
    SELECT
      stage,
      uniqExact(candidate_id) AS candidates
    FROM marts.fct_applications
    WHERE event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY stage
    ORDER BY indexOf(['applied','screened','interviewed','offered','hired'], stage)
    """
    tenant_clause = "AND tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


@router.get("/funnel/by-channel", response_model=TimedResult)
@timed_query
def funnel_by_channel(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
) -> list[dict[str, Any]]:
    """按 source_channel 拆解漏斗."""
    sql = """
    SELECT
      source_channel AS channel,
      stage,
      uniqExact(candidate_id) AS candidates
    FROM marts.fct_applications
    WHERE event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY channel, stage
    ORDER BY channel, indexOf(['applied','screened','interviewed','offered','hired'], stage)
    """
    tenant_clause = "AND tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


@router.get("/funnel/by-country", response_model=TimedResult)
@timed_query
def funnel_by_country(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """按候选人地区拆解. Join dim_candidates."""
    sql = """
    SELECT
      c.country,
      a.stage,
      uniqExact(a.candidate_id) AS candidates
    FROM marts.fct_applications a
    LEFT JOIN marts.dim_candidates c ON c.id = a.candidate_id
    WHERE a.event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY c.country, a.stage
    ORDER BY candidates DESC
    LIMIT :limit
    """
    tenant_clause = "AND a.tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "tenant": tenant_id or "",
            "limit": limit,
        },
    )


# ---------------------------------------------------------------------------
# 2) Match 趋势
# ---------------------------------------------------------------------------
@router.get("/matches/trend", response_model=TimedResult)
@timed_query
def matches_trend(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
    granularity: str = Query("day", pattern="^(hour|day|week|month)$"),
) -> list[dict[str, Any]]:
    sql = """
    SELECT
      {bucket} AS bucket,
      count() AS matches,
      uniqExact(candidate_id) AS candidates,
      uniqExact(job_id) AS jobs,
      avg(score) AS avg_score,
      sum(is_accepted) AS accepted
    FROM marts.fct_matches
    WHERE event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY bucket
    ORDER BY bucket
    """
    bucket_expr = {
        "hour": "toStartOfHour(matched_at)",
        "day": "toDate(matched_at)",
        "week": "toStartOfWeek(matched_at)",
        "month": "toStartOfMonth(matched_at)",
    }[granularity]
    tenant_clause = "AND tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(bucket=bucket_expr, tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


@router.get("/matches/top-jobs", response_model=TimedResult)
@timed_query
def top_matched_jobs(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """匹配数 Top 岗位 (含接受率)."""
    sql = """
    SELECT
      j.id AS job_id,
      j.title,
      j.industry,
      j.country,
      count() AS matches,
      sum(m.is_accepted) AS accepted,
      round(avg(m.score), 3) AS avg_score
    FROM marts.fct_matches m
    LEFT JOIN marts.dim_jobs j ON j.id = m.job_id
    WHERE m.event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY j.id, j.title, j.industry, j.country
    ORDER BY matches DESC
    LIMIT :limit
    """
    tenant_clause = "AND m.tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "tenant": tenant_id or "",
            "limit": limit,
        },
    )


# ---------------------------------------------------------------------------
# 3) 留存 cohort
# ---------------------------------------------------------------------------
@router.get("/candidates/cohort", response_model=TimedResult)
@timed_query
def candidate_retention_cohort(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=90)),
    end: date = Query(default_factory=date.today),
) -> list[dict[str, Any]]:
    """按注册日 cohort, 计算 1/7/14/30 天的回访率 (回访 = 投递 / 匹配)."""
    sql = """
    WITH
      toDate(c.created_at) AS cohort_day,
      toDate(m.matched_at) AS activity_day
    SELECT
      cohort_day,
      count(DISTINCT c.id) AS cohort_size,
      count(DISTINCT if(dateDiff('day', cohort_day, activity_day) = 1, c.id, null)) AS d1,
      count(DISTINCT if(dateDiff('day', cohort_day, activity_day) = 7, c.id, null)) AS d7,
      count(DISTINCT if(dateDiff('day', cohort_day, activity_day) = 14, c.id, null)) AS d14,
      count(DISTINCT if(dateDiff('day', cohort_day, activity_day) = 30, c.id, null)) AS d30
    FROM marts.dim_candidates c
    LEFT JOIN marts.fct_matches m ON m.candidate_id = c.id
    WHERE cohort_day BETWEEN :start AND :end
    {tenant}
    GROUP BY cohort_day
    ORDER BY cohort_day
    """
    tenant_clause = "AND c.tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


# ---------------------------------------------------------------------------
# 4) SLA
# ---------------------------------------------------------------------------
@router.get("/sla/daily", response_model=TimedResult)
@timed_query
def sla_daily(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
) -> list[dict[str, Any]]:
    """每日 SLA. 用 -State/-Merge 拿实时结果."""
    sql = """
    SELECT
      event_date,
      countMerge(ticket_count) AS tickets,
      countMerge(sla_met_count) AS sla_met,
      round(
        countMerge(sla_met_count) / nullIf(countMerge(ticket_count), 0), 4
      ) AS sla_rate,
      round(avgMerge(avg_first_response_min), 1) AS avg_first_min,
      round(quantileMerge(0.95)(p95_first_response_min), 1) AS p95_first_min,
      round(avgMerge(avg_resolution_min), 1) AS avg_resolve_min,
      round(quantileMerge(0.95)(p95_resolution_min), 1) AS p95_resolve_min
    FROM marts.fct_sla_metrics
    WHERE event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY event_date
    ORDER BY event_date
    """
    tenant_clause = "AND tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


@router.get("/sla/breakdown", response_model=TimedResult)
@timed_query
def sla_breakdown(
    tenant_id: Optional[str] = Query(None),
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
) -> list[dict[str, Any]]:
    """按 priority 拆 SLA."""
    sql = """
    SELECT
      priority,
      countMerge(ticket_count) AS tickets,
      countMerge(sla_met_count) AS sla_met,
      round(
        countMerge(sla_met_count) / nullIf(countMerge(ticket_count), 0), 4
      ) AS sla_rate,
      round(avgMerge(avg_first_response_min), 1) AS avg_first_min,
      round(avgMerge(avg_resolution_min), 1) AS avg_resolve_min
    FROM marts.fct_sla_metrics
    WHERE event_date BETWEEN :start AND :end
    {tenant}
    GROUP BY priority
    ORDER BY priority
    """
    tenant_clause = "AND tenant_id = :tenant" if tenant_id else ""
    return _ch().query(
        sql.format(tenant=tenant_clause),
        {"start": start.isoformat(), "end": end.isoformat(), "tenant": tenant_id or ""},
    )


# ---------------------------------------------------------------------------
# 5) Admin: ETL
# ---------------------------------------------------------------------------
@router.get("/admin/etl/status")
def etl_status(_: CurrentUser = Depends(_admin)) -> dict[str, Any]:
    return get_scheduler().status()


@router.post("/admin/etl/run")
def etl_run_now(_: CurrentUser = Depends(_admin)) -> dict[str, Any]:
    result = get_scheduler().run_now()
    return result.to_dict()


# ---------------------------------------------------------------------------
# 6) Generic multi-dim drilldown (高级用法, 给 BI 用)
# ---------------------------------------------------------------------------
class DrilldownRequest(BaseModel):
    table: str
    dimensions: list[str]
    metrics: list[str]
    filters: dict[str, Any] = {}
    start: Optional[date] = None
    end: Optional[date] = None
    limit: int = 1000


# 白名单: 安全第一
ALLOWED_DRILLDOWN_TABLES = {
    "marts.fct_matches",
    "marts.fct_applications",
    "marts.dim_candidates",
    "marts.dim_jobs",
    "marts.fct_sla_metrics",
}
ALLOWED_DRILLDOWN_COLUMNS = {
    "event_date", "matched_at", "created_at", "tenant_id", "channel", "stage",
    "country", "industry", "city", "priority", "status", "experience_band",
    "is_accepted", "score", "is_open",
}
# metric 名 -> SQL 表达式
ALLOWED_DRILLDOWN_METRICS = {
    "count", "uniq_candidates", "uniq_jobs", "avg_score", "is_accepted_sum",
}


@router.post("/drilldown", response_model=TimedResult)
@timed_query
def drilldown(req: DrilldownRequest, user: CurrentUser = Depends(_admin)) -> list[dict[str, Any]]:
    """多维度下钻. 维度 / 指标走白名单, 防止 SQL 注入."""
    if req.table not in ALLOWED_DRILLDOWN_TABLES:
        raise HTTPException(400, f"table not allowed: {req.table}")
    for d in req.dimensions:
        if d not in ALLOWED_DRILLDOWN_COLUMNS:
            raise HTTPException(400, f"dimension not allowed: {d}")
    for m in req.metrics:
        if m not in ALLOWED_DRILLDOWN_METRICS:
            raise HTTPException(400, f"metric not allowed: {m}")

    # 简单 metric 转 SQL expr
    metric_expr = {
        "count": "count()",
        "uniq_candidates": "uniqExact(candidate_id)",
        "uniq_jobs": "uniqExact(job_id)",
        "avg_score": "avg(score)",
        "is_accepted_sum": "sum(is_accepted)",
    }
    metric_cols = ", ".join(f"{metric_expr.get(m, m)} AS {m}" for m in req.metrics)
    dim_cols = ", ".join(req.dimensions)
    sql = f"SELECT {dim_cols}, {metric_cols} FROM {req.table}"
    if req.start and req.end:
        sql += " WHERE event_date BETWEEN :start AND :end"
    if req.dimensions:
        sql += f" GROUP BY {dim_cols} ORDER BY {req.dimensions[0]}"
    sql += f" LIMIT {int(req.limit)}"

    params: dict[str, Any] = {}
    if req.start and req.end:
        params["start"] = req.start.isoformat()
        params["end"] = req.end.isoformat()
    return _ch().query(sql, params)
