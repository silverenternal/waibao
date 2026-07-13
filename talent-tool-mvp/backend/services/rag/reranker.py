"""BGE-reranker cross-encoder with a deterministic lexical fallback.

Production deployments vendor in `sentence_transformers.CrossEncoder` (model
`BAAI/bge-reranker-large`).  When that is unavailable we fall back to a small
lexical overlap score that still gives a meaningful ranking signal.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from typing import Iterable

from .models import RetrievedChunk


_TOKEN_RE = re.compile(r"[A-Za-z0-9一-鿿ぁ-ヿ]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _bow(text: str) -> Counter:
    return Counter(_tokenize(text))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class Reranker:
    """Cross-encoder reranker.

    Args:
        model_name: name of the BGE-reranker model on HuggingFace Hub.
        top_k: cap on the number of chunks to return.
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-large"

    def __init__(self, model_name: str = DEFAULT_MODEL, top_k: int = 5) -> None:
        self.model_name = model_name
        self.top_k = top_k
        self._model: object | None = None
        self._tokenizer: object | None = None

    # ------------------------------------------------------------------
    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception:  # noqa: BLE001
            return False
        try:
            self._model = CrossEncoder(self.model_name)
            return True
        except Exception:  # noqa: BLE001
            self._model = None
            return False

    # ------------------------------------------------------------------
    def rerank(
        self,
        query: str,
        chunks: Iterable[RetrievedChunk],
        *,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        chunks = list(chunks)
        if not chunks:
            return []
        k = top_k or self.top_k

        if self._load_model() and self._model is not None:
            try:
                pairs = [(query, c.content) for c in chunks]
                scores = self._model.predict(pairs)  # type: ignore[attr-defined]
                for c, s in zip(chunks, scores):
                    c.rerank_score = float(s)
                chunks.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)
                return chunks[:k]
            except Exception:  # noqa: BLE001
                pass  # fall through

        return self._lexical_rerank(query, chunks, k)

    # ------------------------------------------------------------------
    def _lexical_rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        k: int,
    ) -> list[RetrievedChunk]:
        q = _bow(query)
        scored: list[tuple[float, RetrievedChunk]] = []
        for c in chunks:
            d = _bow(c.content)
            base = _cosine(q, d)
            # boost for query term coverage
            q_terms = set(q)
            d_terms = set(d)
            coverage = (len(q_terms & d_terms) / max(1, len(q_terms))) if q_terms else 0.0
            # boost for higher original retrieval score
            s = 0.6 * base + 0.3 * coverage + 0.1 * max(0.0, c.score)
            c.rerank_score = s
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:k]]
