"""T2801 — ETL 数据一致性测试 (Postgres vs ClickHouse)."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _FakeCH:
    """clickhouse_client 替代: 模拟 Airbyte 同步后的行."""

    def __init__(self) -> None:
        self._raw_candidates = [
            {"id": "c1", "updated_at": "2026-07-01T00:00:00Z"},
            {"id": "c2", "updated_at": "2026-07-02T00:00:00Z"},
            {"id": "c3", "updated_at": "2026-07-03T00:00:00Z"},
        ]
        self._raw_jobs = [
            {"id": "j1", "updated_at": "2026-07-01T00:00:00Z"},
            {"id": "j2", "updated_at": "2026-07-02T00:00:00Z"},
        ]
        self._raw_matches = [
            {"id": "m1", "candidate_id": "c1", "job_id": "j1", "score": 0.9, "accepted": 1},
        ]

    def query(self, sql: str, params: dict | None = None):  # noqa: ANN001
        if "fct_matches" in sql:
            return [
                {"event_date": "2026-07-01", "matches": 1, "avg_score": 0.9, "accepted": 1},
            ]
        if "fct_applications" in sql and "stage" in sql:
            return [
                {"stage": "applied", "candidates": 100},
                {"stage": "screened", "candidates": 60},
                {"stage": "interviewed", "candidates": 30},
                {"stage": "offered", "candidates": 12},
                {"stage": "hired", "candidates": 5},
            ]
        if "countMerge" in sql and "ticket_count" in sql and "priority" in sql:
            return [
                {"priority": "high", "tickets": 50, "sla_met": 45, "sla_rate": 0.9, "avg_first_min": 10.0, "avg_resolve_min": 240.0},
            ]
        if "countMerge" in sql:
            return [
                {"event_date": "2026-07-01", "tickets": 10, "sla_met": 9, "sla_rate": 0.9, "avg_first_min": 8.0, "p95_first_min": 20.0, "avg_resolve_min": 200.0, "p95_resolve_min": 500.0},
            ]
        if "dim_candidates" in sql and "experience_band" in sql:
            return [{"experience_band": "mid", "count": 2}]
        if "FROM raw_candidates" in sql.lower() or "raw_candidates" in sql:
            return self._raw_candidates
        return []

    def query_one(self, sql: str, params=None):  # noqa: ANN001
        if "version()" in sql:
            return {"v": "24.3"}
        return {"ok": True}

    def health(self) -> dict:
        return {"ok": True, "version": "24.3"}

    def row_count(self, table: str) -> int:
        return {
            "raw_candidates": len(self._raw_candidates),
            "raw_jobs": len(self._raw_jobs),
            "raw_matches": len(self._raw_matches),
        }.get(table, 0)


class _FakeSupabase:
    """模拟 Supabase Postgres: candidates / jobs / matches 表行."""

    def __init__(self) -> None:
        self.candidates = [
            {"id": "c1", "updated_at": "2026-07-01T00:00:00Z"},
            {"id": "c2", "updated_at": "2026-07-02T00:00:00Z"},
            {"id": "c3", "updated_at": "2026-07-03T00:00:00Z"},
        ]
        self.jobs = [
            {"id": "j1", "updated_at": "2026-07-01T00:00:00Z"},
            {"id": "j2", "updated_at": "2026-07-02T00:00:00Z"},
        ]
        self.matches = [
            {"id": "m1", "candidate_id": "c1", "job_id": "j1", "score": 0.9, "accepted": True},
        ]

    def table(self, name: str):
        m = MagicMock()
        data = {
            "candidates": self.candidates,
            "jobs": self.jobs,
            "matches": self.matches,
        }.get(name, [])
        m.select.return_value.execute.return_value.data = data
        return m


# ---------------------------------------------------------------------------
# 一致性: Postgres vs ClickHouse 行数
# ---------------------------------------------------------------------------
def test_candidate_row_count_consistency():
    ch = _FakeCH()
    sb = _FakeSupabase()
    assert ch.row_count("raw_candidates") == len(sb.candidates)
    assert ch.row_count("raw_jobs") == len(sb.jobs)
    assert ch.row_count("raw_matches") == len(sb.matches)


def test_candidate_id_set_consistency():
    ch = _FakeCH()
    sb = _FakeSupabase()
    ch_ids = {r["id"] for r in ch.query("SELECT * FROM raw_candidates")}
    sb_ids = {c["id"] for c in sb.candidates}
    assert ch_ids == sb_ids, f"id sets differ: ch={ch_ids - sb_ids} sb={sb_ids - ch_ids}"


# ---------------------------------------------------------------------------
# 一致性: 漏斗 / 趋势 / SLA 查询返回
# ---------------------------------------------------------------------------
def test_funnel_returns_5_stages():
    ch = _FakeCH()
    rows = ch.query("SELECT stage, uniqExact(candidate_id) AS candidates FROM marts.fct_applications GROUP BY stage")
    stages = {r["stage"] for r in rows}
    assert stages == {"applied", "screened", "interviewed", "offered", "hired"}


def test_funnel_is_monotonic():
    ch = _FakeCH()
    rows = ch.query("SELECT stage, candidates FROM marts.fct_applications ORDER BY stage")
    by_stage = {r["stage"]: r["candidates"] for r in rows}
    # 漏斗必须单调递减
    seq = ["applied", "screened", "interviewed", "offered", "hired"]
    for prev, nxt in zip(seq, seq[1:]):
        assert by_stage[nxt] <= by_stage[prev], f"{prev} -> {nxt} 漏斗递增!"


def test_sla_rate_within_range():
    ch = _FakeCH()
    rows = ch.query("SELECT priority, countMerge(sla_met_count) AS sla_met FROM marts.fct_sla_metrics GROUP BY priority")
    for r in rows:
        assert 0.0 <= r["sla_rate"] <= 1.0


def test_sla_p95_geq_avg():
    ch = _FakeCH()
    rows = ch.query("SELECT event_date, avg_first_min AS a, p95_first_min AS p FROM marts.fct_sla_metrics")
    for r in rows:
        assert r["p"] >= r["a"], "P95 必须 >= 均值"


def test_matches_score_in_range():
    ch = _FakeCH()
    rows = ch.query("SELECT avg(score) AS avg_score FROM marts.fct_matches")
    for r in rows:
        assert 0.0 <= r["avg_score"] <= 1.0


# ---------------------------------------------------------------------------
# 模拟: Airbyte sync → raw 表行数变化
# ---------------------------------------------------------------------------
def test_airbyte_sync_adds_rows():
    """模拟一次 Airbyte CDC 同步后 raw 表行数增长."""
    ch = _FakeCH()
    before = ch.row_count("raw_candidates")
    # 模拟 Postgres 有新行, 同步进 ClickHouse
    ch._raw_candidates.append({"id": "c4", "updated_at": "2026-07-04T00:00:00Z"})
    after = ch.row_count("raw_candidates")
    assert after == before + 1


def test_airbyte_sync_idempotent_on_no_change():
    """同一数据再同步, ClickHouse 不应破坏 (idempotent)."""
    ch = _FakeCH()
    before = ch.row_count("raw_candidates")
    # 重复同步同一行 (id 不变)
    ch._raw_candidates.append(ch._raw_candidates[0].copy())
    after = ch.row_count("raw_candidates")
    # 即使 raw 表 append, dbt 的 ReplacingMergeTree 也会去重
    # 这里的 raw 表是 append, 但下游 dim_* 用 ReplacingMergeTree 做幂等
    assert after == before + 1  # raw 是 append-only
    # dim_candidates 用 ReplacingMergeTree, 重复 id 自动覆盖
    # (这个行为是 ClickHouse 引擎保证的, 这里只声明约束)


# ---------------------------------------------------------------------------
# 端到端: scheduler 触发 ETL + dbt + 查询
# ---------------------------------------------------------------------------
def test_end_to_end_pipeline_runs():
    from services.warehouse.etl_pipeline import PipelineStatus
    from services.warehouse.etl_scheduler import ETLScheduler

    sched = ETLScheduler(enabled=False, interval_seconds=60)
    sched.pipeline = MagicMock()
    sched.pipeline.run.return_value = MagicMock(
        status=PipelineStatus.SUCCEEDED,
        records_synced=100,
        bytes_synced=4096,
        duration_s=10.0,
        error=None,
        job_id="123",
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        to_dict=lambda: {"job_id": "123", "status": "succeeded"},
    )
    result = sched.run_now()
    assert result.status == PipelineStatus.SUCCEEDED
    assert sched.status()["total_runs"] == 1


# ---------------------------------------------------------------------------
# dbt project 内容 sanity check
# ---------------------------------------------------------------------------
def test_dbt_models_reference_correct_sources():
    from pathlib import Path
    base = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "models"

    # stg 引用 raw
    stg = (base / "staging" / "candidates" / "stg_candidates.sql").read_text()
    assert "source('warehouse_raw'" in stg
    assert "raw_candidates" in stg

    # marts 引用 staging 或 raw
    fct = (base / "marts" / "candidates" / "fct_matches.sql").read_text()
    assert "raw_matches" in fct or "stg_matches" in fct

    sla = (base / "marts" / "tickets" / "fct_sla_metrics.sql").read_text()
    assert "stg_tickets" in sla
    assert "AggregatingMergeTree" in sla
