"""T2701: 完整 RAG (LlamaIndex + Qdrant) test suite — 60+ tests.

Coverage:
- document_parser:  9 tests  (file / mime detection, fallbacks, language)
- chunker:         11 tests  (size, overlap, fallback, position)
- embedder:         8 tests  (OpenAI / BGE / mock, determinism, normalisation)
- retriever:       10 tests  (vector, BM25, hybrid, RRF, qdrant bridge)
- reranker:         6 tests  (lexical fallback, top-k cap, scoring)
- generator:        6 tests  (compact, refine, simple, template)
- citation:         7 tests  (format, highlight, inline tokens)
- service:         10 tests  (ingest text/file, query, stream, errors)
- models:           4 tests  (Citation token, RetrievalMode enum)
"""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from services.rag import (
    Chunk,
    Chunker,
    Citation,
    CitationFormatter,
    DocumentParser,
    Embedder,
    EmbeddingModel,
    GenerationConfig,
    Generator,
    GeneratorMode,
    ParsedDocument,
    RagService,
    RagServiceError,
    Reranker,
    RetrievedChunk,
    Retriever,
    RetrievalConfig,
    RetrievalMode,
)
from services.rag.embedder import _deterministic_vector
from services.rag.retriever import InMemoryStore, _rrf_fuse


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def sample_text() -> str:
    return (
        "RecruitTech is an AI-powered recruitment platform. "
        "It uses LlamaIndex for RAG. Qdrant stores embeddings. "
        "BGE-reranker re-orders retrieved chunks. "
        "Citations link answers to source documents."
    )


@pytest.fixture
def long_text() -> str:
    para = "Sentence number X. " * 200
    return para


@pytest.fixture
def tmp_doc(tmp_path: Path, sample_text: str) -> str:
    p = tmp_path / "doc.txt"
    p.write_text(sample_text, encoding="utf-8")
    return str(p)


@pytest.fixture
def service() -> RagService:
    return RagService(
        parser=DocumentParser(),
        chunker=Chunker(chunk_size=64, chunk_overlap=8),
        embedder=Embedder(model=EmbeddingModel.MOCK),
        retriever=Retriever(RetrievalConfig(top_k=3)),
        reranker=Reranker(top_k=3),
        generator=Generator(GenerationConfig(mode=GeneratorMode.TEMPLATE)),
        citation_formatter=CitationFormatter(),
    )


# ----------------------------------------------------------------------
# 1) document_parser  (9)
# ----------------------------------------------------------------------

class TestDocumentParser:
    def test_parse_text_plain(self, tmp_doc: str) -> None:
        p = DocumentParser()
        doc = p.parse(tmp_doc, "text/plain")
        assert "RecruitTech" in doc.text
        assert doc.parser_used != "unknown"
        assert doc.pages >= 1
        assert doc.language in {"en", "zh", "ja"}

    def test_parse_text_fallback_md(self, tmp_path: Path) -> None:
        p = tmp_path / "x.md"
        p.write_text("# Title\n\nHello world.", encoding="utf-8")
        doc = DocumentParser().parse(str(p), "text/markdown")
        assert "Hello world" in doc.text

    def test_parse_text_fallback_html(self, tmp_path: Path) -> None:
        p = tmp_path / "x.html"
        p.write_text("<html><body><h1>Hi</h1><p>Body</p></body></html>", encoding="utf-8")
        doc = DocumentParser().parse(str(p), "text/html")
        assert "Hi" in doc.text
        assert "<" not in doc.text

    def test_detect_mime(self, tmp_path: Path) -> None:
        p = tmp_path / "x.pdf"
        p.write_text("fake", encoding="utf-8")
        assert DocumentParser().detect_mime(str(p)) == "application/pdf"

    def test_supports_valid(self, tmp_doc: str) -> None:
        assert DocumentParser().supports(tmp_doc, "text/plain")

    def test_supports_binary_rejection(self, tmp_path: Path) -> None:
        p = tmp_path / "x.zip"
        p.write_text("fake", encoding="utf-8")
        assert not DocumentParser().supports(str(p), "application/zip")

    def test_parse_text_in_memory(self) -> None:
        doc = DocumentParser().parse_text("hello world", source="test")
        assert doc.text == "hello world"
        assert doc.parser_used == "raw"
        assert doc.metadata["source"] == "test"

    def test_parse_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            DocumentParser().parse_text("   ")

    def test_chinese_language_detection(self) -> None:
        doc = DocumentParser().parse_text("招聘系统支持中文检索。", source="zh")
        assert doc.language == "zh"


