"""T902 — 互评对照 API.

GET  /api/match/eval/{id}                — 双方评分对比 + 强弱项
POST /api/match/eval/{id}/discuss        — 发起讨论(创建协同房间)
POST /api/match/eval/{id}/comments       — 评论
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole

logger = logging.getLogger("recruittech.api.match_eval")
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EvalComment(BaseModel):
    author_role: str = Field(default="talent_partner", description="candidate|employer|talent_partner|admin")
    body: str
    dimension: Optional[str] = None  # skill/communication/culture/potential


class DiscussRequest(BaseModel):
    topic: str = Field(default="Match evaluation discussion", max_length=200)
    participants: list[str] = Field(
        default_factory=list,
        description="user_ids 列表(候选人 + 用人方 + talent_partner)",
    )


class EvalComparisonResponse(BaseModel):
    match_id: str
    candidate_eval: Optional[dict[str, Any]] = None
    employer_eval: Optional[dict[str, Any]] = None
    # 派生:双方一致项 / 分歧项
    aligned_strengths: list[str] = []
    aligned_concerns: list[str] = []
    divergent_dimensions: list[dict[str, Any]] = []
    overall_alignment: float = 0.0  # 0~1
    discussion_room_id: Optional[str] = None
    comments: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _load_eval_record(supabase, match_id: str) -> Optional[dict[str, Any]]:
    """从 mutual_evaluations 表(若存在)拉取最新一条评估."""
    try:
        resp = (
            supabase.table("mutual_evaluations")
            .select("*")
            .eq("match_id", match_id)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return resp.data
    except Exception:
        # 表可能不存在
        return None


def _score_alignment(
    candidate_eval: Optional[dict[str, Any]],
    employer_eval: Optional[dict[str, Any]],
) -> tuple[float, list[str], list[str], list[dict[str, Any]]]:
    """计算双方一致性 + 对齐项 / 分歧项.

    Returns: (alignment_score, aligned_strengths, aligned_concerns, divergent_dims)
    """
    if not candidate_eval or not employer_eval:
        return 0.0, [], [], []

    DIMENSIONS = ["skill", "communication", "culture", "potential"]

    aligned_strengths: list[str] = []
    aligned_concerns: list[str] = []
    divergent: list[dict[str, Any]] = []
    diffs: list[float] = []

    for dim in DIMENSIONS:
        c_val = candidate_eval.get(dim)
        e_val = employer_eval.get(dim)
        if not isinstance(c_val, (int, float)) or not isinstance(e_val, (int, float)):
            continue
        avg = (c_val + e_val) / 2.0
        gap = abs(c_val - e_val)
        diffs.append(gap)
        if gap <= 0.5 and avg >= 4.0:
            aligned_strengths.append(dim)
        elif gap <= 0.5 and avg <= 2.5:
            aligned_concerns.append(dim)
        elif gap > 1.5:
            divergent.append(
                {
                    "dimension": dim,
                    "candidate": c_val,
                    "employer": e_val,
                    "gap": gap,
                }
            )

    avg_gap = (sum(diffs) / len(diffs)) if diffs else 0.0
    # max gap is 4 (5 vs 1); 越接近 0 越一致
    alignment = max(0.0, min(1.0, 1.0 - avg_gap / 4.0))
    return round(alignment, 3), aligned_strengths, aligned_concerns, divergent


def _load_comments(supabase, match_id: str) -> list[dict[str, Any]]:
    try:
        resp = (
            supabase.table("match_eval_comments")
            .select("*")
            .eq("match_id", match_id)
            .order("created_at", desc=False)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/{match_id}", response_model=EvalComparisonResponse)
async def get_eval_comparison(
    match_id: UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """获取互评对照视图."""
    supabase = get_supabase_admin()
    match_id_str = str(match_id)

    # 1) match 必须存在
    match_resp = (
        supabase.table("matches")
        .select("id")
        .eq("id", match_id_str)
        .maybe_single()
        .execute()
    )
    if not match_resp.data:
        raise HTTPException(status_code=404, detail="Match not found")

    # 2) 双方评估
    eval_rec = _load_eval_record(supabase, match_id_str)
    candidate_eval = (eval_rec or {}).get("candidate_eval") if eval_rec else None
    employer_eval = (eval_rec or {}).get("employer_eval") if eval_rec else None

    alignment, strengths, concerns, divergent = _score_alignment(
        candidate_eval, employer_eval
    )

    comments = _load_comments(supabase, match_id_str)
    room_id = (eval_rec or {}).get("discussion_room_id") if eval_rec else None

    return EvalComparisonResponse(
        match_id=match_id_str,
        candidate_eval=candidate_eval,
        employer_eval=employer_eval,
        aligned_strengths=strengths,
        aligned_concerns=concerns,
        divergent_dimensions=divergent,
        overall_alignment=alignment,
        discussion_room_id=room_id,
        comments=comments,
    )


@router.post("/{match_id}/discuss")
async def start_discussion(
    match_id: UUID,
    body: DiscussRequest,
    user: CurrentUser = Depends(
        require_role(UserRole.talent_partner, UserRole.admin)
    ),
):
    """发起互评讨论(创建协同房间)."""
    supabase = get_supabase_admin()
    match_id_str = str(match_id)

    match_resp = (
        supabase.table("matches")
        .select("id, candidate_id, role_id")
        .eq("id", match_id_str)
        .maybe_single()
        .execute()
    )
    if not match_resp.data:
        raise HTTPException(status_code=404, detail="Match not found")

    room_id = str(uuid.uuid4())
    record = {
        "id": room_id,
        "topic": body.topic,
        "match_id": match_id_str,
        "participants": list({*body.participants, str(user.id)}),
        "status": "active",
        "created_by": str(user.id),
        "created_at": datetime.utcnow().isoformat(),
    }
    try:
        supabase.table("rooms").insert(record).execute()
    except Exception as exc:
        logger.warning(f"rooms insert failed: {exc}")
        # 继续返回 room_id,允许外部系统继续创建

    # 回写到 mutual_evaluations(若存在)
    try:
        supabase.table("mutual_evaluations").upsert(
            {
                "match_id": match_id_str,
                "discussion_room_id": room_id,
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="match_id",
        ).execute()
    except Exception as exc:
        logger.debug(f"mutual_evaluations upsert skipped: {exc}")

    return {
        "match_id": match_id_str,
        "room_id": room_id,
        "topic": body.topic,
        "participants": record["participants"],
        "status": "active",
    }


@router.post("/{match_id}/comments")
async def post_comment(
    match_id: UUID,
    body: EvalComment,
    user: CurrentUser = Depends(get_current_user),
):
    """评论一条互评."""
    supabase = get_supabase_admin()
    match_id_str = str(match_id)

    if not body.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")

    comment_id = str(uuid.uuid4())
    record = {
        "id": comment_id,
        "match_id": match_id_str,
        "author_id": str(user.id),
        "author_role": body.author_role or user.role.value,
        "body": body.body.strip(),
        "dimension": body.dimension,
        "created_at": datetime.utcnow().isoformat(),
    }
    try:
        supabase.table("match_eval_comments").insert(record).execute()
    except Exception as exc:
        logger.warning(f"insert match_eval_comments failed: {exc}")
        # 即使失败也返回 id,便于客户端乐观更新
    return {"comment": record}