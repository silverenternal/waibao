"""T903 — feedback_loop 单元测试 (权重调整 + audit log + daily_scheduler)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from services import feedback_loop as fl


# ---------------------------------------------------------------------------
# Stub Supabase client
# ---------------------------------------------------------------------------


class _TableStub:
    def __init__(self, store: dict | None = None) -> None:
        self.store = store or {}
        self.last_query = None
        self.last_insert = None
        self.last_upsert = None

    def select(self, *_args, **_kwargs):
        self.last_query = ("select", _args, _kwargs)
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def insert(self, data):
        self.last_insert = data
        return self

    def upsert(self, data, **_):
        self.last_upsert = data
        return self

    def update(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _SupabaseStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.match_rows: list[dict] = []
        self.history_rows: list[dict] = []
        self.settings_rows: list[dict] = []
        self.audit_rows: list[dict] = []

    def table(self, name: str):
        self.calls.append(("table", name))
        return _TableStub(store={})


# ---------------------------------------------------------------------------
# aggregate_outcomes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_outcomes_basic_counts(monkeypatch):
    fake_sb = _SupabaseStub()

    def fake_table(name):
        if name == "two_way_matches":
            return _StaticTable(
                [
                    {"status": "placed", "harmonic_score": 0.85},
                    {"status": "placed", "harmonic_score": 0.7},
                    {"status": "rejected_by_employer", "harmonic_score": 0.5},
                    {"status": "pending", "harmonic_score": 0.3},
                    {"status": "withdrawn", "harmonic_score": 0.2},
                ]
            )
        if name == "matching_quality_history":
            return _StaticTable([])
        return _StaticTable([])

    fake_sb.table = fake_table  # type: ignore[assignment]
    metrics = await fl.aggregate_outcomes(since_days=7, supabase=fake_sb)  # type: ignore[arg-type]

    assert metrics.tp == 2
    assert metrics.fp == 1
    assert metrics.fn == 1
    assert metrics.tn == 1
    assert metrics.total == 5
    assert metrics.precision == pytest.approx(2 / 3, rel=1e-3)
    assert metrics.recall == pytest.approx(2 / 3, rel=1e-3)
    assert metrics.f1 > 0
    assert "0.8-1.0" in metrics.bucket_distribution


@pytest.mark.asyncio
async def test_aggregate_outcomes_handles_empty(monkeypatch):
    fake_sb = _SupabaseStub()

    def fake_table(name):
        return _StaticTable([])

    fake_sb.table = fake_table  # type: ignore[assignment]
    metrics = await fl.aggregate_outcomes(since_days=7, supabase=fake_sb)  # type: ignore[arg-type]
    assert metrics.total == 0
    assert metrics.precision == 0
    assert metrics.bucket_distribution == {}


class _StaticTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def insert(self, data):
        return self

    def upsert(self, data, **_):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


# ---------------------------------------------------------------------------
# compute_weight_adjustment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_weight_adjustment_low_precision():
    metrics = fl.Metrics(
        precision=0.4,
        recall=0.7,
        f1=0.5,
        total=50,
    )
    adj = await fl.compute_weight_adjustment(fl.DEFAULT_WEIGHTS, metrics)
    assert adj.delta["skill"] > 0
    assert "skill" in adj.reason or "precision" in adj.reason
    # 归一化:权重和应为 1
    total = sum(adj.new_weights.values())
    assert pytest.approx(total, abs=1e-3) == 1.0


@pytest.mark.asyncio
async def test_compute_weight_adjustment_low_recall():
    metrics = fl.Metrics(precision=0.8, recall=0.3, f1=0.45, total=80)
    adj = await fl.compute_weight_adjustment(fl.DEFAULT_WEIGHTS, metrics)
    assert adj.delta["semantic"] > 0


@pytest.mark.asyncio
async def test_compute_weight_adjustment_high_bucket_low_conversion():
    metrics = fl.Metrics(
        precision=0.7,
        recall=0.7,
        f1=0.7,
        total=60,
        bucket_distribution={"0.8-1.0": {"count": 10, "placed_rate": 0.1}},
    )
    adj = await fl.compute_weight_adjustment(fl.DEFAULT_WEIGHTS, metrics)
    assert adj.delta.get("experience", 0) > 0


@pytest.mark.asyncio
async def test_compute_weight_adjustment_low_sample_no_change():
    metrics = fl.Metrics(precision=0.4, recall=0.3, f1=0.35, total=10)
    adj = await fl.compute_weight_adjustment(fl.DEFAULT_WEIGHTS, metrics)
    assert adj.confidence < 0.5
    # 样本量小,不调整
    assert all(v == 0 for v in adj.delta.values())


@pytest.mark.asyncio
async def test_compute_weight_adjustment_stable_no_change():
    metrics = fl.Metrics(precision=0.8, recall=0.75, f1=0.78, total=120)
    adj = await fl.compute_weight_adjustment(fl.DEFAULT_WEIGHTS, metrics)
    assert all(v == 0 for v in adj.delta.values())
    assert "稳定" in adj.reason


# ---------------------------------------------------------------------------
# apply_adjustment + audit log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_adjustment_writes_settings_and_audit(monkeypatch):
    fake_sb = _SupabaseStub()
    calls: list[tuple[str, str]] = []

    class _TrackerTable:
        def __init__(self, name):
            self.name = name

        def upsert(self, data, **_):
            calls.append(("upsert", self.name))
            return self

        def insert(self, data):
            calls.append(("insert", self.name))
            return self

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def maybe_single(self):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    def fake_table(name):
        calls.append(("table", name))
        return _TrackerTable(name)

    fake_sb.table = fake_table  # type: ignore[assignment]

    result = await fl.apply_adjustment(
        {"skill": 0.5, "semantic": 0.3, "experience": 0.2, "culture": 0.1},
        actor="admin",
        reason="manual",
        supabase=fake_sb,  # type: ignore[arg-type]
        require_approval=False,
    )
    assert result["status"] == "active"
    # weights 归一化
    assert pytest.approx(sum(result["weights"].values()), abs=1e-3) == 1.0
    # settings + audit 都被写
    assert ("upsert", "settings") in calls
    assert ("insert", "settings_audit") in calls


@pytest.mark.asyncio
async def test_apply_adjustment_normalization_clamps_extreme_values():
    fake_sb = _SupabaseStub()
    result = await fl.apply_adjustment(
        {"skill": 999, "semantic": 0, "experience": 0, "culture": 0},
        actor="x",
        reason="edge",
        supabase=fake_sb,  # type: ignore[arg-type]
        require_approval=False,
    )
    # 即使给极端值,各 weight 也被 clamp + 归一化
    for v in result["weights"].values():
        assert 0 <= v <= 1
    assert pytest.approx(sum(result["weights"].values()), abs=1e-3) == 1.0


# ---------------------------------------------------------------------------
# daily_scheduler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_scheduler_returns_full_payload(monkeypatch):
    fake_sb = _SupabaseStub()

    def fake_table(name):
        if name == "two_way_matches":
            return _StaticTable(
                [
                    {"status": "placed", "harmonic_score": 0.85},
                    {"status": "placed", "harmonic_score": 0.82},
                    {"status": "rejected_by_employer", "harmonic_score": 0.5},
                ]
            )
        return _StaticTable([])

    fake_sb.table = fake_table  # type: ignore[assignment]
    result = await fl.daily_scheduler(supabase=fake_sb, since_days=7)  # type: ignore[arg-type]
    assert "metrics" in result
    assert "adjustment" in result
    assert "result" in result
    assert result["result"]["status"] in ("pending", "active")


@pytest.mark.asyncio
async def test_daily_scheduler_force_flag(monkeypatch):
    fake_sb = _SupabaseStub()
    fake_sb.table = lambda name: _StaticTable([])  # type: ignore[assignment]
    result = await fl.daily_scheduler(supabase=fake_sb, force=True)  # type: ignore[arg-type]
    assert result["force"] is True


# ---------------------------------------------------------------------------
# get_current_weights fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_weights_returns_defaults_when_empty(monkeypatch):
    fake_sb = _SupabaseStub()
    fake_sb.table = lambda name: _StaticTable([])  # type: ignore[assignment]
    weights = await fl.get_current_weights(supabase=fake_sb)  # type: ignore[arg-type]
    assert weights == fl.DEFAULT_WEIGHTS


@pytest.mark.asyncio
async def test_get_current_weights_parses_json_string(monkeypatch):
    fake_sb = _SupabaseStub()
    fake_sb.table = lambda name: _StaticTable(  # type: ignore[assignment]
        # .maybe_single() expects execute().data to be a single dict (or None)
        {"value": json.dumps({"skill": 0.6, "semantic": 0.2, "experience": 0.1, "culture": 0.1})}
    )
    weights = await fl.get_current_weights(supabase=fake_sb)  # type: ignore[arg-type]
    # get_current_weights merges with defaults, stored skill=0.6 wins
    assert weights["skill"] == pytest.approx(0.6)
    assert "culture" in weights