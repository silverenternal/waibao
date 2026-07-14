"""v10.0 T5027 — Real RAG streaming tests (chunks + LLM tokens over SSE)."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace


from services.rag.query_stream import RagStreamEvent, StreamingRagQuery


def _chunk(doc_id, chunk_id, content, score=0.9):
    """Duck-typed chunk — StreamingRagQuery accepts any object with the right attrs."""
    return SimpleNamespace(
        document_id=doc_id, chunk_id=chunk_id,
        content=content, score=score,
    )


def _collect(events):
    """Drain an async iterator into a list (sync test helper)."""
    return asyncio.run(_drain(events))


async def _drain(agen):
    out = []
    async for ev in agen:
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Event ordering: status(retrieving) -> chunk(s) -> status(generating) -> token(s) -> done
# ---------------------------------------------------------------------------
def test_stream_event_ordering_and_types():
    chunks = [_chunk("d1", "c1", "Python is great"), _chunk("d2", "c2", "It has asyncio")]
    q = StreamingRagQuery(
        retrieve=lambda query: chunks,
        generate=_fake_generate(["Hello", " world"]),
    )
    events = _collect(q.stream("what is python", top_k=2))
    types = [e.type for e in events]
    assert types[0] == "status"
    assert types[1:3] == ["chunk", "chunk"]
    assert types[3] == "status"
    assert types[-1] == "done"
    assert "token" in types
    # stages reported correctly
    assert events[0].data["stage"] == "retrieving"
    assert events[3].data["stage"] == "generating"
    assert events[3].data["chunks"] == 2


def test_stream_chunks_carry_citation_and_content():
    chunks = [_chunk("docA", "1", "alpha content", score=0.77)]
    q = StreamingRagQuery(retrieve=lambda query: chunks,
                          generate=_fake_generate(["x"]))
    events = _collect(q.stream("q"))
    chunk_events = [e for e in events if e.type == "chunk"]
    assert len(chunk_events) == 1
    assert chunk_events[0].data["citation"] == "[docA:1]"
    assert chunk_events[0].data["content"] == "alpha content"
    assert chunk_events[0].data["score"] == 0.77


def test_stream_tokens_concatenate_to_answer():
    q = StreamingRagQuery(retrieve=lambda query: [],
                          generate=_fake_generate(["Hello", " ", "world", "!"]))
    events = _collect(q.stream("q"))
    tokens = [e.data["content"] for e in events if e.type == "token"]
    assert "".join(tokens) == "Hello world!"


def test_stream_done_has_citations_and_token_count():
    chunks = [_chunk("d", "c", "ctx")]
    q = StreamingRagQuery(retrieve=lambda query: chunks,
                          generate=_fake_generate(["a", "b", "c"]))
    events = _collect(q.stream("q"))
    done = [e for e in events if e.type == "done"][0]
    assert done.data["citations"] == ["[d:c]"]
    assert done.data["tokens"] == 3
    assert done.data["elapsed_ms"] >= 0.0


def test_stream_empty_retrieval_still_streams_answer():
    q = StreamingRagQuery(retrieve=lambda query: [],
                          generate=_fake_generate(["no", "docs"]))
    events = _collect(q.stream("q"))
    assert [e for e in events if e.type == "chunk"] == []
    done = [e for e in events if e.type == "done"][0]
    assert done.data["tokens"] == 2


def test_stream_generate_error_emits_error_event():
    async def gen(query, chunks):
        raise RuntimeError("llm down")
        yield  # pragma: no cover

    q = StreamingRagQuery(retrieve=lambda query: [], generate=gen)
    events = _collect(q.stream("q"))
    assert any(e.type == "error" for e in events)
    assert "RuntimeError" in [e for e in events if e.type == "error"][0].data["message"]


def test_stream_offline_fallback_when_no_components():
    # No retriever / streamer / generate -> offline deterministic path
    q = StreamingRagQuery()
    events = _collect(q.stream("what is asyncio"))
    types = [e.type for e in events]
    assert types[-1] == "done"
    assert "token" in types


def test_sse_format_is_valid_json():
    ev = RagStreamEvent("token", {"content": "hi", "run_id": "r1"})
    line = ev.to_sse()
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    payload = json.loads(line[len("data: "):].strip())
    assert payload["type"] == "token"
    assert payload["content"] == "hi"


def test_stream_sse_yields_strings():
    chunks = [_chunk("d", "c", "ctx")]
    q = StreamingRagQuery(retrieve=lambda query: chunks,
                          generate=_fake_generate(["hi"]))
    sse_chunks = _collect(q.stream_sse("q"))
    assert all(isinstance(s, str) for s in sse_chunks)
    assert all(s.startswith("data: ") for s in sse_chunks)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _fake_generate(tokens):
    async def gen(query, chunks):
        for t in tokens:
            yield t
    return gen
