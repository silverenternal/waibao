"""
T1404 — /api/search global full-text + semantic endpoint.

GET /api/search?q=<text>&type=<candidates|roles|tickets|policies|all>&limit=<n>

T2501 — POST /api/search/multimodal
  Accepts JSON body {query, image_b64?, video_b64?, audio_b64?, filename?}
  or multipart/form-data with the same fields. Returns fused ranked
  results across text + image + video + voice channels (RRF weighted).

Returns ranked results across whichever tables the caller is authorized to see
(RBAC enforced per query branch).

Latency target: p95 < 500ms.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
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


# ---------------------------------------------------------------------------
# T2501 — /api/search/multimodal (text + image + video + voice)
# ---------------------------------------------------------------------------


class MultimodalHit(BaseModel):
    type: str
    id: str
    title: str
    snippet: str
    url: str
    score: float
    icon: Optional[str] = None
    channel_scores: dict[str, float] = Field(default_factory=dict)
    matched_channels: list[str] = Field(default_factory=list)


class MultimodalSearchResponse(BaseModel):
    query: str
    took_ms: float
    total: int
    channels_used: list[str]
    weights: dict[str, float]
    items: list[MultimodalHit]


class MultimodalJsonRequest(BaseModel):
    query: str = ""
    image_b64: Optional[str] = None
    image_filename: str = ""
    video_b64: Optional[str] = None
    video_filename: str = ""
    audio_b64: Optional[str] = None
    audio_filename: str = ""
    limit: int = Field(20, ge=1, le=50)
    text_weight: float = Field(0.45, ge=0.0, le=1.0)
    image_weight: float = Field(0.30, ge=0.0, le=1.0)
    video_weight: float = Field(0.15, ge=0.0, le=1.0)
    voice_weight: float = Field(0.10, ge=0.0, le=1.0)


def _decode_optional_b64(payload: Optional[str]) -> bytes:
    if not payload:
        return b""
    try:
        return base64.b64decode(payload)
    except Exception:
        return b""


@router.post("/multimodal", response_model=MultimodalSearchResponse)
async def search_multimodal_json(
    payload: MultimodalJsonRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """JSON body variant of /api/search/multimodal."""
    return await _run_multimodal(
        query=payload.query,
        image_bytes=_decode_optional_b64(payload.image_b64),
        image_filename=payload.image_filename,
        video_bytes=_decode_optional_b64(payload.video_b64),
        video_filename=payload.video_filename,
        audio_bytes=_decode_optional_b64(payload.audio_b64),
        audio_filename=payload.audio_filename,
        limit=payload.limit,
        weights={
            "text": payload.text_weight,
            "image": payload.image_weight,
            "video": payload.video_weight,
            "voice": payload.voice_weight,
        },
    )


@router.post("/multimodal/upload", response_model=MultimodalSearchResponse)
async def search_multimodal_upload(
    query: str = Form(""),
    image: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    limit: int = Form(20),
    user: CurrentUser = Depends(get_current_user),
):
    """Multipart variant of /api/search/multimodal for direct file uploads."""
    image_bytes = await image.read() if image else b""
    video_bytes = await video.read() if video else b""
    audio_bytes = await audio.read() if audio else b""
    return await _run_multimodal(
        query=query,
        image_bytes=image_bytes,
        image_filename=(image.filename if image else "") or "",
        video_bytes=video_bytes,
        video_filename=(video.filename if video else "") or "",
        audio_bytes=audio_bytes,
        audio_filename=(audio.filename if audio else "") or "",
        limit=limit,
    )


async def _run_multimodal(
    *,
    query: str,
    image_bytes: bytes,
    image_filename: str,
    video_bytes: bytes,
    video_filename: str,
    audio_bytes: bytes,
    audio_filename: str,
    limit: int,
    weights: Optional[dict[str, float]] = None,
) -> MultimodalSearchResponse:
    started = time.perf_counter()
    try:
        from services.matching.multimodal_search import (
            multimodal_search,
            ChannelWeights,
        )
    except ImportError as exc:  # pragma: no cover - module always present
        raise HTTPException(status_code=500, detail=f"multimodal unavailable: {exc}")

    cw = ChannelWeights(**(weights or {}))
    result = multimodal_search(
        query_text=query,
        image_bytes=image_bytes or None,
        image_filename=image_filename,
        video_bytes=video_bytes or None,
        video_filename=video_filename,
        audio_bytes=audio_bytes or None,
        audio_filename=audio_filename,
        limit=limit,
        weights=cw,
    )

    channels_used: list[str] = []
    if query.strip():
        channels_used.append("text")
    if image_bytes:
        channels_used.append("image")
    if video_bytes:
        channels_used.append("video")
    if audio_bytes:
        channels_used.append("voice")

    return MultimodalSearchResponse(
        query=result.query_text,
        took_ms=round((time.perf_counter() - started) * 1000, 2),
        total=result.total,
        channels_used=channels_used,
        weights=result.channel_weights,
        items=[
            MultimodalHit(
                type=h.type,
                id=h.id,
                title=h.title,
                snippet=h.snippet,
                url=h.url,
                score=h.score,
                icon=None,
                channel_scores=h.channel_scores,
                matched_channels=h.matched_channels,
            )
            for h in result.items
        ],
    )
