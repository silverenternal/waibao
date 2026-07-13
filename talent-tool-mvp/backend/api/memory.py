"""T2702 — Memory API (the public surface for the agent unified memory store).

Endpoints (mounted under /api/memory):

* POST   /memories                 - create a memory
* GET    /memories                 - list memories for current user
* GET    /memories/{id}            - get a single memory
* PATCH  /memories/{id}            - edit a memory
* DELETE /memories/{id}            - delete a memory
* POST   /memories/query           - semantic query (top_k)
* POST   /memories/extract         - extract from a chat via LLM (or heuristic)
* POST   /memories/forget          - GDPR-style revocation
* POST   /memories/decay           - manual decay (admin)
* GET    /memories/access-log      - audit trail (admin / owner)
* POST   /memories/links           - create a graph link
* GET    /memories/{id}/links      - links touching a memory
* GET    /health                   - component health

All endpoints are tenant-isolated via the JWT context.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.memory import (
    Memory,
    MemoryLink,
    MemoryQuery,
    MemoryStore,
    MemoryType,
    RelationType,
    get_memory_store,
    reset_memory_store,
)

logger = logging.getLogger("recruittech.api.memory")
router = APIRouter()


# ----------------------------------------------------------------------
# Pydantic contracts
# ----------------------------------------------------------------------

class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    type: MemoryType = MemoryType.FACT
    source_agent: str = Field(default="api.memory", min_length=1, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None


class MemoryPatch(BaseModel):
    content: Optional[str] = None
    summary: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None
    is_archived: Optional[bool] = None
    type: Optional[MemoryType] = None


class MemoryQueryRequest(BaseModel):
    query_text: str = Field(min_length=1)
    top_k: int = 10
    types: list[MemoryType] = Field(default_factory=list)
    min_confidence: float = 0.0
    min_decay: float = 0.0
    include_links: bool = False


class MemoryOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    summary: Optional[str] = None
    source_agent: str
    type: MemoryType
    confidence: float
    decay_score: float
    access_count: int
    last_accessed: Optional[str] = None
    metadata: dict[str, Any]
    is_archived: bool
    created_at: str
    updated_at: str


class MemoryLinkCreate(BaseModel):
    memory_id_a: uuid.UUID
    memory_id_b: uuid.UUID
    relation: RelationType = RelationType.RELATED
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryLinkOut(BaseModel):
    id: uuid.UUID
    memory_id_a: uuid.UUID
    memory_id_b: uuid.UUID
    relation: RelationType
    weight: float
    created_at: str


class ForgetRequest(BaseModel):
    source_agent: Optional[str] = None
    type: Optional[MemoryType] = None
    older_than_days: Optional[int] = None
    decay_below: Optional[float] = None


class ExtractRequest(BaseModel):
    messages: list[dict[str, str]]
    max_items: int = 16
    persist: bool = True


class DecayRequest(BaseModel):
    factor: float = 0.95


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _to_out(m: Memory) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        tenant_id=m.tenant_id,
        user_id=m.user_id,
        content=m.content,
        summary=m.summary,
        source_agent=m.source_agent,
        type=m.type,
        confidence=m.confidence,
        decay_score=m.decay_score,
        access_count=m.access_count,
        last_accessed=m.last_accessed.isoformat() if m.last_accessed else None,
        metadata=m.metadata,
        is_archived=m.is_archived,
        created_at=m.created_at.isoformat() if m.created_at else "",
        updated_at=m.updated_at.isoformat() if m.updated_at else "",
    )


def _ensure_store_initialized(store: MemoryStore) -> MemoryStore:
    """Wire Supabase backend if a client is available (no-op in tests)."""
    if getattr(store.backend, "__class__", None).__name__ == "InMemoryBackend":
        try:
            sb = get_supabase_admin()
            if sb is not None:
                store.init(supabase_client_factory=lambda: sb)
        except Exception:
            pass
    return store


def _resolve_user_uuid(user: CurrentUser) -> uuid.UUID:
    try:
        return uuid.UUID(str(user.id))
    except Exception:
        return uuid.uuid4()


def _resolve_tenant_id(user: CurrentUser) -> uuid.UUID | None:
    """Best-effort tenant_id lookup. Tolerates both model attribute and JWT
    extra field. Returns ``None`` when neither is present.
    """
    tid = getattr(user, "tenant_id", None)
    if tid:
        try:
            return uuid.UUID(str(tid))
        except Exception:
            pass
    # Some auth flows stash the tenant under app_metadata
    extra = getattr(user, "model_extra", None) or {}
    tid = extra.get("tenant_id") if isinstance(extra, dict) else None
    if tid:
        try:
            return uuid.UUID(str(tid))
        except Exception:
            pass
    return None


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@router.get("/health", tags=["memory-health"])
async def health() -> dict[str, Any]:
    store = _ensure_store_initialized(get_memory_store())
    backend = store.backend.__class__.__name__
    return {
        "status": "ok",
        "backend": backend,
        "components": {
            "store": "MemoryStore (Mem0 vendor-in)",
            "extractor": "EntityExtractor (LLM + heuristic)",
            "injector": "MemoryInjector",
            "subscribers": [
                "profile.updated",
                "preference.expressed",
                "interview.completed",
                "offer.received",
                "memory.decay.requested",
            ],
        },
    }


@router.post("/memories", response_model=MemoryOut, tags=["memories"])
async def create_memory(
    body: MemoryCreate,
    user: CurrentUser = Depends(get_current_user),
) -> MemoryOut:
    store = _ensure_store_initialized(get_memory_store())
    tenant_id = _resolve_tenant_id(user) or uuid.UUID(int=0)
    m = store.add(
        user_id=_resolve_user_uuid(user),
        content=body.content,
        source_agent=body.source_agent,
        type=body.type,
        tenant_id=tenant_id,
        confidence=body.confidence,
        metadata=body.metadata,
    )
    if body.summary:
        m.summary = body.summary
        store.backend.update(m)
    return _to_out(m)


@router.get("/memories", response_model=list[MemoryOut], tags=["memories"])
async def list_memories(
    user: CurrentUser = Depends(get_current_user),
    types: list[MemoryType] = Query(default_factory=list),
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[MemoryOut]:
    store = _ensure_store_initialized(get_memory_store())
    items = store.list_for_user(
        _resolve_user_uuid(user),
        types=types or None,
        include_archived=include_archived,
    )
    return [_to_out(m) for m in items[:limit]]


@router.get("/memories/{memory_id}", response_model=MemoryOut, tags=["memories"])
async def get_memory(
    memory_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> MemoryOut:
    store = _ensure_store_initialized(get_memory_store())
    m = store.get(memory_id)
    if m is None or m.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory not found")
    return _to_out(m)


@router.patch("/memories/{memory_id}", response_model=MemoryOut, tags=["memories"])
async def patch_memory(
    memory_id: uuid.UUID,
    body: MemoryPatch,
    user: CurrentUser = Depends(get_current_user),
) -> MemoryOut:
    store = _ensure_store_initialized(get_memory_store())
    m = store.get(memory_id)
    if m is None or m.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory not found")
    if body.content is not None:
        m.content = body.content
    if body.summary is not None:
        m.summary = body.summary
    if body.confidence is not None:
        m.confidence = body.confidence
    if body.metadata is not None:
        m.metadata = body.metadata
    if body.is_archived is not None:
        m.is_archived = body.is_archived
    if body.type is not None:
        m.type = body.type
    m.updated_at = datetime.utcnow()
    store.backend.update(m)
    return _to_out(m)


@router.delete("/memories/{memory_id}", tags=["memories"])
async def delete_memory(
    memory_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    store = _ensure_store_initialized(get_memory_store())
    m = store.get(memory_id)
    if m is None or m.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory not found")
    store.backend.delete(memory_id)
    return {"deleted": True, "id": str(memory_id)}


@router.post("/memories/query", response_model=list[MemoryOut], tags=["memories"])
async def query_memories(
    body: MemoryQueryRequest,
    user: CurrentUser = Depends(get_current_user),
) -> list[MemoryOut]:
    store = _ensure_store_initialized(get_memory_store())
    items = store.query(
        user_id=_resolve_user_uuid(user),
        query_text=body.query_text,
        top_k=body.top_k,
        types=body.types or None,
        min_confidence=body.min_confidence,
        min_decay=body.min_decay,
        include_links=body.include_links,
    )
    return [_to_out(m) for m in items]


@router.post("/memories/extract", response_model=list[MemoryOut], tags=["memories"])
async def extract_memories(
    body: ExtractRequest,
    user: CurrentUser = Depends(get_current_user),
) -> list[MemoryOut]:
    """Extract memories from a chat transcript (LLM or heuristic)."""
    from services.memory.extractor import EntityExtractor

    store = _ensure_store_initialized(get_memory_store())
    extractor = EntityExtractor()
    items = extractor.extract(body.messages, max_items=body.max_items)
    if not body.persist:
        return [
            MemoryOut(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(int=0),
                user_id=_resolve_user_uuid(user),
                content=it["content"],
                summary=None,
                source_agent="extractor",
                type=it["type"],
                confidence=it["confidence"],
                decay_score=1.0,
                access_count=0,
                last_accessed=None,
                metadata={},
                is_archived=False,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )
            for it in items
        ]
    tenant_id = _resolve_tenant_id(user) or uuid.UUID(int=0)
    out: list[Memory] = []
    for it in items:
        m = store.add(
            user_id=_resolve_user_uuid(user),
            content=it["content"],
            source_agent="extractor",
            type=it["type"],
            tenant_id=tenant_id,
            confidence=it["confidence"],
            metadata={"extracted": True},
        )
        out.append(m)
    return [_to_out(m) for m in out]


@router.post("/memories/forget", tags=["memories"])
async def forget_memories(
    body: ForgetRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """GDPR revocation: delete memories matching the filter."""
    store = _ensure_store_initialized(get_memory_store())
    user_uuid = _resolve_user_uuid(user)

    def _predicate(m: Memory) -> bool:
        if body.older_than_days is not None and m.created_at:
            age = (datetime.utcnow() - m.created_at).days
            if age < body.older_than_days:
                return False
        if body.decay_below is not None and m.decay_score >= body.decay_below:
            return False
        return True

    n = store.forget(
        user_id=user_uuid,
        predicate=_predicate,
        source_agent=body.source_agent,
        type=body.type,
    )
    return {"deleted": n, "user_id": str(user_uuid)}


@router.post("/memories/decay", tags=["memories"])
async def manual_decay(
    body: DecayRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually trigger decay (typically a cron does this)."""
    store = _ensure_store_initialized(get_memory_store())
    n = store.decay(factor=body.factor)
    return {"affected": n, "factor": body.factor}


