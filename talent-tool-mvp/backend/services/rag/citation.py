"""Citation injection — automatic [doc_id:chunk_id] tokens.

Given a generated answer and the supporting chunks, we:

1. Detect existing inline tokens in the answer and keep them
2. For chunks that were used but not cited, append a "Sources" section
3. Produce a structured list of `Citation` objects for the UI
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .models import RetrievedChunk


_TOKEN_RE = re.compile(r"\[([0-9a-f]{8}):([0-9a-f]{8})\]")


@dataclass
class Citation:
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    document_name: str
    position: int
    snippet: str
    score: float = 0.0
    rerank_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def token(self) -> str:
        return f"[{str(self.document_id)[:8]}:{str(self.chunk_id)[:8]}]"

    def to_dict(self) -> dict:
        return {
            "document_id": str(self.document_id),
            "chunk_id": str(self.chunk_id),
            "document_name": self.document_name,
            "position": self.position,
            "snippet": self.snippet,
            "score": self.score,
            "rerank_score": self.rerank_score,
            "metadata": self.metadata,
            "token": self.token(),
        }


class CitationFormatter:
    """Add / extract citations to a generated answer."""

    def __init__(self, *, snippet_chars: int = 240) -> None:
        self.snippet_chars = snippet_chars

    # ------------------------------------------------------------------
    def extract_inline(self, answer: str) -> set[str]:
        """Return the set of `doc:chunk` tokens that appear in the answer."""
        return set(_TOKEN_RE.findall(answer))

    # ------------------------------------------------------------------
    def build_citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        citations: list[Citation] = []
        for c in chunks:
            citations.append(Citation(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                document_name=c.document_name,
                position=c.position,
                snippet=c.content[: self.snippet_chars],
                score=c.score,
                rerank_score=c.rerank_score,
                metadata=c.metadata,
            ))
        return citations

    # ------------------------------------------------------------------
    def format(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> tuple[str, list[Citation]]:
        """Append a `Sources:` block with any chunk that wasn't cited inline.

        Returns the augmented answer and the structured citation list.
        """
        citations = self.build_citations(chunks)
        if not citations:
            return answer, []

        # Map of (short_doc, short_chunk) -> Citation
        cited = self.extract_inline(answer)
        unused = [
            c for c in citations
            if (str(c.document_id)[:8], str(c.chunk_id)[:8]) not in cited
        ]

        if not unused:
            return answer, citations

        sources_block = "\n\nSources:\n" + "\n".join(
            f"  - {c.token()} {c.document_name} (chunk {c.position})"
            for c in unused
        )
        return answer.rstrip() + sources_block, citations

    # ------------------------------------------------------------------
    def highlight_tokens(self, text: str) -> list[dict[str, Any]]:
        """Return a list of segments for the UI highlighter.

        Each segment is either:
          * {"type": "text", "text": "..."}
          * {"type": "citation", "text": "[doc:chunk]", "document_id": ..., "chunk_id": ...}
        """
        out: list[dict[str, Any]] = []
        last_end = 0
        for m in _TOKEN_RE.finditer(text):
            if m.start() > last_end:
                out.append({"type": "text", "text": text[last_end : m.start()]})
            doc_short, chunk_short = m.group(1), m.group(2)
            out.append({
                "type": "citation",
                "text": m.group(0),
                "document_id": doc_short,
                "chunk_id": chunk_short,
            })
            last_end = m.end()
        if last_end < len(text):
            out.append({"type": "text", "text": text[last_end:]})
        return out