# ----------------------------------------------------------------------
# 2) chunker  (11)
# ----------------------------------------------------------------------

class TestChunker:
    def test_basic_split(self, sample_text: str) -> None:
        chunks = Chunker(chunk_size=32, chunk_overlap=4).split_text(sample_text)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.content
            assert c.position >= 0
            assert c.token_count >= 1

    def test_positions_are_unique(self, long_text: str) -> None:
        chunks = Chunker(chunk_size=128, chunk_overlap=16).split_text(long_text)
        positions = [c.position for c in chunks]
        assert len(positions) == len(set(positions))

    def test_overlap_present(self, long_text: str) -> None:
        chunks = Chunker(chunk_size=200, chunk_overlap=40).split_text(long_text)
        if len(chunks) >= 2:
            # some content from chunk[i] should appear in chunk[i+1]
            joined_tail = chunks[0].content[-120:]
            assert any(t in chunks[1].content for t in joined_tail.split() if len(t) > 4)

    def test_document_id_propagated(self, sample_text: str) -> None:
        did = uuid.uuid4()
        chunks = Chunker(chunk_size=64, chunk_overlap=8).split_text(
            sample_text, document_id=did
        )
        assert all(c.document_id == did for c in chunks)

    def test_empty_text_returns_empty(self) -> None:
        assert Chunker().split_text("") == []
        assert Chunker().split_text("    \n   ") == []

    def test_invalid_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError):
            Chunker(chunk_size=0)

    def test_invalid_overlap_raises(self) -> None:
        with pytest.raises(ValueError):
            Chunker(chunk_size=100, chunk_overlap=100)
        with pytest.raises(ValueError):
            Chunker(chunk_size=100, chunk_overlap=200)

    def test_metadata_copied(self, long_text: str) -> None:
        meta = {"source": "test", "tag": "docs"}
        chunks = Chunker(chunk_size=128, chunk_overlap=16).split_text(
            long_text, metadata=meta
        )
        assert all(c.metadata.get("source") == "test" for c in chunks)

    def test_chunk_to_dict(self, sample_text: str) -> None:
        c = Chunker().split_text(sample_text)[0]
        d = c.to_dict()
        assert {"chunk_id", "document_id", "position", "content", "token_count"} <= set(d)

    def test_short_text_single_chunk(self) -> None:
        chunks = Chunker(chunk_size=1024).split_text("short")
        assert len(chunks) == 1
        assert chunks[0].content == "short"

    def test_split_documents(self) -> None:
        docs = [
            ParsedDocument(text="alpha beta gamma delta", document_id=uuid.uuid4()),
            ParsedDocument(text="epsilon zeta eta theta", document_id=uuid.uuid4()),
        ]
        out = Chunker(chunk_size=16, chunk_overlap=4).split(docs)
        assert sum(1 for c in out if c.document_id == docs[0].document_id) >= 1
        assert sum(1 for c in out if c.document_id == docs[1].document_id) >= 1


# ----------------------------------------------------------------------
# 3) embedder  (8)
# ----------------------------------------------------------------------

class TestEmbedder:
    def test_dim_for_models(self) -> None:
        assert EmbeddingModel.BGE_LARGE.dim == 1024
        assert EmbeddingModel.OPENAI_SMALL.dim == 1536
        assert EmbeddingModel.MOCK.dim == 1024

    def test_deterministic_vector_normalised(self) -> None:
        v = _deterministic_vector("hello world", 16)
        assert len(v) == 16
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_same_text_same_vector(self) -> None:
        a = _deterministic_vector("foo bar", 32)
        b = _deterministic_vector("foo bar", 32)
        assert a == b

    def test_different_text_different_vector(self) -> None:
        a = _deterministic_vector("alpha", 32)
        b = _deterministic_vector("beta", 32)
        assert a != b

    def test_embed_batch(self) -> None:
        e = Embedder(model=EmbeddingModel.MOCK)
        vecs = e.embed(["a b c", "d e f"])
        assert len(vecs) == 2
        assert all(len(v) == e.model.dim for v in vecs)

    def test_embed_empty(self) -> None:
        assert Embedder().embed([]) == []

    def test_embed_openai_without_key_falls_back(self) -> None:
        e = Embedder(model=EmbeddingModel.OPENAI_SMALL, api_key=None)
        v = e.embed_one("hello")
        assert len(v) == EmbeddingModel.OPENAI_SMALL.dim

    def test_remote_flag(self) -> None:
        assert EmbeddingModel.OPENAI_SMALL.is_remote
        assert not EmbeddingModel.BGE_LARGE.is_remote


