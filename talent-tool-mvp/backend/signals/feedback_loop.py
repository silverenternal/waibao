"""Feedback Loop - 匹配质量持续学习.

需求 3 闭环: 匹配/面试/入职结果回流到画像,持续优化.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from supabase import Client

logger = logging.getLogger("recruittech.signals.feedback_loop")


async def record_match_outcome(
    match_id: str,
    outcome: str,        # accepted / rejected / hired / withdrawn
    feedback: dict,
    supabase: Optional[Client] = None,
):
    """记录匹配结果,用于模型校准."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    new_status = {
        "accepted": "accepted",
        "rejected": "rejected_by_candidate",
        "hired": "placed",
        "withdrawn": "rejected_by_employer",
    }.get(outcome, "pending")

    update = {
        "status": new_status,
        "feedback_loop": supabase.table("two_way_matches")
            .select("feedback_loop")
            .eq("id", match_id)
            .maybe_single()
            .execute()
            .data or {},
        "updated_at": datetime.utcnow().isoformat(),
    }
    if not isinstance(update["feedback_loop"], dict):
        update["feedback_loop"] = {}
    update["feedback_loop"].update({
        "outcome": outcome,
        "feedback": feedback,
        "recorded_at": datetime.utcnow().isoformat(),
    })

    supabase.table("two_way_matches").update(update).eq("id", match_id).execute()
    logger.info(f"match {match_id} outcome={outcome}")


async def recalibrate_match_scores(
    candidate_id: Optional[str] = None,
    role_id: Optional[str] = None,
    supabase: Optional[Client] = None,
):
    """基于历史 outcomes,微调匹配权重(MVP: 仅记录,生产可接入在线学习)."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    query = supabase.table("two_way_matches").select("*")
    if candidate_id:
        query = query.eq("candidate_id", candidate_id)
    if role_id:
        query = query.eq("role_id", role_id)

    matches = query.execute().data or []
    stats = {"total": len(matches), "placed": 0, "rejected": 0, "accepted": 0}
    for m in matches:
        s = m.get("status", "pending")
        if s in stats:
            stats[s] = stats.get(s, 0) + 1

    logger.info(f"recalibration stats: {stats}")
    return stats


async def update_candidate_embedding(user_id: str, supabase: Optional[Client] = None):
    """基于最新日记/对话更新求职者画像的 embedding."""
    if supabase is None:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()

    # 拉取最近日记 + clarifications
    journals = (
        supabase.table("daily_journals")
        .select("content, ai_rating, mood_score")
        .eq("user_id", user_id)
        .order("journal_date", desc=True)
        .limit(30)
        .execute()
    ).data or []

    clar = supabase.table("candidate_clarifications").select("*").eq(
        "user_id", user_id
    ).maybe_single().execute().data or {}

    # 拼接文本
    text = json.dumps({
        "journals": journals,
        "clarification": clar,
    }, ensure_ascii=False)

    # 调 OpenAI embedding (mock here)
    try:
        from openai import AsyncOpenAI
        import os
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
        embedding = resp.data[0].embedding
    except Exception:
        embedding = [0.0] * 1536

    supabase.table("agent_memory").upsert({
        "user_id": user_id,
        "persona": "jobseeker",
        "scope": "long_term",
        "key": "profile_embedding",
        "value": embedding,
    }, on_conflict="user_id,scope,key").execute()