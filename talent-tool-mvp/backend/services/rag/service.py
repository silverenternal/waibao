"""RagService — high-level orchestrator that ties parser / chunker / embedder /
retriever / reranker / generator / citation together.

This is the only public entry point for the API layer.  All long-lived
components (Qdrant client, embedder, reranker) are constructed once and
shared across requests via the singleton factory `get_rag_service()`.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from .chunker import Chunk, Chunker
from .citation import Citation, CitationFormatter
from .document_parser import DocumentParser, ParsedDocument
from .embedder import Embedder, EmbeddingModel
from .generator import GenerationConfig, Generator, GeneratorMode
from .models import (
    DocumentStatus,
    RagCollection,
    RagDocument,
    RetrievedChunk,
    RetrievalMode,
)
from .reranker import Reranker
from .retriever import Retriever, RetrievalConfig


logger = logging.getLogger("recruittech.rag.service")


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class RagServiceError(Exception):
    """Base error for the RAG service."""

    def __init__(self, message: str, *, code: str = "rag_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# ----------------------------------------------------------------------
# Result containers
# ----------------------------------------------------------------------

@dataclass
class IngestionResult:
    document_id: uuid.UUID
    chunks: list[Chunk] = field(default_factory=list)
    total_tokens: int = 0
    parse_ms: int = 0
    chunk_ms: int = 0
    embed_ms: int = 0
    index_ms: int = 0

    def total_ms(self) -> int:
        return self.parse_ms + self.chunk_ms + self.embed_ms + self.index_ms


@dataclass
class QueryResult:
    query: str
    answer: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    retrieval_ms: int = 0
    generation_ms: int = 0
    rerank_ms: int = 0
    total_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "chunks": [c.model_dump(mode="json") for c in self.chunks],
            "citations": [c.to_dict() for c in self.citations],
            "retrieval_ms": self.retrieval_ms,
            "generation_ms": self.generation_ms,
            "rerank_ms": self.rerank_ms,
            "total_ms": self.total_ms,
            "metadata": self.metadata,
        }


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------

class RagService:
    """High-level RAG orchestrator.

    All components are pluggable — tests can inject mocks by passing
    pre-constructed collaborators to the constructor.
    """

    def __init__(
        self,
        *,
        parser: DocumentParser | None = None,
        chunker: Chunker | None = None,
        embedder: Embedder | None = None,
        retriever: Retriever | None = None,
        reranker: Reranker | None = None,
        generator: Generator | None = None,
        citation_formatter: CitationFormatter | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_model: EmbeddingModel = EmbeddingModel.BGE_LARGE,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        self.parser = parser or DocumentParser()
        self.chunker = chunker or Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embedder = embedder or Embedder(model=embedding_model)
        self.retriever = retriever or Retriever(RetrievalConfig(
            qdrant_url=qdrant_url or os.environ.get("QDRANT_URL"),
            qdrant_api_key=qdrant_api_key or os.environ.get("QDRANT_API_KEY"),
        ))
        self.reranker = reranker or Reranker()
        self.generator = generator or Generator(GenerationConfig(
            mode=GeneratorMode.COMPACT,
        ))
        self.citation_formatter = citation_formatter or CitationFormatter()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_text(
        self,
        *,
        text: str,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        document_name: str,
        qdrant_collection: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        if not text or not text.strip():
            raise RagServiceError("Cannot ingest empty text", code="empty_text")

        t0 = time.perf_counter()
        parsed = self.parser.parse_text(text, source=metadata.get("source", "raw") if metadata else "raw")
        parse_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        chunks = self.chunker._split_one(parsed)  # noqa: SLF001 — internal use OK
        chunk_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        texts = [c.content for c in chunks]
        if texts:
            vectors = self.embedder.embed(texts)
        else:
            vectors = []
        embed_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        for c, v in zip(chunks, vectors):
            self.retriever.add(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_name=document_name,
                collection_id=collection_id,
                position=c.position,
                content=c.content,
                embedding=v,
                metadata=c.metadata,
                qdrant_collection=qdrant_collection,
            )
        index_ms = int((time.perf_counter() - t0) * 1000)

        return IngestionResult(
            document_id=document_id,
            chunks=chunks,
            total_tokens=sum(c.token_count for c in chunks),
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
            index_ms=index_ms,
        )

    def ingest_file(
        self,
        *,
        file_path: str,
        mime_type: str | None,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        document_name: str,
        qdrant_collection: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        if not self.parser.supports(file_path, mime_type):
            raise RagServiceError(
                f"Unsupported file: {file_path} (mime={mime_type})",
                code="unsupported_file",
            )

        t0 = time.perf_counter()
        parsed = self.parser.parse(file_path, mime_type)
        parse_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        parsed.document_id = document_id
        chunks = self.chunker._split_one(parsed)  # noqa: SLF001
        chunk_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        texts = [c.content for c in chunks]
        vectors = self.embedder.embed(texts) if texts else []
        embed_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        for c, v in zip(chunks, vectors):
            self.retriever.add(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_name=document_name,
                collection_id=collection_id,
                position=c.position,
                content=c.content,
                embedding=v,
                metadata={**(c.metadata or {}), **(metadata or {})},
                qdrant_collection=qdrant_collection,
            )
        index_ms = int((time.perf_counter() - t0) * 1000)

        return IngestionResult(
            document_id=document_id,
            chunks=chunks,
            total_tokens=sum(c.token_count for c in chunks),
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            embed_ms=embed_ms,
            index_ms=index_ms,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def query(
        self,
        query: str,
        *,
        collection_id: uuid.UUID,
        qdrant_collection: str | None = None,
        top_k: int = 5,
        mode: RetrievalMode | None = None,
        use_reranker: bool = True,
        use_citations: bool = True,
    ) -> QueryResult:
        if not query or not query.strip():
            raise RagServiceError("Query must be non-empty", code="empty_query")

        cfg = self.retriever.config
        prev_mode = cfg.mode
        try:
            if mode is not None:
                cfg.mode = mode
            t0 = time.perf_counter()
            query_vec = self.embedder.embed_one(query)
            chunks = self.retriever.retrieve(
                query=query,
                query_embedding=query_vec,
                collection_id=collection_id,
                top_k=top_k,
                qdrant_collection=qdrant_collection,
            )
            retrieval_ms = int((time.perf_counter() - t0) * 1000)
        finally:
            cfg.mode = prev_mode

        t0 = time.perf_counter()
        if use_reranker and chunks:
            chunks = self.reranker.rerank(query, chunks, top_k=top_k)
        rerank_ms = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        answer = self.generator.generate(query, chunks)
        generation_ms = int((time.perf_counter() - t0) * 1000)

        citations: list[Citation] = []
        if use_citations:
            answer, citations = self.citation_formatter.format(answer, chunks)

        return QueryResult(
            query=query,
            answer=answer,
            chunks=chunks,
            citations=citations,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            rerank_ms=rerank_ms,
            total_ms=retrieval_ms + rerank_ms + generation_ms,
            metadata={
                "collection_id": str(collection_id),
                "top_k": top_k,
                "mode": cfg.mode.value,
                "use_reranker": use_reranker,
            },
        )

    # ------------------------------------------------------------------
    # Streamed query — yield partial answers
    # ------------------------------------------------------------------
    def query_stream(
        self,
        query: str,
        *,
        collection_id: uuid.UUID,
        qdrant_collection: str | None = None,
        top_k: int = 5,
    ) -> Iterable[dict[str, Any]]:
        result = self.query(
            query,
            collection_id=collection_id,
            qdrant_collection=qdrant_collection,
            top_k=top_k,
        )
        # emit metadata
        yield {
            "event": "metadata",
            "data": {
                "retrieval_ms": result.retrieval_ms,
                "rerank_ms": result.rerank_ms,
                "chunks": [c.model_dump(mode="json") for c in result.chunks],
                "citations": [c.to_dict() for c in result.citations],
            },
        }
        # emit answer in fixed-size chunks (true streaming would require
        # an OpenAI streaming call — we emit a small fallback here)
        text = result.answer
        chunk = 80
        for i in range(0, len(text), chunk):
            yield {"event": "token", "data": {"text": text[i : i + chunk]}}
        yield {
            "event": "done",
            "data": {
                "total_ms": result.total_ms,
                "generation_ms": result.generation_ms,
            },
        }


# ----------------------------------------------------------------------
# Singleton factory
# ----------------------------------------------------------------------

_singleton: RagService | None = None


def get_rag_service() -> RagService:
    """Lazily build a process-wide `RagService`."""
    global _singleton
    if _singleton is None:
        _singleton = RagService()
    return _singleton


def reset_rag_service() -> None:
    """Drop the cached service (used in tests)."""
    global _singleton
    _singleton = None
