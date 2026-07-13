"""Pydantic models for the RAG module.

Pure data containers — no vendor imports — to keep the boundary thin and
allow callers (services, API, tests) to depend on a stable shape.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class RetrievalMode(str, Enum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"


# ----------------------------------------------------------------------
# Persistence models (mirror the SQL migration)
# ----------------------------------------------------------------------

class RagCollection(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None = None
    embedding_model: str = "bge-large-en-v1.5"
    embedding_dim: int = 1024
    qdrant_collection: str
    chunk_size: int = 512
    chunk_overlap: int = 50
    reranker_model: str = "bge-reranker-large"
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class RagDocument(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    collection_id: uuid.UUID
    name: str
    display_name: str
    source: str
    mime_type: str | None = None
    size_bytes: int = 0
    storage_path: str | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: str | None = None
    total_chunks: int = 0
    total_tokens: int = 0
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    uploaded_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------
# In-memory pipeline models
# ----------------------------------------------------------------------

class RetrievedChunk(BaseModel):
    """One retrieved chunk with optional score, ready for re-ranking / generation."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    collection_id: uuid.UUID
    position: int
    content: str
    score: float = 0.0
    rerank_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = 0

    def citation_token(self) -> str:
        """Stable token used for in-text citations, e.g. [doc_id:chunk_id]."""
        short_doc = str(self.document_id)[:8]
        short_chunk = str(self.chunk_id)[:8]
        return f"[{short_doc}:{short_chunk}]"