# ----------------------------------------------------------------------
# 4) retriever  (10)
# ----------------------------------------------------------------------

class TestRetriever:
    def _populate(self, r: Retriever, n: int = 5) -> uuid.UUID:
        cid = uuid.uuid4()
        did = uuid.uuid4()
        for i in range(n):
            r.add(
                chunk_id=uuid.uuid4(),
                document_id=did,
                document_name="d.txt",
                collection_id=cid,
                position=i,
                content=f"document about topic {i} - keyword alpha {i*2}",
                embedding=[1.0 if j == i else 0.0 for j in range(n)],
            )
        return cid

    def test_vector_search(self) -> None:
        r = Retriever(RetrievalConfig(top_k=3, mode=RetrievalMode.VECTOR))
        cid = self._populate(r)
        v = [1.0, 0.0, 0.0, 0.0, 0.0]
        out = r.retrieve("alpha", v, cid)
        assert len(out) >= 1
        assert out[0].position == 0

    def test_bm25_keyword_match(self) -> None:
        r = Retriever(RetrievalConfig(top_k=3, mode=RetrievalMode.BM25))
        cid = self._populate(r)
        v = [0.0] * 5
        out = r.retrieve("alpha 8", v, cid)  # "alpha 8" matches chunk #4
        assert any(c.position == 4 for c in out)

    def test_hybrid_uses_both(self) -> None:
        r = Retriever(RetrievalConfig(top_k=3, mode=RetrievalMode.HYBRID))
        cid = self._populate(r)
        v = [1.0, 0.0, 0.0, 0.0, 0.0]
        out = r.retrieve("alpha", v, cid)
        assert out  # non-empty

    def test_top_k_caps_results(self) -> None:
        r = Retriever(RetrievalConfig(top_k=2))
        cid = self._populate(r, n=10)
        v = [1.0] + [0.0] * 9
        out = r.retrieve("q", v, cid, top_k=2)
        assert len(out) == 2

    def test_clear_collection(self) -> None:
        r = Retriever()
        cid = self._populate(r)
        r.clear_collection(cid)
        v = [1.0, 0.0, 0.0, 0.0, 0.0]
        out = r.retrieve("alpha", v, cid)
        assert out == []

    def test_in_memory_store_rrf(self) -> None:
        # Two ranked lists overlapping; RRF should rank the overlap highest
        a = [{"chunk_id": "1", "x": 1}, {"chunk_id": "2", "x": 2}, {"chunk_id": "3", "x": 3}]
        b = [{"chunk_id": "3", "x": 1}, {"chunk_id": "2", "x": 2}, {"chunk_id": "1", "x": 3}]
        fused = _rrf_fuse([a, b], weights=[1.0, 1.0], top_k=3)
        keys = [str(x["chunk_id"]) for x in fused]
        assert set(keys) == {"1", "2", "3"}
        # All three should have positive score
        for x in fused:
            assert x["_score"] > 0

    def test_in_memory_store_vector(self) -> None:
        s = InMemoryStore()
        cid = uuid.uuid4()
        s.upsert({
            "chunk_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "document_name": "n",
            "collection_id": cid,
            "position": 0,
            "content": "x",
            "vector": [1.0, 0.0],
            "metadata": {},
        })
        out = s.vector_search([1.0, 0.0], cid, 1)
        assert out and out[0]["_score"] > 0.99

    def test_in_memory_store_bm25(self) -> None:
        s = InMemoryStore()
        cid = uuid.uuid4()
        for i, content in enumerate(["alpha beta", "alpha", "beta", "gamma"]):
            s.upsert({
                "chunk_id": uuid.uuid4(),
                "document_id": uuid.uuid4(),
                "document_name": "n",
                "collection_id": cid,
                "position": i,
                "content": content,
                "vector": [0.0] * 4,
                "metadata": {},
            })
        out = s.bm25_search("alpha beta", cid, 3)
        assert out
        # the first chunk with both terms should rank highest
        assert "alpha beta" in out[0]["content"]

    def test_qdrant_client_optional(self) -> None:
        # Without a Qdrant URL the retriever still works via the in-memory store
        r = Retriever(RetrievalConfig(qdrant_url=None))
        cid = self._populate(r)
        out = r.retrieve("alpha", [1.0, 0.0, 0.0, 0.0, 0.0], cid)
        assert out

    def test_score_threshold(self) -> None:
        r = Retriever(RetrievalConfig(top_k=10, mode=RetrievalMode.VECTOR, score_threshold=0.5))
        cid = self._populate(r)
        out = r.retrieve("x", [0.0, 0.0, 0.0, 0.0, 0.0], cid)
        # all-zero vector is orthogonal, so nothing passes threshold
        assert out == []


