"""Sentence-aware chunker — vendor-in LlamaIndex SentenceSplitter.

The default chunk size is 512 tokens with 50 tokens of overlap, as required by
T2701.  We use LlamaIndex's `SentenceSplitter` when available, and fall back
to a simple sentence + window implementation for tests / environments without
the optional tokenizers.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from .document_parser import ParsedDocument


@dataclass
class Chunk:
    chunk_id: uuid.UUID = field(default_factory=uuid.uuid4)
    document_id: uuid.UUID = field(default_factory=uuid.uuid4)
    position: int = 0
    content: str = ""
    token_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "position": self.position,
            "content": self.content,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


# ----------------------------------------------------------------------
# Sentence helpers
# ----------------------------------------------------------------------

_SENTENCE_BREAK = re.compile(r"(?<=[.!?。！？\n])\s+")


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_BREAK.split(text)
    return [p.strip() for p in parts if p.strip()]


def _approx_token_count(text: str) -> int:
    """Token counting fallback (≈ 1 token / 4 chars for English, / 1.5 for CJK)."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return max(1, cjk + len(text) - cjk) // 4 if cjk == 0 else cjk + (len(text) - cjk) // 4


# ----------------------------------------------------------------------
# LlamaIndex bridge
# ----------------------------------------------------------------------

def _try_sentence_splitter(chunk_size: int, chunk_overlap: int):
    try:
        from llama_index.core.node_parser import SentenceSplitter  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        return SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

class Chunker:
    """Split parsed documents into chunks.

    Args:
        chunk_size: target token count per chunk.
        chunk_overlap: token overlap between consecutive chunks.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be in [0, chunk_size)")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = _try_sentence_splitter(chunk_size, chunk_overlap)

    # ------------------------------------------------------------------
    def split(self, documents: Iterable[ParsedDocument]) -> list[Chunk]:
        out: list[Chunk] = []
        for doc in documents:
            out.extend(self._split_one(doc))
        return out

    def split_text(self, text: str, *, document_id: uuid.UUID | None = None,
                   metadata: dict | None = None) -> list[Chunk]:
        doc = ParsedDocument(text=text, document_id=document_id or uuid.uuid4(),
                             metadata=metadata or {})
        return self._split_one(doc)

    # ------------------------------------------------------------------
    def _split_one(self, doc: ParsedDocument) -> list[Chunk]:
        text = doc.text
        if not text or not text.strip():
            return []

        if self._splitter is not None:
            try:
                nodes = self._splitter.split_text(text)
                chunks: list[Chunk] = []
                position = 0
                for n in nodes:
                    if not n or not n.strip():
                        continue
                    chunks.append(Chunk(
                        document_id=doc.document_id,
                        position=position,
                        content=n.strip(),
                        token_count=_approx_token_count(n),
                        metadata={
                            **doc.metadata,
                            "parser": doc.parser_used,
                            "language": doc.language,
                        },
                    ))
                    position += 1
                return chunks
            except Exception:  # noqa: BLE001
                pass  # fall through to local impl

        # ----- Fallback: sentence + sliding window -----
        sentences = _split_sentences(text)
        chunks: list[Chunk] = []
        buf: list[str] = []
        buf_tokens = 0
        position = 0

        def flush() -> None:
            nonlocal buf, buf_tokens, position
            if not buf:
                return
            content = " ".join(buf).strip()
            if content:
                chunks.append(Chunk(
                    document_id=doc.document_id,
                    position=position,
                    content=content,
                    token_count=buf_tokens,
                    metadata={
                        **doc.metadata,
                        "parser": doc.parser_used or "fallback",
                        "language": doc.language,
                    },
                ))
                position += 1
            buf = []
            buf_tokens = 0

        for sent in sentences:
            st = _approx_token_count(sent)
            if st + buf_tokens > self.chunk_size and buf:
                flush()
                # carry overlap sentences
                if self.chunk_overlap > 0 and chunks:
                    last = chunks[-1].content
                    overlap_sents = _split_sentences(last)
                    carry: list[str] = []
                    carry_tok = 0
                    for s in reversed(overlap_sents):
                        t = _approx_token_count(s)
                        if carry_tok + t > self.chunk_overlap:
                            break
                        carry.insert(0, s)
                        carry_tok += t
                    buf = carry
                    buf_tokens = carry_tok
            buf.append(sent)
            buf_tokens += st

        flush()
        return chunks
