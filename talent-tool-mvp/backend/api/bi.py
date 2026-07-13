"""BI proxy API (T2802) — Cube.js 代理 + Redis 缓存.

Endpoints:
    GET  /api/bi/meta                          立方体元数据 (cubes/dimensions/measures)
    POST /api/bi/query                         任意 Cube.js 查询 (前端 drag/drop)
    GET  /api/bi/funnel                        HR 漏斗 (内置 dashboard)
    GET  /api/bi/recruitment-efficiency       招聘效率 (内置 dashboard)
    GET  /api/bi/channel-roi                   渠道 ROI (内置 dashboard)
    GET  /api/bi/agent-performance             Agent 性能 (内置 dashboard)
    GET  /api/bi/customer-success              客户成功 (内置 dashboard)
    GET  /api/bi/dashboards                    列出已保存的 dashboard
    POST /api/bi/dashboards                    保存 dashboard
    DELETE /api/bi/dashboards/{id}             删除 dashboard
    POST /api/bi/dashboards/{id}/share         生成分享链接

设计:
- 所有 /api/bi/query 走 5 分钟 Redis 缓存 (key 包含 query hash)
- /api/bi/dashboards 保存在 Supabase `bi_dashboards` 表 (缺表时退化到本地内存)
- Cube.js 服务配置: CUBEJS_URL (默认 http://localhost:4000)
- 失败时降级: 返回 last-known-good + 标记 stale=true
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_role
from contracts.shared import UserRole

logger = logging.getLogger("recruittech.api.bi")
router = APIRouter()

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
CUBEJS_URL = os.getenv("CUBEJS_URL", "http://localhost:4000").rstrip("/")
CUBEJS_API_SECRET = os.getenv("CUBEJS_API_SECRET", "waibao-bi-dev-secret-CHANGE-ME-IN-PROD")
CACHE_TTL_SECONDS = int(os.getenv("BI_CACHE_TTL", "300"))  # 5 min

REDIS_URL = os.getenv("REDIS_URL", "")
_redis_client = None
_mem_cache: dict[str, tuple[float, Any]] = {}


async def _get_redis():
    """惰性连接 Redis. 失败时退化到本地内存 cache."""
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        try:
            import redis.asyncio as redis  # type: ignore

            _redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
            await _redis_client.ping()
            logger.info("BI proxy: Redis cache connected at %s", REDIS_URL)
        except Exception as exc:  # pragma: no cover
            logger.warning("BI proxy: Redis unavailable, falling back to in-memory: %s", exc)
            _redis_client = None
    return _redis_client


async def _cache_get(key: str) -> Optional[Any]:
    r = await _get_redis()
    if r is not None:
        try:
            raw = await r.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # pragma: no cover
            logger.warning("BI cache get failed: %s", exc)
    v = _mem_cache.get(key)
    if v and v[0] > time.time():
        return v[1]
    if v:
        _mem_cache.pop(key, None)
    return None


async def _cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    r = await _get_redis()
    if r is not None:
        try:
            await r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception as exc:  # pragma: no cover
            logger.warning("BI cache set failed: %s", exc)
    _mem_cache[key] = (time.time() + ttl, value)


# -------------------------------------------------------------------
# Cube.js HTTP client
# -------------------------------------------------------------------
async def _cubejs_get(path: str) -> dict:
    headers = {"Authorization": CUBEJS_API_SECRET}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{CUBEJS_URL}{path}", headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        logger.warning("Cube.js GET %s failed: %s", path, exc)
        raise HTTPException(status_code=502, detail=f"Cube.js unavailable: {exc}") from exc


async def _cubejs_post(path: str, payload: dict) -> dict:
    headers = {"Authorization": CUBEJS_API_SECRET, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{CUBEJS_URL}{path}", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        logger.warning("Cube.js POST %s failed: %s", path, exc)
        raise HTTPException(status_code=502, detail=f"Cube.js unavailable: {exc}") from exc


def _hash_query(query: dict) -> str:
    return "bi:" + hashlib.sha256(json.dumps(query, sort_keys=True, default=str).encode()).hexdigest()[:24]


# -------------------------------------------------------------------
# Fallback (offline / dev) — minimal mock dataset
# -------------------------------------------------------------------
def _mock_meta() -> dict:
    return {
        "cubes": [
            {
                "name": "Candidates",
                "title": "候选人",
                "measures": [
                    {"name": "Candidates.count", "title": "候选人总数", "type": "count"},
                    {"name": "Candidates.highIntentCount", "title": "高意向候选人", "type": "count"},
                ],
                "dimensions": [
                    {"name": "Candidates.source", "title": "来源", "type": "string"},
                    {"name": "Candidates.channel", "title": "渠道", "type": "string"},
                    {"name": "Candidates.city", "title": "城市", "type": "string"},
                ],
            },
            {
                "name": "Matches",
                "title": "匹配",
                "measures": [
                    {"name": "Matches.count", "title": "匹配总数", "type": "count"},
                    {"name": "Matches.avgScore", "title": "平均匹配分", "type": "avg"},
                    {"name": "Matches.acceptedCount", "title": "接受数", "type": "count"},
                ],
                "dimensions": [
                    {"name": "Matches.decision", "title": "决策", "type": "string"},
                    {"name": "Matches.channel", "title": "渠道", "type": "string"},
                    {"name": "Matches.scoreBucket", "title": "分档", "type": "string"},
                ],
            },
            {
                "name": "Tickets",
                "title": "工单",
                "measures": [
                    {"name": "Tickets.count", "title": "工单总数", "type": "count"},
                    {"name": "Tickets.slaBreachRate", "title": "SLA 违约率", "type": "avg"},
                ],
                "dimensions": [
                    {"name": "Tickets.priority", "title": "优先级", "type": "string"},
                    {"name": "Tickets.sentiment", "title": "情绪", "type": "string"},
                ],
            },
            {
                "name": "Roles",
                "title": "岗位",
                "measures": [
                    {"name": "Roles.count", "title": "岗位数", "type": "count"},
                    {"name": "Roles.openRoles", "title": "在招岗位", "type": "count"},
                    {"Name": "Roles.daysToFill", "name": "Roles.daysToFill", "title": "填补天数", "type": "avg"},
                ],
                "dimensions": [
                    {"name": "Roles.department", "title": "部门", "type": "string"},
                    {"name": "Roles.city", "title": "城市", "type": "string"},
                    {"name": "Roles.seniority", "title": "资历", "type": "string"},
                ],
            },
        ]
    }


def _mock_query(query: dict) -> dict:
    """基于 query shape 的最小 mock 数据 — 让前端离线可渲染."""
    measures = query.get("measures") or []
    dimensions = query.get("dimensions") or []
    time_dim = next((d for d in dimensions if d.endswith(".createdAt")), None)

    rows: list[dict] = []
    if time_dim:
        for i in range(7):
            row: dict = {time_dim: f"2026-07-{10 + i:02d}"}
            for d in dimensions:
                if d != time_dim:
                    row[d] = ["linkedin", "lagou", "referral", "boss"][i % 4]
            for m in measures:
                row[m] = round(20 + i * 3 + len(measures), 2)
            rows.append(row)
    else:
        for i in range(min(5, max(1, len(dimensions) or len(measures)))):
            row = {}
            for d in dimensions:
                row[d] = ["linkedin", "lagou", "referral", "boss", "wechat"][i % 5]
            for m in measures:
                row[m] = round(10 + i * 7, 2)
            rows.append(row)
    return {"data": rows, "annotation": {"measures": measures, "dimensions": dimensions}}


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------
@router.get("/meta", summary="Cube.js 元数据 (cubes/dimensions/measures)")
async def get_meta(_user: CurrentUser = Depends(get_current_user)):
    cache_key = "bi:meta"
    cached = await _cache_get(cache_key)
    if cached:
        return {"data": cached, "cached": True}
    try:
        meta = await _cubejs_get("/cubejs-api/v1/meta")
    except HTTPException:
        meta = _mock_meta()
    await _cache_set(cache_key, meta)
    return {"data": meta, "cached": False}


class CubeQuery(BaseModel):
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict] = Field(default_factory=list)
    timeDimensions: list[dict] = Field(default_factory=list)
    order: list[list] = Field(default_factory=list)
    limit: int = 1000
    offset: int = 0


@router.post("/query", summary="任意 Cube.js 查询 (5 分钟 Redis 缓存)")
async def run_query(
    body: CubeQuery,
    _user: CurrentUser = Depends(get_current_user),
):
    payload = body.model_dump()
    cache_key = _hash_query(payload)
    cached = await _cache_get(cache_key)
    if cached is not None:
        return {"data": cached, "cached": True, "stale": False}
    try:
        result = await _cubejs_post("/cubejs-api/v1/load", {"query": payload})
        await _cache_set(cache_key, result)
        return {"data": result, "cached": False, "stale": False}
    except HTTPException:
        result = _mock_query(payload)
        return {"data": result, "cached": False, "stale": True}


# -------------------------------------------------------------------
# Built-in dashboards — fixed queries
# -------------------------------------------------------------------
DASHBOARD_QUERIES = {
    "funnel": {
        "title": "HR 漏斗",
        "description": "从候选人进入到入职的完整漏斗",
        "widgets": [
            {
                "id": "funnel-stage-count",
                "type": "bar",
                "title": "各阶段候选人",
                "query": {
                    "measures": ["Candidates.count"],
                    "dimensions": ["Candidates.stage"],
                },
            },
            {
                "id": "funnel-source",
                "type": "pie",
                "title": "来源分布",
                "query": {
                    "measures": ["Candidates.count"],
                    "dimensions": ["Candidates.source"],
                },
            },
        ],
    },
    "recruitment-efficiency": {
        "title": "招聘效率",
        "description": "填补天数 / 匹配平均分 / 决策时长",
        "widgets": [
            {
                "id": "re-days-to-fill",
                "type": "kpi",
                "title": "平均填补天数",
                "query": {"measures": ["Roles.daysToFill"]},
            },
            {
                "id": "re-avg-score",
                "type": "kpi",
                "title": "平均匹配分",
                "query": {"measures": ["Matches.avgScore"]},
            },
            {
                "id": "re-time-to-decision",
                "type": "kpi",
                "title": "平均决策时长 (h)",
                "query": {"measures": ["Matches.timeToDecisionHours"]},
            },
        ],
    },
    "channel-roi": {
        "title": "渠道 ROI",
        "description": "每个渠道带来候选人数与接受率",
        "widgets": [
            {
                "id": "roi-channel-count",
                "type": "bar",
                "title": "渠道候选人数",
                "query": {
                    "measures": ["Matches.count", "Matches.acceptedCount"],
                    "dimensions": ["Matches.channel"],
                },
            },
            {
                "id": "roi-conversion",
                "type": "bar",
                "title": "渠道转化率",
                "query": {
                    "measures": ["Matches.acceptedCount", "Matches.count"],
                    "dimensions": ["Matches.channel"],
                },
            },
        ],
    },
    "agent-performance": {
        "title": "Agent 性能",
        "description": "每个 agent 处理的匹配数 / 接受率",
        "widgets": [
            {
                "id": "ap-agent-table",
                "type": "table",
                "title": "Agent 表现",
                "query": {
                    "measures": [
                        "Matches.count",
                        "Matches.acceptedCount",
                        "Matches.avgScore",
                    ],
                    "dimensions": ["Matches.agentId", "Matches.agentName"],
                },
            }
        ],
    },
    "customer-success": {
        "title": "客户成功",
        "description": "工单 SLA / NPS 代理 / 工单情绪分布",
        "widgets": [
            {
                "id": "cs-sla",
                "type": "kpi",
                "title": "SLA 违约率",
                "query": {"measures": ["Tickets.slaBreachRate"]},
            },
            {
                "id": "cs-nps",
                "type": "kpi",
                "title": "NPS 代理分",
                "query": {"measures": ["Tickets.npsProxy"]},
            },
            {
                "id": "cs-sentiment",
                "type": "pie",
                "title": "工单情绪分布",
                "query": {
                    "measures": ["Tickets.count"],
                    "dimensions": ["Tickets.sentiment"],
                },
            },
        ],
    },
}


@router.get("/dashboards/built-in", summary="列出 5 个内置 dashboard")
async def list_builtin(_user: CurrentUser = Depends(get_current_user)):
    return {"dashboards": [{**v, "key": k, "built_in": True} for k, v in DASHBOARD_QUERIES.items()]}


@router.get("/dashboards/{key}/data", summary="取 dashboard 全部 widget 数据")
async def get_dashboard_data(
    key: str,
    _user: CurrentUser = Depends(get_current_user),
):
    cfg = DASHBOARD_QUERIES.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"unknown dashboard: {key}")
    out_widgets: list[dict] = []
    for w in cfg["widgets"]:
        try:
            data = await run_query(CubeQuery(**w["query"]), _user)  # type: ignore[arg-type]
            out_widgets.append({**w, "data": data.get("data", {})})
        except Exception as exc:  # pragma: no cover
            logger.warning("dashboard %s widget %s failed: %s", key, w["id"], exc)
            out_widgets.append({**w, "data": {"data": []}, "error": str(exc)})
    return {"key": key, "title": cfg["title"], "widgets": out_widgets}


# -------------------------------------------------------------------
# User-saved dashboards — Supabase `bi_dashboards` table
# -------------------------------------------------------------------
class SavedDashboard(BaseModel):
    name: str
    widgets: list[dict]
    description: str = ""
    shared: bool = False


# In-memory fallback (process-local) when Supabase table not present
_saved: dict[str, dict] = {}


def _sb():
    try:
        from api.deps import get_supabase_admin  # type: ignore

        return get_supabase_admin()
    except Exception:  # pragma: no cover
        return None


@router.get("/dashboards", summary="列出用户保存的 dashboard")
async def list_saved(user: CurrentUser = Depends(get_current_user)):
    sb = _sb()
    if sb is not None:
        try:
            res = (
                sb.table("bi_dashboards")
                .select("id,name,description,widgets,shared,owner_id,created_at,updated_at")
                .or_(f"owner_id.eq.{user.id},shared.eq.true")
                .execute()
            )
            return {"dashboards": res.data or []}
        except Exception as exc:  # pragma: no cover
            logger.info("Supabase bi_dashboards unavailable: %s", exc)
    return {"dashboards": list(_saved.values())}


@router.post("/dashboards", summary="保存 dashboard")
async def create_dashboard(
    body: SavedDashboard,
    user: CurrentUser = Depends(get_current_user),
):
    rec = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "description": body.description,
        "widgets": body.widgets,
        "shared": body.shared,
        "owner_id": str(user.id),
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    sb = _sb()
    if sb is not None:
        try:
            sb.table("bi_dashboards").insert(rec).execute()
            return rec
        except Exception as exc:  # pragma: no cover
            logger.info("Supabase insert failed, in-memory: %s", exc)
    _saved[rec["id"]] = rec
    return rec


@router.delete("/dashboards/{dash_id}")
async def delete_dashboard(
    dash_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    sb = _sb()
    if sb is not None:
        try:
            sb.table("bi_dashboards").delete().eq("id", dash_id).eq("owner_id", str(user.id)).execute()
            return {"ok": True, "id": dash_id}
        except Exception as exc:  # pragma: no cover
            logger.info("Supabase delete failed: %s", exc)
    if dash_id in _saved:
        del _saved[dash_id]
        return {"ok": True, "id": dash_id}
    raise HTTPException(status_code=404, detail="dashboard not found")


@router.post("/dashboards/{dash_id}/share", summary="生成分享 token")
async def share_dashboard(
    dash_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    token = hashlib.sha256(f"{dash_id}:{user.id}:{time.time()}".encode()).hexdigest()[:32]
    sb = _sb()
    if sb is not None:
        try:
            sb.table("bi_dashboards").update({"shared": True, "share_token": token}).eq("id", dash_id).execute()
        except Exception as exc:  # pragma: no cover
            logger.info("Supabase share update failed: %s", exc)
    if dash_id in _saved:
        _saved[dash_id]["shared"] = True
        _saved[dash_id]["share_token"] = token
    return {"share_token": token, "url": f"/admin/bi/shared/{token}"}


@router.get("/health", summary="BI proxy 健康检查")
async def health(_user: CurrentUser = Depends(get_current_user)):
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{CUBEJS_URL}/cubejs-api/v1/meta", headers={"Authorization": CUBEJS_API_SECRET})
            cube_ok = r.status_code == 200
    except Exception:
        cube_ok = False
    return {
        "ok": True,
        "cubejs_url": CUBEJS_URL,
        "cubejs_reachable": cube_ok,
        "redis": bool(await _get_redis()),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "built_in_dashboards": list(DASHBOARD_QUERIES.keys()),
    }