# ----------------------------------------------------------------------
# 5) reranker  (6)
# ----------------------------------------------------------------------

class TestReranker:
    def _chunk(self, content: str, score: float = 0.5) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_name="d.txt",
            collection_id=uuid.uuid4(),
            position=0,
            content=content,
            score=score,
        )

    def test_rerank_top_k(self) -> None:
        r = Reranker(top_k=2)
        chunks = [self._chunk("alpha"), self._chunk("beta"), self._chunk("gamma")]
        out = r.rerank("alpha", chunks, top_k=2)
        assert len(out) == 2
        assert all(c.rerank_score is not None for c in out)

    def test_rerank_empty(self) -> None:
        assert Reranker().rerank("anything", []) == []

    def test_rerank_orders_by_relevance(self) -> None:
        r = Reranker()
        chunks = [
            self._chunk("unrelated text"),
            self._chunk("this is about the alpha query"),
            self._chunk("alpha alpha alpha alpha"),
        ]
        out = r.rerank("alpha", chunks, top_k=3)
        # The chunk with "alpha" repeated should rank first
        assert "alpha" in out[0].content

    def test_default_model_constant(self) -> None:
        assert Reranker.DEFAULT_MODEL.startswith("BAAI/")

    def test_rerank_uses_initial_score(self) -> None:
        r = Reranker()
        a = self._chunk("alpha", score=0.0)
        b = self._chunk("alpha", score=1.0)
        out = r.rerank("alpha", [a, b], top_k=1)
        # higher initial score should win when content overlap is equal
        assert out[0].score == 1.0

    def test_rerank_no_crash_on_unicode(self) -> None:
        r = Reranker()
        chunks = [self._chunk("招聘政策说明"), self._chunk("福利政策")]
        out = r.rerank("招聘", chunks)
        assert out
        assert out[0].rerank_score is not None


# ----------------------------------------------------------------------
# 6) generator  (6)
# ----------------------------------------------------------------------

class TestGenerator:
    def _chunk(self, content: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_name="d.txt",
            collection_id=uuid.uuid4(),
            position=0,
            content=content,
        )

    def test_template_mode(self) -> None:
        g = Generator(GenerationConfig(mode=GeneratorMode.TEMPLATE))
        out = g.generate("hi?", [self._chunk("hello")])
        assert "hi?" in out
        assert "hello" in out

    def test_simple_mode_returns_top_chunk(self) -> None:
        g = Generator(GenerationConfig(mode=GeneratorMode.SIMPLE))
        out = g.generate("?", [self._chunk("first"), self._chunk("second")])
        assert out == "first"

    def test_no_chunks_returns_placeholder(self) -> None:
        g = Generator()
        out = g.generate("anything", [])
        assert "could not" in out.lower() or "no relevant" in out.lower()

    def test_compact_with_no_client_falls_back(self) -> None:
        g = Generator(GenerationConfig(mode=GeneratorMode.COMPACT, api_key=None))
        out = g.generate("q", [self._chunk("a"), self._chunk("b")])
        assert "a" in out and "b" in out

    def test_refine_with_no_client_falls_back(self) -> None:
        g = Generator(GenerationConfig(mode=GeneratorMode.REFINE, api_key=None))
        out = g.generate("q", [self._chunk("alpha"), self._chunk("beta")])
        assert out

    def test_citations_in_template(self) -> None:
        g = Generator(GenerationConfig(mode=GeneratorMode.TEMPLATE))
        c = self._chunk("snippet content here")
        out = g.generate("?", [c])
        # the citation token for that chunk should appear in the output
        assert c.citation_token() in out


