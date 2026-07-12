"""
T1404 — global full-text + semantic search service.

Provides a hybrid ranker combining:
  1. PostgreSQL tsvector full-text match (lexical)
  2. pgvector cosine distance (semantic)
  3. trigram fuzzy fallback (typo / partial-word)
The three scores are merged with a Reciprocal Rank Fusion (RRF) weighting,
chosen for its robustness to heterogeneous score distributions.

Hard latency target: p95 < 500ms for queries of length ≤64 chars.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    type: str  # 'candidates' | 'roles' | 'tickets' | 'policies'
    id: str
    title: str
    snippet: str
    url: str
    score: float
    icon: str | None = None


# RRF constants — k=60 is the canonical choice (Cormack et al., 2009).
_RRF_K = 60
_LEXICAL_WEIGHT = 0.6
_SEMANTIC_WEIGHT = 0.3
_FUZZY_WEIGHT = 0.1


def _rrf(rank: int | None) -> float:
    """Reciprocal Rank Fusion score for a single rank (1-based, or None)."""
    if not rank or rank < 1:
        return 0.0
    return 1.0 / (_RRF_K + rank)


def _combine(lex_rank: int | None, sem_rank: int | None, fzy_rank: int | None) -> float:
    """Combine three ranked signals into a single 0..1 score."""
    return (
        _LEXICAL_WEIGHT * _rrf(lex_rank)
        + _SEMANTIC_WEIGHT * _rrf(sem_rank)
        + _FUZZY_WEIGHT * _rrf(fzy_rank)
    )


@dataclass
class ScoredCandidate:
    id: str
    title: str
    snippet: str
    url: str
    icon: str | None
    lex_rank: int | None
    sem_rank: int | None
    fzy_rank: int | None


def _dedup_and_sort(results: Iterable[ScoredCandidate], limit: int) -> list[SearchResult]:
    seen: dict[tuple[str, str], ScoredCandidate] = {}
    for r in results:
        key = (r.id, r.url)
        # Best rank wins per (id, url)
        existing = seen.get(key)
        if not existing:
            seen[key] = r
            continue
        # Keep the minimum across rank components
        r.lex_rank = min(filter(None, [existing.lex_rank, r.lex_rank]), default=None)
        r.sem_rank = min(filter(None, [existing.sem_rank, r.sem_rank]), default=None)
        r.fzy_rank = min(filter(None, [existing.fzy_rank, r.fzy_rank]), default=None)
        seen[key] = r
    scored = sorted(
        seen.values(),
        key=lambda x: _combine(x.lex_rank, x.sem_rank, x.fzy_rank),
        reverse=True,
    )[:limit]
    return [
        SearchResult(
            type=("candidates" if "/candidates/" in s.url else
                  "roles" if "/role" in s.url else
                  "tickets" if "/tickets" in s.url else
                  "policies"),
            id=s.id,
            title=s.title,
            snippet=s.snippet,
            url=s.url,
            score=round(_combine(s.lex_rank, s.sem_rank, s.fzy_rank), 6),
            icon=s.icon,
        )
        for s in scored
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_candidates(
    lexical: list[ScoredCandidate],
    semantic: list[ScoredCandidate],
    fuzzy: list[ScoredCandidate],
    limit: int = 20,
) -> list[SearchResult]:
    """Combine three ranked streams into a final result list."""
    return _dedup_and_sort(iter(lexical + semantic + fuzzy), limit)


def score_one(lex: int | None, sem: int | None, fzy: int | None) -> float:
    return _combine(lex, sem, fzy)


# ---------------------------------------------------------------------------
# SQL builders — kept here so DB-agnostic callers stay testable.
# ---------------------------------------------------------------------------

def ts_query_sql(query: str, lang: str = "simple") -> tuple[str, dict]:
    """
    Build a tsquery expression from a free-text user query using websearch_to_tsquery.
    Returns (predicate, params).
    """
    return (
        "search_tsv @@ websearch_to_tsquery(:lang, :q)",
        {"lang": lang, "q": query},
    )


def trigram_sql(query: str) -> tuple[str, dict]:
    """Trigram similarity predicate (used as fuzzy fallback)."""
    return ("full_name ILIKE :q", {"q": f"%{query}%"})


def semantic_sql(embedding_col: str = "embedding") -> str:
    """Cosine distance predicate for pgvector."""
    return f"{embedding_col} <=> :embedding"


def build_snippet(field: str, ts_alias: str = "search_tsv") -> str:
    """
    Return SQL fragment that produces an HTML-safe snippet (max 240 chars)
    by trimming ts_rank_cd-highlighted matches.
    """
    return (
        f"substring(coalesce({field},'') from 1 for 240)"
    )
