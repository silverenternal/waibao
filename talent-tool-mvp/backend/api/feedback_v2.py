"""v8.0 T3902 — 用户反馈统一入口 API v2.

设计:
- POST /api/feedback/v2                  收集反馈 (rating/bug/feature/experience/performance)
- 提交时自动附带 context (current_page / tenant / user / user_agent)
- 归类 (LLM): bug / feature / 体验 / 性能 — 使用关键词 + 长度启发式 (可被 LLM 注入覆盖)
- 优先级: critical / high / medium / low
- GET  /api/feedback/v2/list             列表 (admin) — 支持类型/优先级/趋势筛选
- GET  /api/feedback/v2/trend            趋势 (按天聚合)

数据落表: feedback_v2 (与 pilot_feedback 区分)
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.feedback_v2")
router = APIRouter()


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


FEEDBACK_TYPES = ("rating", "bug", "feature", "experience", "performance")
CATEGORIES = ("bug", "feature", "experience", "performance", "other")
PRIORITIES = ("critical", "high", "medium", "low")

# 关键词权重 (粗略启发式 — LLM 可覆盖)
_BUG_KEYWORDS = (
    "崩溃", "卡死", "闪退", "报错", "异常", "失败", "无法", "crash", "bug",
    "error", "fail", "broken", "stuck", "hang", "exception",
)
_FEATURE_KEYWORDS = (
    "希望", "建议", "能不能", "可以加", "想要", "feature", "wish", "could you",
    "would be nice", "request",
)
_PERF_KEYWORDS = (
    "慢", "卡", "延迟", "性能", "speed", "slow", "lag", "performance",
    "loading", "loading too long",
)
_EXPERIENCE_KEYWORDS = (
    "体验", "UX", "界面", "ui", "ux", "experience", "界面卡", "看不清",
    "不友好", "不便",
)

# 优先级打分
_CRITICAL_KEYWORDS = (
    "critical", "urgent", "生产", "production", "影响业务", "数据丢失",
    "崩溃", "crash", "data loss", "immediately",
)


# ---------------------------------------------------------------------------
# 工具方法
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lower(text: str) -> str:
    return (text or "").lower()


def _keyword_hits(text: str, kws: Tuple[str, ...]) -> int:
    t = _lower(text)
    return sum(1 for k in kws if k in t)


def classify_feedback(category_hint: Optional[str], comment: str) -> str:
    """启发式归类. LLM 接管时仅作 fallback."""
    if category_hint and category_hint in CATEGORIES:
        return category_hint
    bug = _keyword_hits(comment, _BUG_KEYWORDS)
    feat = _keyword_hits(comment, _FEATURE_KEYWORDS)
    perf = _keyword_hits(comment, _PERF_KEYWORDS)
    exp = _keyword_hits(comment, _EXPERIENCE_KEYWORDS)
    scores = {"bug": bug, "feature": feat, "performance": perf, "experience": exp}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other"
    # bug + perf 同时高分时, 取 bug
    if scores["bug"] > 0 and scores["bug"] >= scores["performance"]:
        return "bug"
    if scores["performance"] > 0 and scores["performance"] > scores["bug"]:
        return "performance"
    return best


def score_priority(category: str, rating: Optional[int], comment: str) -> str:
    """基于 category/rating/keyword 推断优先级."""
    if rating is not None and rating <= 2:
        return "high" if category == "bug" else "medium"
    crit = _keyword_hits(comment, _CRITICAL_KEYWORDS)
    if crit > 0:
        return "critical"
    if category == "bug":
        # bug + 关键词 ≥ 2 → high
        if _keyword_hits(comment, _BUG_KEYWORDS) >= 2:
            return "high"
        return "medium"
    if category == "performance":
        return "medium"
    if category == "feature":
        return "low"
    if category == "experience":
        return "low"
    return "low"


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------


class FeedbackV2Create(BaseModel):
    type: str = Field(..., pattern="^(rating|bug|feature|experience|performance)$")
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = Field(None, max_length=200)
    comment: str = Field(..., min_length=1, max_length=4000)
    page: Optional[str] = Field(None, max_length=200)
    feature: Optional[str] = Field(None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackV2Record(BaseModel):
    id: str
    type: str
    category: str
    priority: str
    rating: Optional[int] = None
    title: Optional[str] = None
    comment: str
    page: Optional[str] = None
    feature: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    status: str = "open"


class FeedbackV2ListResponse(BaseModel):
    data: List[FeedbackV2Record]
    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)


class FeedbackV2TrendResponse(BaseModel):
    days: int
    buckets: List[dict[str, Any]]
    top_categories: List[dict[str, Any]]


# ---------------------------------------------------------------------------
# 依赖
# ---------------------------------------------------------------------------


def _auth_user(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    return user


def _admin_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if getattr(user, "role", None) not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="admin only")
    return user


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/api/feedback/v2", status_code=201, response_model=FeedbackV2Record)
async def submit_feedback_v2(
    body: FeedbackV2Create,
    user: CurrentUser = Depends(_auth_user),
):
    """统一反馈入口 (rating/bug/feature/experience/performance)."""
    category = classify_feedback(None, body.comment) if body.type != "rating" else "other"
    if body.type == "rating":
        category = "experience" if (body.rating or 0) < 4 else "other"
    priority = score_priority(category, body.rating, body.comment)
    # metadata 合并
    meta = dict(body.metadata or {})
    if body.page:
        meta.setdefault("page", body.page)
    if body.feature:
        meta.setdefault("feature", body.feature)
    if body.type:
        meta.setdefault("source_type", body.type)
    payload = {
        "type": body.type,
        "category": category,
        "priority": priority,
        "rating": body.rating,
        "title": body.title,
        "comment": body.comment,
        "page": body.page,
        "feature": body.feature,
        "user_id": str(user.id),
        "tenant_id": getattr(user, "tenant_id", None),
        "metadata": meta,
        "created_at": _now_iso(),
        "status": "open",
    }
    supabase = get_supabase_admin()
    if supabase is not None:
        try:
            res = supabase.table("feedback_v2").insert(payload).execute()
            rows = res.data or []
            if rows:
                return FeedbackV2Record(**{**payload, "id": str(rows[0].get("id", "stub"))})
        except Exception as exc:
            logger.warning("feedback_v2 persist failed: %s", exc)
    # offline / 测试 fallback
    return FeedbackV2Record(id="offline-stub", **payload)


@router.get("/api/feedback/v2/list", response_model=FeedbackV2ListResponse)
async def list_feedback_v2(
    type: Optional[str] = Query(None, pattern="^(rating|bug|feature|experience|performance)$"),
    priority: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    category: Optional[str] = Query(None, pattern="^(bug|feature|experience|performance|other)$"),
    status: Optional[str] = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(_admin_user),
):
    supabase = get_supabase_admin()
    if supabase is None:
        return FeedbackV2ListResponse(data=[], total=0)
    try:
        q = supabase.table("feedback_v2").select("*")
        if type:
            q = q.eq("type", type)
        if priority:
            q = q.eq("priority", priority)
        if category:
            q = q.eq("category", category)
        if status:
            q = q.eq("status", status)
        res = q.order("created_at", desc=True).limit(limit).execute()
        rows = res.data or []
    except Exception as exc:
        logger.warning("list_feedback_v2: %s", exc)
        return FeedbackV2ListResponse(data=[], total=0)
    by_type = Counter(r.get("type", "other") for r in rows)
    by_pri = Counter(r.get("priority", "low") for r in rows)
    by_cat = Counter(r.get("category", "other") for r in rows)
    return FeedbackV2ListResponse(
        data=[FeedbackV2Record(**r) for r in rows],
        total=len(rows),
        by_type=dict(by_type),
        by_priority=dict(by_pri),
        by_category=dict(by_cat),
    )


@router.get("/api/feedback/v2/trend", response_model=FeedbackV2TrendResponse)
async def feedback_v2_trend(
    days: int = Query(14, ge=1, le=90),
    user: CurrentUser = Depends(_admin_user),
):
    supabase = get_supabase_admin()
    if supabase is None:
        return FeedbackV2TrendResponse(days=days, buckets=[], top_categories=[])
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        res = (
            supabase.table("feedback_v2")
            .select("category,priority,created_at")
            .gte("created_at", since)
            .execute()
        )
        rows = res.data or []
    except Exception as exc:
        logger.warning("feedback_v2_trend: %s", exc)
        return FeedbackV2TrendResponse(days=days, buckets=[], top_categories=[])
    bucket: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "critical": 0, "high": 0})
    cats: Counter = Counter()
    for r in rows:
        date = (r.get("created_at") or "")[:10]
        if not date:
            continue
        b = bucket[date]
        b["total"] += 1
        pri = r.get("priority", "low")
        if pri in ("critical", "high"):
            b[pri] += 1
        cats[r.get("category", "other")] += 1
    buckets = [
        {"date": d, **vals}
        for d, vals in sorted(bucket.items())
    ]
    top_categories = [
        {"category": c, "count": n} for c, n in cats.most_common(5)
    ]
    return FeedbackV2TrendResponse(days=days, buckets=buckets, top_categories=top_categories)


@router.post("/api/feedback/v2/{feedback_id}/status")
async def update_feedback_status(
    feedback_id: str,
    status: str = Query(..., pattern="^(open|triaged|in_progress|resolved|closed)$"),
    user: CurrentUser = Depends(_admin_user),
):
    supabase = get_supabase_admin()
    if supabase is None:
        raise HTTPException(status_code=503, detail="supabase unavailable")
    try:
        res = (
            supabase.table("feedback_v2")
            .update({"status": status, "updated_at": _now_iso()})
            .eq("id", feedback_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"id": feedback_id, "status": status, "updated": bool(res.data)}


__all__ = [
    "router",
    "classify_feedback",
    "score_priority",
    "FEEDBACK_TYPES",
    "CATEGORIES",
    "PRIORITIES",
]