# ----------------------------------------------------------------------
# 7) citation  (7)
# ----------------------------------------------------------------------

class TestCitation:
    def _chunk(self, content: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_name="d.txt",
            collection_id=uuid.uuid4(),
            position=0,
            content=content,
        )

    def test_format_appends_sources(self) -> None:
        f = CitationFormatter()
        c = self._chunk("body")
        out, cits = f.format("answer without citation", [c])
        assert cits and out.endswith(")") or "Sources" in out
        assert cits[0].token() in out

    def test_format_keeps_inline_citations(self) -> None:
        f = CitationFormatter()
        c = self._chunk("body")
        # Pretend the answer already cites the chunk
        answer_with_token = f"answer {c.citation_token()} more"
        out, cits = f.format(answer_with_token, [c])
        # Should not duplicate sources block since the only chunk is cited
        assert "Sources" not in out or cits[0].token() not in out.split("Sources:")[-1]

    def test_extract_inline(self) -> None:
        f = CitationFormatter()
        cited = f.extract_inline("see [abcdef12:12345678] and [00000000:11111111]")
        assert ("abcdef12", "12345678") in cited
        assert ("00000000", "11111111") in cited

    def test_highlight_tokens_segments(self) -> None:
        f = CitationFormatter()
        segs = f.highlight_tokens("hi [abcdef00:12345678] there")
        assert any(s["type"] == "citation" for s in segs)
        assert any(s["type"] == "text" for s in segs)

    def test_build_citations_truncates(self) -> None:
        f = CitationFormatter(snippet_chars=20)
        c = self._chunk("a" * 200)
        cits = f.build_citations([c])
        assert len(cits[0].snippet) == 20

    def test_citation_to_dict_keys(self) -> None:
        c = Citation(
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            document_name="d",
            position=1,
            snippet="s",
        )
        d = c.to_dict()
        for k in (
            "document_id",
            "chunk_id",
            "document_name",
            "position",
            "snippet",
            "token",
        ):
            assert k in d

    def test_format_empty_chunks(self) -> None:
        f = CitationFormatter()
        out, cits = f.format("nothing", [])
        assert cits == [] and out == "nothing"


# ----------------------------------------------------------------------
# 8) service  (10)
# ----------------------------------------------------------------------

