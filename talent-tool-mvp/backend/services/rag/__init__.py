"""RAG service package — T2701.

Vendor-in LlamaIndex components for:
  - document parsing (PDF/Word/Markdown/HTML/text)
  - chunking (SentenceSplitter)
  - embedding (OpenAI / BGE)
  - retrieval (Qdrant + BM25 hybrid)
  - reranking (BGE-reranker)
  - generation (ResponseSynthesizer)
  - citation injection

Public API:
  - DocumentParser.parse(file_path, mime_type) -> list[Document]
  - Chunker.split(documents) -> list[Chunk]
  - Embedder.embed(texts) -> list[list[float]]
  - Retriever.retrieve(query, top_k) -> list[RetrievedChunk]
  - Reranker.rerank(query, chunks, top_k) -> list[RetrievedChunk]
  - Generator.generate(query, chunks) -> str
  - CitationFormatter.format(answer, chunks) -> (answer, citations)
  - RagService  - high-level orchestrator
"""
from __future__ import annotations

from .chunker import Chunker, Chunk
from .citation import Citation, CitationFormatter
from .document_parser import DocumentParser, ParsedDocument
from .embedder import Embedder, EmbeddingModel
from .generator import Generator, GenerationConfig, GeneratorMode
from .models import (
    DocumentStatus,
    RagCollection,
    RagDocument,
    RetrievedChunk,
)
from .reranker import Reranker
from .retriever import Retriever, RetrievalConfig, RetrievalMode
from .service import RagService, RagServiceError, get_rag_service, reset_rag_service

__all__ = [
    "Chunker",
    "Chunk",
    "Citation",
    "CitationFormatter",
    "DocumentParser",
    "DocumentStatus",
    "Embedder",
    "EmbeddingModel",
    "GenerationConfig",
    "Generator",
    "GeneratorMode",
    "ParsedDocument",
    "RagCollection",
    "RagDocument",
    "RagService",
    "RagServiceError",
    "get_rag_service",
    "reset_rag_service",
    "Reranker",
    "RetrievedChunk",
    "Retriever",
    "RetrievalConfig",
    "RetrievalMode",
]
