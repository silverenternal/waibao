"""RAG API — T2701.

Endpoints (mounted under /api/rag):

* POST   /collections               - create a new RAG collection
* GET    /collections               - list collections for the tenant
* GET    /collections/{id}          - get a single collection
* POST   /documents                 - multipart upload (file) -> ingest
* GET    /documents                 - list documents in a collection
* GET    /documents/{id}            - get a single document
* POST   /query                     - question + top_k -> answer + citations
* POST   /query/stream              - SSE stream of the answer
* GET    /health                    - dependency health (Qdrant, embedder, ...)

All endpoints require a JWT (current_user) and are tenant-isolated.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.rag import (
    Chunker,
    CitationFormatter,
    DocumentParser,
    Embedder,
    EmbeddingModel,
    Generator,
    GenerationConfig,
    RagService,
    Reranker,
    RetrievalConfig,
    RetrievalMode,
    Retriever,
    get_rag_service,
)


logger = logging.getLogger("recruittech.api.rag")
router = APIRouter()


# ----------------------------------------------------------------------
# Pydantic contracts
# ----------------------------------------------------------------------

class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    embedding_model: EmbeddingModel = EmbeddingModel.BGE_LARGE
    chunk_size: int = 512
    chunk_overlap: int = 50
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectionOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    qdrant_collection: str
    chunk_size: int
    chunk_overlap: int
    is_active: bool
    created_at: str


class DocumentOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    name: str
    display_name: str
    source: str
    mime_type: str | None
    size_bytes: int
    status: str
    total_chunks: int
    total_tokens: int
    error_message: str | None
    created_at: str
    updated_at: str


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    collection_id: uuid.UUID
    top_k: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode = RetrievalMode.HYBRID
    use_reranker: bool = True
    use_citations: bool = True


class CitationOut(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    document_name: str
    position: int
    snippet: str
    score: float
    rerank_score: float | None
    token: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: list[CitationOut]
    retrieval_ms: int
    rerank_ms: int
    generation_ms: int
    total_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _require_tenant(user: CurrentUser) -> uuid.UUID:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant required for RAG access")
    return user.tenant_id


def _get_service() -> RagService:
    try:
        return get_rag_service()
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG service init failed: %s", exc)
        # Fallback to a fresh in-process instance
        return RagService()


# ----------------------------------------------------------------------
# Collections
# ----------------------------------------------------------------------

@router.post("/collections", response_model=CollectionOut, tags=["rag-collections"])
async def create_collection(
    body: CollectionCreate,
    user: CurrentUser = Depends(get_current_user),
) -> CollectionOut:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    qdrant_collection = f"tenant_{tenant_id}_{body.name.lower().replace(' ', '_')}"
    row = {
        "tenant_id": str(tenant_id),
        "name": body.name,
        "description": body.description,
        "embedding_model": body.embedding_model.value,
        "embedding_dim": body.embedding_model.dim,
        "qdrant_collection": qdrant_collection,
        "chunk_size": body.chunk_size,
        "chunk_overlap": body.chunk_overlap,
        "metadata": body.metadata,
        "is_active": True,
    }
    res = sb.table("rag_collections").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create collection")
    d = res.data[0]
    return CollectionOut(
        id=d["id"],
        tenant_id=d["tenant_id"],
        name=d["name"],
        description=d.get("description"),
        embedding_model=d["embedding_model"],
        embedding_dim=d["embedding_dim"],
        qdrant_collection=d["qdrant_collection"],
        chunk_size=d["chunk_size"],
        chunk_overlap=d["chunk_overlap"],
        is_active=d["is_active"],
        created_at=d["created_at"],
    )


@router.get("/collections", response_model=list[CollectionOut], tags=["rag-collections"])
async def list_collections(
    user: CurrentUser = Depends(get_current_user),
) -> list[CollectionOut]:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    res = sb.table("rag_collections").select("*").eq("tenant_id", str(tenant_id)).eq("is_active", True).execute()
    return [
        CollectionOut(
            id=d["id"],
            tenant_id=d["tenant_id"],
            name=d["name"],
            description=d.get("description"),
            embedding_model=d["embedding_model"],
            embedding_dim=d["embedding_dim"],
            qdrant_collection=d["qdrant_collection"],
            chunk_size=d["chunk_size"],
            chunk_overlap=d["chunk_overlap"],
            is_active=d["is_active"],
            created_at=d["created_at"],
        )
        for d in (res.data or [])
    ]


@router.get("/collections/{collection_id}", response_model=CollectionOut, tags=["rag-collections"])
async def get_collection(
    collection_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> CollectionOut:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    res = sb.table("rag_collections").select("*").eq("id", str(collection_id)).eq("tenant_id", str(tenant_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    d = res.data[0]
    return CollectionOut(**{k: d[k] for k in CollectionOut.model_fields if k in d})


# ----------------------------------------------------------------------
# Documents
# ----------------------------------------------------------------------

async def _ingest_upload(
    *,
    file: UploadFile,
    collection_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str | None,
    source: str,
) -> DocumentOut:
    sb = get_supabase_admin()
    # 1) validate collection
    cres = sb.table("rag_collections").select("*").eq("id", str(collection_id)).eq("tenant_id", str(tenant_id)).execute()
    if not cres.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    coll = cres.data[0]

    # 2) create document row
    document_id = uuid.uuid4()
    doc_row = {
        "id": str(document_id),
        "tenant_id": str(tenant_id),
        "collection_id": str(collection_id),
        "name": file.filename or "document",
        "display_name": display_name or file.filename or "document",
        "source": source,
        "mime_type": file.content_type,
        "size_bytes": 0,
        "status": "pending",
        "uploaded_by": str(user_id),
        "metadata": {"uploaded_via": "api"},
    }
    ins = sb.table("rag_documents").insert(doc_row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="Failed to create document row")
    doc_row_id = ins.data[0]["id"]

    # 3) save file to a temp path
    tmp_dir = os.path.join(os.path.dirname(__file__), "..", ".tmp_rag_uploads")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{document_id}_{file.filename or 'doc'}")
    size = 0
    with open(tmp_path, "wb") as fh:
        while chunk := await file.read(64 * 1024):
            fh.write(chunk)
            size += len(chunk)
    sb.table("rag_documents").update({"size_bytes": size}).eq("id", doc_row_id).execute()

    # 4) ingest
    sb.table("rag_documents").update({"status": "parsing"}).eq("id", doc_row_id).execute()
    service = _get_service()
    try:
        result = service.ingest_file(
            file_path=tmp_path,
            mime_type=file.content_type,
            collection_id=collection_id,
            document_id=document_id,
            document_name=file.filename or "document",
            qdrant_collection=coll["qdrant_collection"],
        )
    except Exception as exc:  # noqa: BLE001
        sb.table("rag_documents").update({
            "status": "failed",
            "error_message": str(exc)[:500],
        }).eq("id", doc_row_id).execute()
        raise HTTPException(status_code=400, detail=f"Ingestion failed: {exc}")

    # 5) update document row
    final = sb.table("rag_documents").update({
        "status": "indexed",
        "total_chunks": len(result.chunks),
        "total_tokens": result.total_tokens,
    }).eq("id", doc_row_id).execute()
    row = final.data[0]

    # 6) write chunks mirror to pgvector
    for c, vec in zip(result.chunks, service.embedder.embed([cc.content for cc in result.chunks])):
        sb.table("rag_chunks").insert({
            "id": str(c.chunk_id),
            "document_id": str(document_id),
            "tenant_id": str(tenant_id),
            "collection_id": str(collection_id),
            "position": c.position,
            "content": c.content,
            "token_count": c.token_count,
            "embedding": vec,
            "metadata": c.metadata,
        }).execute()

    # cleanup
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    return DocumentOut(
        id=row["id"],
        collection_id=row["collection_id"],
        name=row["name"],
        display_name=row["display_name"],
        source=row["source"],
        mime_type=row.get("mime_type"),
        size_bytes=row.get("size_bytes", 0),
        status=row["status"],
        total_chunks=row.get("total_chunks", 0),
        total_tokens=row.get("total_tokens", 0),
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/documents", response_model=DocumentOut, tags=["rag-documents"])
async def upload_document(
    file: UploadFile = File(...),
    collection_id: uuid.UUID = Form(...),
    display_name: str | None = Form(None),
    source: str = Form("upload"),
    user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    tenant_id = _require_tenant(user)
    return await _ingest_upload(
        file=file,
        collection_id=collection_id,
        tenant_id=tenant_id,
        user_id=user.id,
        display_name=display_name,
        source=source,
    )


@router.get("/documents", response_model=list[DocumentOut], tags=["rag-documents"])
async def list_documents(
    collection_id: uuid.UUID = Query(...),
    user: CurrentUser = Depends(get_current_user),
) -> list[DocumentOut]:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    res = (
        sb.table("rag_documents")
        .select("*")
        .eq("tenant_id", str(tenant_id))
        .eq("collection_id", str(collection_id))
        .neq("status", "deleted")
        .order("created_at", desc=True)
        .execute()
    )
    return [DocumentOut(**d) for d in (res.data or [])]


@router.get("/documents/{document_id}", response_model=DocumentOut, tags=["rag-documents"])
async def get_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    res = sb.table("rag_documents").select("*").eq("id", str(document_id)).eq("tenant_id", str(tenant_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut(**res.data[0])


# ----------------------------------------------------------------------
# Query
# ----------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse, tags=["rag-query"])
async def query_rag(
    body: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
) -> QueryResponse:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()

    cres = sb.table("rag_collections").select("*").eq("id", str(body.collection_id)).eq("tenant_id", str(tenant_id)).execute()
    if not cres.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    coll = cres.data[0]

    service = _get_service()
    t0 = time.perf_counter()
    result = service.query(
        body.query,
        collection_id=body.collection_id,
        qdrant_collection=coll["qdrant_collection"],
        top_k=body.top_k,
        mode=body.mode,
        use_reranker=body.use_reranker,
        use_citations=body.use_citations,
    )
    total_ms = int((time.perf_counter() - t0) * 1000)

    # write query log
    try:
        sb.table("rag_query_logs").insert({
            "tenant_id": str(tenant_id),
            "collection_id": str(body.collection_id),
            "query": body.query,
            "retrieved_ids": [str(c.chunk_id) for c in result.chunks],
            "citations": [c.to_dict() for c in result.citations],
            "answer": result.answer,
            "retrieval_ms": result.retrieval_ms,
            "generation_ms": result.generation_ms,
            "total_tokens": sum(c.token_count for c in result.chunks),
            "model": coll["embedding_model"],
            "user_id": str(user.id),
        }).execute()
    except Exception:  # noqa: BLE001
        pass  # logging should never fail the request

    return QueryResponse(
        query=result.query,
        answer=result.answer,
        citations=[
            CitationOut(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                document_name=c.document_name,
                position=c.position,
                snippet=c.snippet,
                score=c.score,
                rerank_score=c.rerank_score,
                token=c.token(),
            )
            for c in result.citations
        ],
        retrieval_ms=result.retrieval_ms,
        rerank_ms=result.rerank_ms,
        generation_ms=result.generation_ms,
        total_ms=total_ms,
        metadata=result.metadata,
    )


@router.post("/query/stream", tags=["rag-query"])
async def query_rag_stream(
    body: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    tenant_id = _require_tenant(user)
    sb = get_supabase_admin()
    cres = sb.table("rag_collections").select("*").eq("id", str(body.collection_id)).eq("tenant_id", str(tenant_id)).execute()
    if not cres.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    coll = cres.data[0]
    service = _get_service()

    async def event_source() -> AsyncIterator[bytes]:
        result = service.query(
            body.query,
            collection_id=body.collection_id,
            qdrant_collection=coll["qdrant_collection"],
            top_k=body.top_k,
            mode=body.mode,
        )
        meta_payload = {
            "retrieval_ms": result.retrieval_ms,
            "rerank_ms": result.rerank_ms,
            "chunks": [c.model_dump(mode="json") for c in result.chunks],
            "citations": [c.to_dict() for c in result.citations],
        }
        yield f"event: metadata\ndata: {json.dumps(meta_payload)}\n\n".encode()
        # stream answer in chunks
        for i in range(0, len(result.answer), 80):
            chunk = result.answer[i : i + 80]
            token_payload = json.dumps({"text": chunk})
            yield f"event: token\ndata: {token_payload}\n\n".encode()
            await asyncio.sleep(0.005)
        done_payload = json.dumps({"total_ms": result.total_ms})
        yield f"event: done\ndata: {done_payload}\n\n".encode()

    return StreamingResponse(event_source(), media_type="text/event-stream")


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------

@router.get("/health", tags=["rag-health"])
async def rag_health(
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    tenant_id = _require_tenant(user)
    return {
        "status": "ok",
        "tenant_id": str(tenant_id),
        "embedding_model": EmbeddingModel.BGE_LARGE.value,
        "qdrant_url": os.environ.get("QDRANT_URL"),
        "components": {
            "parser": "DocumentParser",
            "chunker": "SentenceSplitter",
            "embedder": EmbeddingModel.BGE_LARGE.value,
            "retriever": "QdrantVectorStore + BM25 hybrid",
            "reranker": Reranker.DEFAULT_MODEL,
            "generator": "ResponseSynthesizer(compact)",
        },
    }
