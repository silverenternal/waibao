"""SSE token-by-token streaming for RAG answers — T5020.

Wraps an OpenAI-compatible Chat Completions ``stream=True`` call behind an
async generator that yields ``ServerSentEvent``-formatted chunks.  When no
LLM client is available (offline / tests) we fall back to a deterministic
token-emitter that splits the template answer into word tokens so the
streaming contract and downstream UI can still be exercised.

Event schema (one SSE ``data:`` frame per token):

    data: {"type":"token","content":"Hello"}

    data: {"type":"token","content":" world"}

    data: {"type":"done","run_id":"...","citations":["[abc:def]"]}

    data: {"type":"error","message":"..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Iterable

from .generator import GenerationConfig, Generator
from .models import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    type: str
    content: str = ""
    run_id: str = ""
    citations: list[str] | None = None
    message: str | None = None

    def to_sse(self) -> str:
        payload: dict[str, Any] = {"type": self.type, "content": self.content}
        if self.run_id:
            payload["run_id"] = self.run_id
        if self.citations is not None:
            payload["citations"] = self.citations
        if self.message is not None:
            payload["message"] = self.message
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class StreamingGenerator:
    """Stream a RAG answer token-by-token over SSE."""

    def __init__(self, config: GenerationConfig | None = None) -> None:
        self.config = config or GenerationConfig()
        self._generator = Generator(self.config)
        self._client: Any = None

    # ------------------------------------------------------------------
    def _client_or_none(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.config.api_key:
            return None
        try:
            from openai import OpenAI  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        kwargs: dict[str, Any] = {"api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    # ------------------------------------------------------------------
    async def stream(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        run_id: str | None = None,
        real: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """Yield ``StreamEvent``s ending with a ``done`` (or ``error``) event."""
        run_id = run_id or str(uuid.uuid4())
        citations = [c.citation_token() for c in chunks[: self.config.max_context_chunks]]

        client = self._client_or_none()
        if client is None:
            if real:
                yield StreamEvent(
                    type="error",
                    run_id=run_id,
                    message="no LLM client configured for streaming",
                )
                return
            # Offline fallback: emit the template answer word-by-word.
            text = self._generator.generate(query, chunks)
            async for tok in self._emit_words(text, run_id):
                yield tok
            yield StreamEvent(type="done", run_id=run_id, citations=citations)
            return

        # Live streaming path.
        try:
            user_prompt = self._build_user_prompt(query, chunks)
            stream = client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
                messages=[
                    {
                        "role": "system",
                        "content": self.config.system_prompt
                        or "Answer using the provided context; cite [doc_id:chunk_id].",
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                token = getattr(delta, "content", None) if delta else None
                if token:
                    yield StreamEvent(type="token", content=token, run_id=run_id)
            yield StreamEvent(type="done", run_id=run_id, citations=citations)
        except Exception as exc:  # noqa: BLE001
            logger.warning("streaming LLM failed: %s", exc)
            if real:
                yield StreamEvent(type="error", run_id=run_id, message=str(exc))
                return
            # graceful degradation: fall back to template stream
            text = self._generator.generate(query, chunks)
            async for tok in self._emit_words(text, run_id):
                yield tok
            yield StreamEvent(type="done", run_id=run_id, citations=citations)

    # ------------------------------------------------------------------
    def _build_user_prompt(self, query: str, chunks: list[RetrievedChunk]) -> str:
        ctx = "\n\n".join(f"[{c.citation_token()}] {c.content}" for c in chunks)
        return f"Context:\n{ctx}\n\nQuestion: {query}\n\nAnswer concisely with citations."

    async def _emit_words(self, text: str, run_id: str) -> AsyncIterator[StreamEvent]:
        for word in text.split():
            yield StreamEvent(type="token", content=word + " ", run_id=run_id)
            await asyncio.sleep(0)  # cooperative yield


def sse_response(events: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
    """Adapt an event stream into raw SSE ``data: ...`` frames for a
    Starlette/FastAPI ``StreamingResponse``."""
    async def gen() -> AsyncIterator[str]:
        async for ev in events:
            yield ev.to_sse()
    return gen()