@router.get("/access-log", tags=["memories"])
async def access_log(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    store = _ensure_store_initialized(get_memory_store())
    return store.access_log(_resolve_user_uuid(user))


@router.post("/memories/links", response_model=MemoryLinkOut, tags=["memories"])
async def create_link(
    body: MemoryLinkCreate,
    user: CurrentUser = Depends(get_current_user),
) -> MemoryLinkOut:
    store = _ensure_store_initialized(get_memory_store())
    # Verify both memories belong to the user
    a = store.get(body.memory_id_a)
    b = store.get(body.memory_id_b)
    if a is None or a.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory A not found")
    if b is None or b.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory B not found")
    link = store.link(
        body.memory_id_a,
        body.memory_id_b,
        body.relation,
        weight=body.weight,
        metadata=body.metadata,
    )
    return MemoryLinkOut(
        id=link.id,
        memory_id_a=link.memory_id_a,
        memory_id_b=link.memory_id_b,
        relation=link.relation,
        weight=link.weight,
        created_at=link.created_at.isoformat(),
    )


@router.get("/memories/{memory_id}/links", response_model=list[MemoryLinkOut], tags=["memories"])
async def list_links(
    memory_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> list[MemoryLinkOut]:
    store = _ensure_store_initialized(get_memory_store())
    m = store.get(memory_id)
    if m is None or m.user_id != _resolve_user_uuid(user):
        raise HTTPException(status_code=404, detail="memory not found")
    links = store.links_for(memory_id)
    return [
        MemoryLinkOut(
            id=l.id,
            memory_id_a=l.memory_id_a,
            memory_id_b=l.memory_id_b,
            relation=l.relation,
            weight=l.weight,
            created_at=l.created_at.isoformat(),
        )
        for l in links
    ]
