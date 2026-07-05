"""embedding_updater — 增量更新画像 embedding.

供 feedback_loop 调用,把用户最新行为数据反映到向量表示中.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from supabase import Client

logger = logging.getLogger("recruittech.signals.embedding_updater")


async def _embed(text: str) -> list[float]:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
        return resp.data[0].embedding
    except Exception:
        return [0.0] * 1536


async def update_jobseeker_embedding(user_id: str, supabase: Client):
    """根据用户最近 30 天数据更新向量."""
    journals = (
        supabase.table("daily_journals")
        .select("content, ai_rating")
        .eq("user_id", user_id)
        .order("journal_date", desc=True)
        .limit(30)
        .execute()
    ).data or []
    clar = (
        supabase.table("candidate_clarifications")
        .select("profile_synthesis, must_haves")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    ).data or {}

    text = json.dumps({"journals": journals, "clar": clar}, ensure_ascii=False)
    emb = await _embed(text)
    supabase.table("agent_memory").upsert({
        "user_id": user_id,
        "persona": "jobseeker",
        "scope": "long_term",
        "key": "profile_embedding",
        "value": emb,
    }, on_conflict="user_id,scope,key").execute()
    logger.info(f"updated embedding for {user_id}")


async def update_role_embedding(role_id: str, supabase: Client):
    """更新岗位画像向量."""
    role = supabase.table("roles").select("*").eq("id", role_id).maybe_single().execute().data or {}
    clar = (
        supabase.table("employer_clarifications")
        .select("talent_image, real_needs")
        .eq("role_id", role_id)
        .maybe_single()
        .execute()
    ).data or {}

    text = json.dumps({"role": role, "clar": clar}, ensure_ascii=False)
    emb = await _embed(text)
    supabase.table("roles").update({"embedding": emb}).eq("id", role_id).execute()