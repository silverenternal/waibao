"""Generator — vendor-in LlamaIndex ResponseSynthesizer.

We implement the two most useful response modes from LlamaIndex:

* ``compact``  - concatenate chunks until context window is filled, then
                 generate a single response (best default).
* ``refine``   - iteratively refine the answer by feeding each chunk
                 sequentially (best for multi-hop QA).
* ``simple``   - extract a span from the top chunk (no LLM call).

When no LLM is available we provide a *template* summariser that simply
concatenates the top chunks with a citation header.  This is what runs in
tests and offline environments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import RetrievedChunk


class GeneratorMode(str, Enum):
    COMPACT = "compact"
    REFINE = "refine"
    SIMPLE = "simple"
    TEMPLATE = "template"


@dataclass
class GenerationConfig:
    mode: GeneratorMode = GeneratorMode.COMPACT
    model: str = "gpt-4o-mini"
    max_tokens: int = 512
    temperature: float = 0.2
    max_context_chunks: int = 8
    system_prompt: str | None = None
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("OPENAI_API_KEY")


_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions using the provided "
    "context.  If the answer is not in the context, say so.  Cite sources "
    "inline using the [doc_id:chunk_id] tokens that appear in the context."
)


class Generator:
    """Generate an answer from a query + retrieved chunks."""

    def __init__(self, config: GenerationConfig | None = None) -> None:
        self.config = config or GenerationConfig()
        self._client: Any = None

    # ------------------------------------------------------------------
    def generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "I could not find any relevant information."
        cfg = self.config
        ctx_chunks = chunks[: cfg.max_context_chunks]

        if cfg.mode == GeneratorMode.SIMPLE:
            return ctx_chunks[0].content
        if cfg.mode == GeneratorMode.TEMPLATE:
            return self._template_answer(query, ctx_chunks)
        if cfg.mode == GeneratorMode.REFINE:
            return self._refine(query, ctx_chunks)
        return self._compact(query, ctx_chunks)

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
    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        return "\n\n".join(
            f"[{c.citation_token()}] {c.content}" for c in chunks
        )

    def _build_user_prompt(self, query: str, chunks: list[RetrievedChunk]) -> str:
        ctx = self._build_context(chunks)
        return (
            f"Context:\n{ctx}\n\n"
            f"Question: {query}\n\n"
            "Answer concisely, citing sources with the [doc_id:chunk_id] tokens."
        )

    # ------------------------------------------------------------------
    def _compact(self, query: str, chunks: list[RetrievedChunk]) -> str:
        client = self._client_or_none()
        if client is None:
            return self._template_answer(query, chunks)
        try:
            resp = client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                messages=[
                    {"role": "system", "content": self.config.system_prompt or _SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_prompt(query, chunks)},
                ],
            )
            return resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            return self._template_answer(query, chunks)

    def _refine(self, query: str, chunks: list[RetrievedChunk]) -> str:
        client = self._client_or_none()
        if client is None:
            return self._template_answer(query, chunks)
        answer = ""
        for c in chunks:
            try:
                ctx = self._build_context([c])
                user_prompt = (
                    f"Context:\n{ctx}\n\nQuestion: {query}\n\n"
                    f"Existing answer (refine it, do NOT repeat):\n{answer or '(empty)'}\n\n"
                    "Refined answer:"
                )
                resp = client.chat.completions.create(
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    messages=[
                        {"role": "system", "content": self.config.system_prompt or _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                answer = resp.choices[0].message.content or answer
            except Exception:  # noqa: BLE001
                return self._template_answer(query, chunks)
        return answer or self._template_answer(query, chunks)

    # ------------------------------------------------------------------
    @staticmethod
    def _template_answer(query: str, chunks: list[RetrievedChunk]) -> str:
        head = f"Here is what I found for: {query!r}\n\n"
        body = "\n\n".join(
            f"- [{c.citation_token()}] {c.content[:300]}" for c in chunks
        )
        return head + body