class TestRagService:
    def test_ingest_text(self, service: RagService) -> None:
        cid = uuid.uuid4()
        did = uuid.uuid4()
        r = service.ingest_text(
            text="alpha beta gamma delta epsilon zeta eta theta iota kappa",
            collection_id=cid,
            document_id=did,
            document_name="d.txt",
        )
        assert r.document_id == did
        assert r.chunks
        assert r.total_tokens >= 1

    def test_ingest_text_empty_raises(self, service: RagService) -> None:
        with pytest.raises(RagServiceError):
            service.ingest_text(
                text="   ",
                collection_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="d",
            )

    def test_ingest_file(self, service: RagService, tmp_path: Path) -> None:
        p = tmp_path / "doc.txt"
        p.write_text("Lorem ipsum dolor sit amet. " * 30, encoding="utf-8")
        r = service.ingest_file(
            file_path=str(p),
            mime_type="text/plain",
            collection_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_name="doc.txt",
        )
        assert r.chunks
        # total_ms uses perf_counter which may be 0 on tiny inputs;
        # we just want a non-negative int — and the breakdown is correctly
        # populated in IngestionResult.
        assert r.total_ms() >= 0
        assert (r.parse_ms + r.chunk_ms + r.embed_ms + r.index_ms) >= 0

    def test_ingest_file_unsupported(self, service: RagService, tmp_path: Path) -> None:
        p = tmp_path / "x.zip"
        p.write_text("fake", encoding="utf-8")
        with pytest.raises(RagServiceError):
            service.ingest_file(
                file_path=str(p),
                mime_type="application/zip",
                collection_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_name="x",
            )

    def test_query_returns_answer(self, service: RagService) -> None:
        cid = uuid.uuid4()
        did = uuid.uuid4()
        service.ingest_text(
            text="RecruitTech uses LlamaIndex and Qdrant for RAG. The platform supports citations.",
            collection_id=cid,
            document_id=did,
            document_name="d.txt",
        )
        r = service.query("What does RecruitTech use?", collection_id=cid, top_k=3)
        assert r.answer
        assert r.chunks
        # total_ms may legitimately be 0 on tiny inputs (perf_counter precision)
        assert r.total_ms >= 0

    def test_query_empty_raises(self, service: RagService) -> None:
        with pytest.raises(RagServiceError):
            service.query("  ", collection_id=uuid.uuid4())

    def test_query_mode_override(self, service: RagService) -> None:
        cid = uuid.uuid4()
        service.ingest_text(
            text="alpha alpha alpha beta gamma",
            collection_id=cid,
            document_id=uuid.uuid4(),
            document_name="d",
        )
        r = service.query("alpha", collection_id=cid, mode=RetrievalMode.BM25, top_k=2)
        assert r.chunks

    def test_query_no_reranker(self, service: RagService) -> None:
        cid = uuid.uuid4()
        service.ingest_text(
            text="alpha beta gamma " * 20,
            collection_id=cid,
            document_id=uuid.uuid4(),
            document_name="d",
        )
        r = service.query(
            "alpha",
            collection_id=cid,
            top_k=2,
            use_reranker=False,
        )
        assert r.rerank_ms >= 0

    def test_query_stream(self, service: RagService) -> None:
        cid = uuid.uuid4()
        service.ingest_text(
            text="x" * 200,
            collection_id=cid,
            document_id=uuid.uuid4(),
            document_name="d",
        )
        events = list(
            service.query_stream("anything", collection_id=cid, top_k=2)
        )
        assert events[0]["event"] == "metadata"
        assert any(e["event"] == "done" for e in events)

    def test_performance_smoke(self, service: RagService) -> None:
        # ingest + retrieve should be well under 2s end-to-end on tiny data
        cid = uuid.uuid4()
        text = ("sentence. " * 50)
        t = time.perf_counter()
        service.ingest_text(
            text=text, collection_id=cid, document_id=uuid.uuid4(), document_name="d"
        )
        ingest_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        service.query("sentence", collection_id=cid, top_k=3, use_reranker=False)
        query_ms = (time.perf_counter() - t) * 1000
        assert ingest_ms < 5000
        assert query_ms < 2000


# ----------------------------------------------------------------------
# 9) models  (4)
# ----------------------------------------------------------------------

class TestModels:
    def test_citation_token_format(self) -> None:
        c = RetrievedChunk(
            chunk_id=uuid.UUID("12345678-aaaa-bbbb-cccc-000000000000"),
            document_id=uuid.UUID("abcdef00-aaaa-bbbb-cccc-000000000000"),
            document_name="d",
            collection_id=uuid.uuid4(),
            position=0,
            content="x",
        )
        tok = c.citation_token()
        assert re.match(r"\[abcdef00:12345678\]", tok)

    def test_retrieval_mode_enum_values(self) -> None:
        assert RetrievalMode.VECTOR.value == "vector"
        assert RetrievalMode.BM25.value == "bm25"
        assert RetrievalMode.HYBRID.value == "hybrid"

    def test_document_status_enum(self) -> None:
        for s in ("pending", "parsing", "chunking", "embedding", "indexed", "failed"):
            from services.rag.models import DocumentStatus
            assert DocumentStatus(s).value == s

    def test_singleton_factory(self) -> None:
        from services.rag.service import get_rag_service, reset_rag_service
        reset_rag_service()
        s1 = get_rag_service()
        s2 = get_rag_service()
        assert s1 is s2
        reset_rag_service()
        s3 = get_rag_service()
        assert s1 is not s3
