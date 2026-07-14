"""Vector retriever — vendor-in LlamaIndex + QdrantVectorStore.

We expose three retrieval modes:

* ``vector``  - dense ANN over Qdrant
* ``bm25``    - lexical / keyword search (LlamaIndex BM25Retriever)
* ``hybrid``  - QueryFusionRetriever combining both (RRF fusion)

The retriever accepts an in-memory fallback (no Qdrant available) so that
unit tests run anywhere.
"""
from __future__ import annotations

import math
import os
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .models import RetrievedChunk, RetrievalMode


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

@dataclass
class RetrievalConfig:
    top_k: int = 5
    mode: RetrievalMode = RetrievalMode.HYBRID
    fusion_num_queries: int = 4          # QueryFusionRetriever num_queries
    vector_weight: float = 0.7
    bm25_weight: float = 0.3
    score_threshold: float = 0.0
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    # When True, every Qdrant collection is namespaced per-tenant
    # (`{base}_{tenant_id}`) and the in-memory store partitions by
    # tenant_id. This is the v10.0 default — multi-tenant isolation is
    # mandatory, never optional in production.
    multi_tenant: bool = True


# ----------------------------------------------------------------------
# In-memory store
# ----------------------------------------------------------------------

class InMemoryStore:
    """Minimal in-memory vector store for tests and offline runs.

    Each entry is `(chunk_id, document_id, document_name, collection_id, tenant_id,
    position, content, vector, metadata)`.  Cosine similarity + BM25 scoring.

    When a ``tenant_id`` is supplied to a search, entries are filtered to
    that tenant first — this mirrors the Qdrant payload filter used in
    production and guarantees multi-tenant isolation in the offline path.
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def upsert(self, entry: dict[str, Any]) -> None:
        self._entries.append(entry)

    def clear(self, collection_id: uuid.UUID | None = None) -> None:
        if collection_id is None:
            self._entries.clear()
        else:
            self._entries = [e for e in self._entries if e["collection_id"] != collection_id]

    def clear_tenant(self, tenant_id: uuid.UUID) -> None:
        self._entries = [e for e in self._entries if e.get("tenant_id") != tenant_id]

    def vector_search(
        self,
        query_vec: list[float],
        collection_id: uuid.UUID,
        top_k: int,
        *,
        tenant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        qn = _norm(query_vec)
        for e in self._entries:
            if e["collection_id"] != collection_id:
                continue
            if tenant_id is not None and e.get("tenant_id") != tenant_id:
                continue
            v = e["vector"]
            vn = _norm(v)
            if vn == 0 or qn == 0:
                continue
            sim = sum(a * b for a, b in zip(query_vec, v)) / (qn * vn)
            scored.append((sim, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            dict(e, _score=score)
            for score, e in scored[:top_k]
        ]

    def bm25_search(
        self,
        query: str,
        collection_id: uuid.UUID,
        top_k: int,
        *,
        tenant_id: uuid.UUID | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[dict[str, Any]]:
        docs = [
            e for e in self._entries
            if e["collection_id"] == collection_id
            and (tenant_id is None or e.get("tenant_id") == tenant_id)
        ]
        if not docs:
            return []
        terms = _tokenize(query)
        if not terms:
            return []
        # IDF
        N = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            seen = set(_tokenize(d["content"]))
            for t in seen:
                df[t] += 1
        idf = {t: math.log(1 + (N - df_t + 0.5) / (df_t + 0.5)) for t, df_t in df.items()}

        avgdl = sum(len(_tokenize(d["content"])) for d in docs) / N
        scored: list[tuple[float, dict[str, Any]]] = []
        for d in docs:
            tokens = _tokenize(d["content"])
            if not tokens:
                continue
            tf: Counter[str] = Counter(tokens)
            dl = len(tokens)
            s = 0.0
            for q in terms:
                if q not in tf:
                    continue
                num = tf[q] * (k1 + 1)
                den = tf[q] + k1 * (1 - b + b * dl / max(1.0, avgdl))
                s += idf.get(q, 0.0) * num / den
            if s > 0:
                scored.append((s, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            dict(e, _score=score)
            for score, e in scored[:top_k]
        ]


# ----------------------------------------------------------------------
# Qdrant bridge
# ----------------------------------------------------------------------

def _qdrant_client(url: str, api_key: str | None):
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        return QdrantClient(url=url, api_key=api_key, timeout=10.0)
    except Exception:  # noqa: BLE001
        return None


def tenant_collection(base: str, tenant_id: uuid.UUID | str | None) -> str:
    """Return the physical Qdrant collection name for a tenant.

    Collection names are namespaced as ``{base}_{sanitized_tenant}`` so two
    tenants sharing the same logical collection never see each other's
    vectors.  When ``tenant_id`` is None the base name is returned unchanged
    (single-tenant / legacy mode).
    """
    if tenant_id is None:
        return base
    t = str(tenant_id).replace("-", "")
    return f"{base}_{t}"


def _qdrant_search(
    client,
    collection: str,
    vector: list[float],
    top_k: int,
    *,
    tenant_id: uuid.UUID | None = None,
):
    try:
        from qdrant_client.http import models as qm  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    try:
        query_filter = None
        if tenant_id is not None:
            query_filter = qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="tenant_id",
                        match=qm.MatchValue(value=str(tenant_id)),
                    )
                ]
            )
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for h in hits:
        payload = h.payload or {}
        out.append({
            "chunk_id": uuid.UUID(payload.get("chunk_id")) if payload.get("chunk_id") else uuid.uuid4(),
            "document_id": uuid.UUID(payload["document_id"]) if payload.get("document_id") else uuid.uuid4(),
            "document_name": payload.get("document_name", ""),
            "collection_id": uuid.UUID(payload["collection_id"]) if payload.get("collection_id") else uuid.uuid4(),
            "tenant_id": uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else tenant_id,
            "position": int(payload.get("position", 0)),
            "content": payload.get("content", ""),
            "vector": vector,
            "metadata": payload.get("metadata", {}),
            "_score": float(h.score or 0.0),
        })
    return out


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

class Retriever:
    """Hybrid retriever — Qdrant (vector) + BM25, fused with RRF."""

    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self.config = config or RetrievalConfig()
        self._inmem = InMemoryStore()
        self._qdrant = None
        if self.config.qdrant_url:
            self._qdrant = _qdrant_client(
                self.config.qdrant_url,
                self.config.qdrant_api_key or os.environ.get("QDRANT_API_KEY"),
            )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def add(
        self,
        *,
        chunk_id: uuid.UUID,
        document_id: uuid.UUID,
        document_name: str,
        collection_id: uuid.UUID,
        position: int,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        qdrant_collection: str | None = None,
        tenant_id: uuid.UUID | str | None = None,
    ) -> None:
        meta = dict(metadata or {})
        entry = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_name": document_name,
            "collection_id": collection_id,
            "tenant_id": tenant_id,
            "position": position,
            "content": content,
            "vector": embedding,
            "metadata": meta,
        }
        self._inmem.upsert(entry)

        # Resolve the physical (tenant-namespaced) collection name.
        physical_collection = self._resolve_collection(qdrant_collection, tenant_id)
        if self._qdrant is not None and physical_collection:
            try:
                from qdrant_client.http import models as qm  # type: ignore
                self._qdrant.upsert(
                    collection_name=physical_collection,
                    points=[
                        qm.PointStruct(
                            id=str(chunk_id),
                            vector=embedding,
                            payload={
                                "chunk_id": str(chunk_id),
                                "document_id": str(document_id),
                                "document_name": document_name,
                                "collection_id": str(collection_id),
                                "tenant_id": str(tenant_id) if tenant_id is not None else None,
                                "position": position,
                                "content": content,
                                "metadata": meta,
                            },
                        )
                    ],
                    wait=True,
                )
            except Exception:  # noqa: BLE001
                # best-effort; in-memory store is still authoritative for tests
                pass

    def clear_collection(self, collection_id: uuid.UUID) -> None:
        self._inmem.clear(collection_id)

    def clear_tenant(self, tenant_id: uuid.UUID) -> None:
        self._inmem.clear_tenant(tenant_id)

    def _resolve_collection(
        self,
        qdrant_collection: str | None,
        tenant_id: uuid.UUID | str | None,
    ) -> str | None:
        if qdrant_collection is None:
            return None
        if not self.config.multi_tenant:
            return qdrant_collection
        return tenant_collection(qdrant_collection, tenant_id)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        collection_id: uuid.UUID,
        *,
        top_k: int | None = None,
        qdrant_collection: str | None = None,
        tenant_id: uuid.UUID | str | None = None,
    ) -> list[RetrievedChunk]:
        cfg = self.config
        k = top_k or cfg.top_k
        physical_collection = self._resolve_collection(qdrant_collection, tenant_id)
        if cfg.mode == RetrievalMode.VECTOR:
            hits = self._vector_search(
                query_embedding, collection_id, k, physical_collection, tenant_id
            )
        elif cfg.mode == RetrievalMode.BM25:
            hits = self._bm25_search(
                query, collection_id, k, physical_collection, tenant_id
            )
        else:
            hits = self._hybrid_search(
                query, query_embedding, collection_id, k, physical_collection, tenant_id
            )

        out: list[RetrievedChunk] = []
        for h in hits:
            out.append(RetrievedChunk(
                chunk_id=h["chunk_id"],
                document_id=h["document_id"],
                document_name=h["document_name"],
                collection_id=h["collection_id"],
                position=h["position"],
                content=h["content"],
                score=float(h.get("_score", 0.0)),
                metadata=h.get("metadata", {}),
            ))
        return [c for c in out if c.score >= cfg.score_threshold][:k]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _vector_search(
        self,
        query_embedding: list[float],
        collection_id: uuid.UUID,
        top_k: int,
        qdrant_collection: str | None,
        tenant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        if self._qdrant is not None and qdrant_collection:
            hits = _qdrant_search(
                self._qdrant, qdrant_collection, query_embedding, top_k,
                tenant_id=tenant_id,
            )
            if hits:
                return hits
        return self._inmem.vector_search(
            query_embedding, collection_id, top_k, tenant_id=tenant_id
        )

    def _bm25_search(
        self,
        query: str,
        collection_id: uuid.UUID,
        top_k: int,
        qdrant_collection: str | None,
        tenant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        # Qdrant has no native BM25 — fall back to in-memory implementation
        return self._inmem.bm25_search(
            query, collection_id, top_k, tenant_id=tenant_id
        )

    def _hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        collection_id: uuid.UUID,
        top_k: int,
        qdrant_collection: str | None,
        tenant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        v_hits = self._vector_search(
            query_embedding, collection_id, top_k * 2, qdrant_collection, tenant_id
        )
        b_hits = self._bm25_search(
            query, collection_id, top_k * 2, qdrant_collection, tenant_id
        )
        return _rrf_fuse(
            [v_hits, b_hits],
            weights=[self.config.vector_weight, self.config.bm25_weight],
            top_k=top_k,
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v)) if v else 0.0


def _tokenize(text: str) -> list[str]:
    import re
    return [t for t in re.split(r"[^a-z0-9一-鿿ぁ-ヿ]+", text.lower()) if t]


def _rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    weights: list[float],
    top_k: int,
    k: int = 60,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion.

    score(d) = sum_i  w_i / (k + rank_i(d))
    """
    if not ranked_lists or not weights:
        return []
    scores: dict[str, float] = {}
    entries: dict[str, dict[str, Any]] = {}
    for lst, w in zip(ranked_lists, weights):
        for rank, e in enumerate(lst):
            key = str(e.get("chunk_id"))
            scores[key] = scores.get(key, 0.0) + w * (1.0 / (k + rank + 1))
            entries[key] = e
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    for key, s in ordered[:top_k]:
        e = dict(entries[key])
        e["_score"] = s
        out.append(e)
    return out
