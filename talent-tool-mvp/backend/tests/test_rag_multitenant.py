"""T5020 — RAG multi-tenant isolation tests."""
from __future__ import annotations

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.rag.embedder import Embedder, EmbeddingModel  # noqa: E402
from services.rag.retriever import (  # noqa: E402
    RetrievalConfig,
    Retriever,
    RetrievalMode,
    tenant_collection,
)


TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
COLL = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _build_retriever(mode=RetrievalMode.VECTOR):
    return Retriever(RetrievalConfig(mode=mode, multi_tenant=True, qdrant_url=None))


def _seed(retriever, tenant_id, content):
    emb = Embedder(model=EmbeddingModel.MOCK)
    cid = uuid.uuid4()
    did = uuid.uuid4()
    vec = emb.embed_one(content)
    retriever.add(
        chunk_id=cid,
        document_id=did,
        document_name=content[:12],
        collection_id=COLL,
        tenant_id=tenant_id,
        position=0,
        content=content,
        embedding=vec,
        qdrant_collection="kb",
    )
    return vec


def test_tenant_collection_namespacing():
    base = "knowledge_base"
    a = tenant_collection(base, TENANT_A)
    b = tenant_collection(base, TENANT_B)
    bare = tenant_collection(base, None)
    assert a != b
    assert a.startswith(base + "_")
    assert bare == base


def test_tenant_a_cannot_retrieve_tenant_b_documents_vector():
    r = _build_retriever(RetrievalMode.VECTOR)
    _seed(r, TENANT_A, "python backend engineer senior")
    _seed(r, TENANT_B, "frontend react designer junior")

    emb = Embedder(model=EmbeddingModel.MOCK)
    q = emb.embed_one("python backend engineer")
    hits = r.retrieve("python backend engineer", q, COLL,
                      tenant_id=TENANT_A, qdrant_collection="kb", top_k=5)
    contents = [h.content for h in hits]
    assert any("python backend" in c for c in contents)
    assert not any("frontend react" in c for c in contents), "tenant B leaked into A"


def test_tenant_isolation_bm25():
    r = _build_retriever(RetrievalMode.BM25)
    _seed(r, TENANT_A, "exclusive tenant a keyword zeta")
    _seed(r, TENANT_B, "exclusive tenant b keyword omega")

    emb = Embedder(model=EmbeddingModel.MOCK)
    hits_b = r.retrieve("zeta", emb.embed_one("zeta"), COLL,
                        tenant_id=TENANT_B, qdrant_collection="kb")
    assert all("zeta" not in h.content for h in hits_b), "tenant A leaked into B via BM25"


def test_tenant_isolation_hybrid():
    r = _build_retriever(RetrievalMode.HYBRID)
    _seed(r, TENANT_A, "hybrid tenant alpha document")
    _seed(r, TENANT_B, "hybrid tenant beta document")

    emb = Embedder(model=EmbeddingModel.MOCK)
    hits = r.retrieve("hybrid alpha", emb.embed_one("hybrid alpha"), COLL,
                      tenant_id=TENANT_A, qdrant_collection="kb")
    assert all("beta" not in h.content for h in hits)


def test_clear_tenant_only_affects_that_tenant():
    r = _build_retriever(RetrievalMode.VECTOR)
    _seed(r, TENANT_A, "tenant a unique content gamma")
    _seed(r, TENANT_B, "tenant b unique content delta")

    r.clear_tenant(TENANT_A)

    emb = Embedder(model=EmbeddingModel.MOCK)
    hits_a = r.retrieve("gamma", emb.embed_one("gamma"), COLL,
                        tenant_id=TENANT_A, qdrant_collection="kb")
    hits_b = r.retrieve("delta", emb.embed_one("delta"), COLL,
                        tenant_id=TENANT_B, qdrant_collection="kb")
    assert hits_a == []
    assert any("delta" in h.content for h in hits_b)


def test_multitenant_disabled_shares_collection():
    r = Retriever(RetrievalConfig(mode=RetrievalMode.VECTOR, multi_tenant=False, qdrant_url=None))
    assert r._resolve_collection("kb", TENANT_A) == "kb"
