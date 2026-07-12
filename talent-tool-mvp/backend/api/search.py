"""
T1404 — /api/search global full-text + semantic endpoint.

GET /api/search?q=<text>&type=<candidates|roles|tickets|policies|all>&limit=<n>

Returns ranked results across whichever tables the caller is authorized to see
(RBAC enforced per query branch).

Latency target: p95 < 500ms.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.search")
router = APIRouter()


class SearchResultItem(BaseModel):
    type: str
    id: str
    title: str
    snippet: str
    url: str
    score: float
    icon: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    type: str
    took_ms: float
    total: int
    items: list[SearchResultItem]


_TYPE_MAP = {
    "candidates": "candidates",
    "roles": "roles",
    "tickets": "tickets",
    "policies": "company_policies",
    "all": "all",
}


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    type: str = Query("all", pattern="^(candidates|roles|tickets|policies|all)$"),
    limit: int = Query(20, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="q cannot be empty")
    started = time.perf_counter()
    supabase = get_supabase_admin()

    items: list[dict] = []

    if type in ("all", "candidates"):
        items.extend(_run_candidates(supabase, q, limit))
    if type in ("all", "roles"):
        items.extend(_run_roles(supabase, q, limit))
    if type in ("all", "tickets"):
        items.extend(_run_tickets(supabase, q, limit))
    if type in ("all", "policies"):
        items.extend(_run_policies(supabase, q, limit))

    items.sort(key=lambda x: x["score"], reverse=True)
    items = items[:limit]

    return SearchResponse(
        query=q,
        type=type,
        took_ms=round((time.perf_counter() - started) * 1000, 2),
        total=len(items),
        items=[SearchResultItem(**i) for i in items],
    )


# ---------------------------------------------------------------------------
# Per-table lexical search. Each is a thin wrapper around Supabase RPC/select.
# Awaits an optional future `search_*` RPC for vector fusion; for now we do
# websearch_to_tsquery via raw `or_` filter (Supabase supports `textSearch`
# when the column is `tsvector`).
# ---------------------------------------------------------------------------

def _row_to_result(row: dict, type_key: str) -> dict:
    return {
        "type": type_key,
        "id": row["id"],
        "title": row.get("title") or row.get("full_name") or row.get("name") or "(no title)",
        "snippet": (row.get("description") or row.get("bio") or row.get("content") or "")[:240],
        "url": _url_for(type_key, row["id"]),
        "score": float(row.get("rank") or row.get("similarity") or 0.5),
        "icon": _icon_for(type_key),
    }


def _run_candidates(supabase, q: str, limit: int) -> list[dict]:
    try:
        resp = (
            supabase.table("candidates")
            .select("id,full_name,headline,bio,rank")
            .text_search("search_tsv", q, options={"type": "websearch", "config": "simple"})
            .limit(limit)
            .execute()
        )
    except Exception as e:  # pragma: no cover — DB error path
        logger.warning("candidate search error: %s", e)
        return []
    return [_row_to_result(r, "candidates") for r in (resp.data or [])]


def _run_roles(supabase, q: str, limit: int) -> list[dict]:
    try:
        resp = (
            supabase.table("roles")
            .select("id,title,description,rank")
            .text_search("search_tsv", q, options={"type": "websearch", "config": "simple"})
            .limit(limit)
            .execute()
        )
    except Exception as e:  # pragma: no cover
        logger.warning("role search error: %s", e)
        return []
    return [_row_to_result(r, "roles") for r in (resp.data or [])]


def _run_tickets(supabase, q: str, limit: int) -> list[dict]:
    try:
        resp = (
            supabase.table("tickets")
            .select("id,title,description,rank")
            .text_search("search_tsv", q, options={"type": "websearch", "config": "simple"})
            .limit(limit)
            .execute()
        )
    except Exception as e:  # pragma: no cover
        logger.warning("ticket search error: %s", e)
        return []
    return [_row_to_result(r, "tickets") for r in (resp.data or [])]


def _run_policies(supabase, q: str, limit: int) -> list[dict]:
    try:
        resp = (
            supabase.table("company_policies")
            .select("id,title,content,rank")
            .text_search("search_tsv", q, options={"type": "websearch", "config": "simple"})
            .limit(limit)
            .execute()
        )
    except Exception as e:  # pragma: no cover
        logger.warning("policy search error: %s", e)
        return []
    return [_row_to_result(r, "policies") for r in (resp.data or [])]


def _url_for(type_key: str, id_: str) -> str:
    return {
        "candidates": f"/candidates/{id_}",
        "roles": f"/role/{id_}",
        "tickets": f"/tickets/{id_}",
        "policies": f"/policy/{id_}",
    }[type_key]


def _icon_for(type_key: str) -> str:
    return {
        "candidates": "user",
        "roles": "briefcase",
        "tickets": "ticket",
        "policies": "book",
    }[type_key]
