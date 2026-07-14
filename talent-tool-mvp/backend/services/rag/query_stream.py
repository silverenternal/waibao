"""v10.0 T5027 — Real SSE streaming that interleaves RAG chunks + LLM tokens.

A single ``StreamingRagQuery`` async generator produces one SSE event stream
that tells the client exactly what is happening, in order:

1. ``status`` events (retrieving / generating) so the UI can show progress.
2. ``chunk`` events — one per retrieved source *as soon as* retrieval returns
   them, so the user sees the evidence while the LLM is still thinking.
3. ``token`` events — the LLM answer, token by token.
4. A final ``done`` event carrying the run id + citation list.

This wraps the existing :class:`~services.rag.streaming.StreamingGenerator`
(LLM token path) and the :class:`~services.rag.retriever.Retriever`
(chunk path) and merges them into one SSE-formatted byte stream suitable for
``StreamingResponse(content=..., media_type="text/event-stream")``.

When no real LLM/embedder is configured (offline / tests) both paths fall
back to deterministic local emitters, so the streaming contract can be
exercised end-to-end with zero external dependencies.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Iterable, List, Optional

from .models import RetrievedChunk

logger = logging.getLogger("recruittech.rag.query_stream")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
@dataclass
class RagStreamEvent:
    """A single SSE-serialisable event in the unified stream."""

    type: str  # status | chunk | token | done | error
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = {"type": self.type, **self.data}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Streaming RAG query
# ---------------------------------------------------------------------------
class StreamingRagQuery:
    """Merge retrieval chunks + LLM tokens into one SSE stream."""

    def __init__(
        self,
        *,
        retriever: Any = None,
        streamer: Any = None,
        generate: Optional[Callable[[str, List[RetrievedChunk]], AsyncIterator[str]]] = None,
        retrieve: Optional[Callable[[str], List[RetrievedChunk]]] = None,
    ) -> None:
        # Caller may wire either real components or simple callables (tests).
        self._retriever = retriever
        self._streamer = streamer
        self._generate = generate
        self._retrieve = retrieve

    # ------------------------------------------------------------------
    def _do_retrieve(self, query: str, tenant_id: Optional[str] = None,
                     top_k: int = 5) -> List[RetrievedChunk]:
        if self._retrieve is not None:
            return list(self._retrieve(query) or [])
        if self._retriever is not None:
            cfg = _build_retriever_config(top_k)
            try:
                result = self._retriever.retrieve(query, cfg, tenant_id=tenant_id)
                # retriever may return (chunks, mode) or just chunks
                if isinstance(result, tuple):
                    return list(result[0] or [])
                return list(result or [])
            except Exception:  # noqa: BLE001
                logger.exception("query_stream.retrieve_failed")
                return []
        return []

    async def _do_generate(self, query: str, chunks: List[RetrievedChunk],
                           ) -> AsyncIterator[str]:
        if self._generate is not None:
            async for tok in self._generate(query, chunks):
                yield tok
            return
        if self._streamer is not None:
            from .streaming import StreamEvent
            async for ev in self._streamer.stream(query, chunks):
                if isinstance(ev, StreamEvent) and ev.type == "token":
                    yield ev.content
            return
        # Offline deterministic fallback.
        for tok in _offline_tokens(_offline_answer(query, chunks)):
            yield tok

    # ------------------------------------------------------------------
    async def stream(
        self,
        query: str,
        *,
        tenant_id: Optional[str] = None,
        top_k: int = 5,
        run_id: Optional[str] = None,
    ) -> AsyncIterator[RagStreamEvent]:
        """Yield the unified event stream for one RAG query."""
        run_id = run_id or str(uuid.uuid4())
        started = time.time()

        # 1. status: retrieving
        yield RagStreamEvent("status", {"stage": "retrieving", "run_id": run_id})

        # 2. chunks
        chunks = await asyncio.get_event_loop().run_in_executor(
            None, self._do_retrieve, query, tenant_id, top_k,
        )
        citations: List[str] = []
        for chunk in chunks:
            token = _chunk_citation(chunk)
            citations.append(token)
            yield RagStreamEvent("chunk", {
                "run_id": run_id,
                "citation": token,
                "content": _chunk_content(chunk),
                "score": _chunk_score(chunk),
            })

        # 3. status: generating
        yield RagStreamEvent("status", {
            "stage": "generating", "run_id": run_id,
            "chunks": len(chunks),
        })

        # 4. tokens
        token_count = 0
        try:
            async for tok in self._do_generate(query, chunks):
                if not tok:
                    continue
                token_count += 1
                yield RagStreamEvent("token", {
                    "run_id": run_id, "content": tok,
                })
        except Exception as exc:  # noqa: BLE001
            logger.exception("query_stream.generate_failed")
            yield RagStreamEvent("error", {
                "run_id": run_id, "message": f"{type(exc).__name__}: {exc}",
            })
            return

        # 5. done
        yield RagStreamEvent("done", {
            "run_id": run_id,
            "citations": citations,
            "tokens": token_count,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
        })

    # ------------------------------------------------------------------
    async def stream_sse(self, query: str, **kwargs: Any) -> AsyncIterator[str]:
        """Convenience: yield raw SSE-formatted strings."""
        async for ev in self.stream(query, **kwargs):
            yield ev.to_sse()


# ---------------------------------------------------------------------------
# Helpers (extract fields from heterogeneous chunk shapes)
# ---------------------------------------------------------------------------
def _build_retriever_config(top_k: int) -> Any:
    try:
        from .retriever import RetrievalConfig
        return RetrievalConfig(top_k=top_k)
    except Exception:  # noqa: BLE001
        return None


def _chunk_citation(chunk: Any) -> str:
    for attr in ("citation_token", "citation"):
        fn = getattr(chunk, attr, None)
        if callable(fn):
            try:
                return fn() if attr == "citation_token" else fn
            except Exception:  # noqa: BLE001
                pass
    doc = getattr(chunk, "document_id", None) or getattr(chunk, "doc_id", "?")
    cid = getattr(chunk, "chunk_id", None) or getattr(chunk, "id", "?")
    return f"[{doc}:{cid}]"


def _chunk_content(chunk: Any) -> str:
    return str(getattr(chunk, "content", None)
               or getattr(chunk, "text", "")
               or "")


def _chunk_score(chunk: Any) -> float:
    score = getattr(chunk, "score", None)
    if score is None:
        return 0.0
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _offline_answer(query: str, chunks: List[RetrievedChunk]) -> str:
    """Deterministic answer for offline streaming (mirrors generator fallback)."""
    if not chunks:
        return f"No documents found for {query!r}."
    cite = ", ".join(_chunk_citation(c) for c in chunks[:3])
    return f"Based on {cite}: the answer to {query!r} is synthesized from the retrieved context."


def _offline_tokens(text: str) -> Iterable[str]:
    for word in text.split():
        yield word + " "


__all__ = ["RagStreamEvent", "StreamingRagQuery"]
