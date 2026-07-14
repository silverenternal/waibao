"""T5020 — RAG real embedding + cache + incremental + streaming tests."""
from __future__ import annotations

import asyncio
import math
import os
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.rag.embedder import (  # noqa: E402
    Embedder,
    EmbeddingCache,
    EmbeddingError,
    EmbeddingModel,
    _deterministic_vector,
)
from services.rag.reranker import Reranker  # noqa: E402
from services.rag.models import RetrievedChunk  # noqa: E402
from services.rag.streaming import StreamingGenerator  # noqa: E402
from services.rag.generator import GenerationConfig, GeneratorMode  # noqa: E402


# ---------------------------------------------------------------------------
# Embedder + cache
# ---------------------------------------------------------------------------

def test_embedder_mock_returns_deterministic_normalized_vectors():
    emb = Embedder(model=EmbeddingModel.MOCK, normalize=True, cache=None)
    a = emb.embed_one("hello world")
    b = emb.embed_one("hello world")
    assert a == b
    assert len(a) == EmbeddingModel.MOCK.dim
    norm = math.sqrt(sum(x * x for x in a))
    assert abs(norm - 1.0) < 1e-6


def test_embedder_cache_hits_avoid_recompute(tmp_path):
    calls = {"n": 0}
    cache = EmbeddingCache(root=tmp_path)

    class CountingEmbedder(Embedder):
        def _compute(self, texts, *, real):  # type: ignore[override]
            calls["n"] += len(texts)
            return super()._compute(texts, real=real)

    emb = CountingEmbedder(model=EmbeddingModel.MOCK, cache=cache)
    emb.embed(["alpha", "beta"])
    emb.embed(["alpha", "beta"])  # fully cached
    assert calls["n"] == 2  # second call served from cache
    stats = cache.stats()
    assert stats["hits"] >= 2


def test_embedder_incremental_only_embeds_new_texts(tmp_path):
    cache = EmbeddingCache(root=tmp_path)
    calls = {"n": 0}

    class CountingEmbedder(Embedder):
        def _compute(self, texts, *, real):  # type: ignore[override]
            calls["n"] += len(texts)
            return super()._compute(texts, real=real)

    emb = CountingEmbedder(model=EmbeddingModel.MOCK, cache=cache)
    emb.embed(["one", "two"])
    calls["n"] = 0
    # add one new + one existing -> only the new one should hit _compute
    emb.embed(["two", "three"])
    assert calls["n"] == 1


def test_embedder_real_raises_when_no_backend():
    # No OPENAI_API_KEY and no HF endpoint -> real=True must raise.
    os.environ.pop("OPENAI_API_KEY", None)
    emb = Embedder(model=EmbeddingModel.OPENAI_SMALL, api_key=None, cache=None)
    with pytest.raises(EmbeddingError):
        emb.embed_one("anything_unique_for_this_test", real=True)


def test_embedder_openai_offline_falls_back_when_not_real():
    os.environ.pop("OPENAI_API_KEY", None)
    emb = Embedder(model=EmbeddingModel.OPENAI_SMALL, api_key=None)
    vec = emb.embed_one("anything")  # real=False -> deterministic fallback
    assert len(vec) == EmbeddingModel.OPENAI_SMALL.dim


def test_cache_is_content_addressed(tmp_path):
    cache = EmbeddingCache(root=tmp_path)
    cache.put("model-x", "Hello World", [0.1, 0.2, 0.3])
    # normalization means case/whitespace insensitive
    got = cache.get("model-x", "  hello   world ", 3)
    assert got == [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]
    # different model -> miss
    assert cache.get("model-y", "Hello World", 3) is None


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

def test_reranker_lexical_orders_by_relevance():
    rer = Reranker(top_k=2)
    chunks = [
        RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                       document_name="a", collection_id=uuid.uuid4(),
                       position=i, content=c, score=0.5)
        for i, c in enumerate([
            "unrelated text about the weather",
            "python engineer resume senior backend",
            "resume review notes",
        ])
    ]
    out = rer.rerank("python engineer resume", chunks)
    assert out[0].content.startswith("python engineer")


def test_reranker_respects_top_k_cap():
    rer = Reranker(top_k=1)
    chunks = [
        RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                       document_name="a", collection_id=uuid.uuid4(),
                       position=i, content="match match match", score=0.5)
        for i in range(5)
    ]
    assert len(rer.rerank("match", chunks)) == 1


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

def test_streaming_emits_tokens_then_done():
    cfg = GenerationConfig(mode=GeneratorMode.TEMPLATE)
    sg = StreamingGenerator(cfg)
    chunks = [
        RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                       document_name="d", collection_id=uuid.uuid4(),
                       position=0, content="streamed context body", score=0.9)
    ]
    events = asyncio.run(_collect(sg.stream("q", chunks, run_id="run-1")))
    types = [e.type for e in events]
    assert types[0] == "token"
    assert types[-1] == "done"
    assert events[-1].run_id == "run-1"
    assert events[-1].citations  # non-empty


def test_streaming_sse_format():
    cfg = GenerationConfig(mode=GeneratorMode.TEMPLATE)
    sg = StreamingGenerator(cfg)
    chunks = [
        RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                       document_name="d", collection_id=uuid.uuid4(),
                       position=0, content="hi there", score=0.9)
    ]
    events = asyncio.run(_collect(sg.stream("q", chunks, run_id="r")))
    frame = events[0].to_sse()
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert '"type": "token"' in frame


def test_streaming_real_errors_without_client():
    os.environ.pop("OPENAI_API_KEY", None)
    cfg = GenerationConfig(api_key=None)
    sg = StreamingGenerator(cfg)
    chunks = [
        RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                       document_name="d", collection_id=uuid.uuid4(),
                       position=0, content="x", score=0.9)
    ]
    events = asyncio.run(_collect(sg.stream("q", chunks, real=True)))
    assert events[-1].type == "error"


async def _collect(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out
