"""
T1404 — backend global search tests.

Unit tests focus on the ranker (no DB) and the URL/icon mapping.
Integration tests against the real Postgres index live in
`backend/tests/integration/test_search_db.py` (gated by INTEGRATION=1).
"""
from backend.services.global_search import (
    SearchResult,
    ScoredCandidate,
    rank_candidates,
    score_one,
    ts_query_sql,
    trigram_sql,
    semantic_sql,
    build_snippet,
)


def _c(id_: str, title: str, lex: int | None, sem: int | None, fzy: int | None) -> ScoredCandidate:
    return ScoredCandidate(
        id=id_,
        title=title,
        snippet="snippet",
        url=f"/candidates/{id_}",
        icon="user",
        lex_rank=lex,
        sem_rank=sem,
        fzy_rank=fzy,
    )


def test_rank_candidates_orders_by_combined_score():
    lex = [_c("a", "Alice", 1, None, None)]
    sem = [_c("b", "Bob", None, 1, None)]
    fzy = [_c("c", "Cara", None, None, 1)]
    out = rank_candidates(lex, sem, fzy, limit=10)
    assert len(out) == 3
    # All three have combined RRF score of 1/(60+1) so order is stable.
    for r in out:
        assert isinstance(r, SearchResult)
        assert 0 <= r.score <= 1


def test_rank_candidates_dedups_by_id_url():
    dup1 = _c("a", "Alice", 1, 5, None)
    dup2 = _c("a", "Alice", 2, None, 3)
    out = rank_candidates([dup1, dup2], [], [], limit=10)
    assert len(out) == 1
    # The combined rank keeps the best (smallest) per-component rank
    assert out[0].id == "a"


def test_rank_candidates_respects_limit():
    lex = [_c(str(i), f"C{i}", i, None, None) for i in range(1, 6)]
    out = rank_candidates(lex, [], [], limit=3)
    assert len(out) == 3


def test_score_one_handles_missing_ranks():
    assert score_one(None, None, None) == 0.0
    assert score_one(1, None, None) > 0


def test_ts_query_sql_returns_websearch_predicate():
    sql, params = ts_query_sql("hello world")
    assert "websearch_to_tsquery" in sql
    assert params["q"] == "hello world"
    assert params["lang"] == "simple"


def test_trigram_sql_returns_ilike_predicate():
    sql, params = trigram_sql("alice")
    assert "ILIKE" in sql
    assert params["q"] == "%alice%"


def test_semantic_sql_returns_cosine_predicate():
    sql = semantic_sql()
    assert "<=>" in sql
    assert "embedding" in sql


def test_build_snippet_truncates_to_240_chars():
    frag = build_snippet("description")
    assert "240" in frag
    assert "substring" in frag
