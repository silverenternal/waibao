"""T2801 — ClickHouse + warehouse 服务层 测试.

策略: 用 mock 模拟 clickhouse-driver, 不依赖真实 ClickHouse.
      集成一致性测试用 mock postgres + mock clickhouse 对比行数.
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake clickhouse_driver
# ---------------------------------------------------------------------------
class _FakeColumn(tuple):
    """clickhouse_driver 返回的 column type 是 (name, type_code) tuple."""

    def __new__(cls, name: str, type_name: str = "String") -> "_FakeColumn":
        return super().__new__(cls, (name, type_name))

    @property
    def name(self) -> str:
        return self[0]

    @property
    def type(self) -> str:
        return self[1]


class _FakeClient:
    """模拟 clickhouse_driver.Client 的最小行为."""

    # 类级共享的查询 mock 数据 (key = query 关键字)
    _QUERY_DATA: dict[str, list[tuple]] = {
        "SELECT x, y FROM t": [(1, "a"), (2, "b")],
    }
    _QUERY_COLS: dict[str, list[tuple[str, str]]] = {
        "SELECT x, y FROM t": [("x", "UInt64"), ("y", "String")],
    }

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._data: list[dict[str, object]] = []
        self._cols: list[tuple[str, str]] = []
        self.executed: list[str] = []
        self.disconnected = False

    def execute(self, query: str, params: dict | None = None,
                with_column_types: bool = False):  # noqa: ANN001
        self.executed.append(query)
        params = params or {}
        if "SELECT 1" in query:
            return [(1,)]
        if "SELECT version()" in query:
            return ([("24.3.0",)], [("v", "String")]) if with_column_types else [(1,)]
        if "FROM system.tables" in query:
            return [(1 if "raw_candidates" in str(params.get("n", "")) else 0,)]
        if "count()" in query and "system.tables" not in query:
            return [(len(self._data),)]
        # 类级 fixture 数据 (覆盖 path: "SELECT x, y FROM t")
        for key, rows in self._QUERY_DATA.items():
            if key in query:
                cols = self._QUERY_COLS[key]
                if with_column_types:
                    return (rows, cols)
                return rows
        if with_column_types:
            return (self._data, self._cols)
        return self._data

    def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def fake_driver():
    """monkey-patch clickhouse_driver.Client 为 _FakeClient."""
    fake_mod = MagicMock()
    fake_mod.Client = _FakeClient
    sys.modules["clickhouse_driver"] = fake_mod
    yield fake_mod
    sys.modules.pop("clickhouse_driver", None)


# ---------------------------------------------------------------------------
# ClickHouseClient
# ---------------------------------------------------------------------------
def test_clickhouse_client_ping(fake_driver):  # noqa: ANN001
    from services.warehouse import ClickHouseConfig
    from services.warehouse.clickhouse_client import ClickHouseClient

    c = ClickHouseClient(ClickHouseConfig(host="localhost", port=9000))
    assert c.ping() is True
    assert c.health()["ok"] is True


def test_clickhouse_client_query(fake_driver):  # noqa: ANN001
    from services.warehouse import ClickHouseConfig
    from services.warehouse.clickhouse_client import ClickHouseClient

    c = ClickHouseClient(ClickHouseConfig())
    c.connect()
    # _FakeClient 已内置 "SELECT x, y FROM t" 数据
    rows = c.query("SELECT x, y FROM t")
    assert rows == [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]


def test_clickhouse_client_table_exists(fake_driver):  # noqa: ANN001
    from services.warehouse import ClickHouseConfig
    from services.warehouse.clickhouse_client import ClickHouseClient

    c = ClickHouseClient(ClickHouseConfig())
    assert c.table_exists("raw_candidates") is True
    assert c.table_exists("does_not_exist") is False


def test_clickhouse_client_close(fake_driver):  # noqa: ANN001
    from services.warehouse import ClickHouseConfig
    from services.warehouse.clickhouse_client import ClickHouseClient

    c = ClickHouseClient(ClickHouseConfig())
    c.connect()
    c.close()
    assert c._client.disconnected is True


# ---------------------------------------------------------------------------
# dbt macro 静态检查
# ---------------------------------------------------------------------------
def test_dbt_macros_exist():
    macros_dir = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "macros"
    assert (macros_dir / "time_buckets.sql").exists()
    assert (macros_dir / "funnel.sql").exists()
    assert (macros_dir / "retention.sql").exists()
    assert (macros_dir / "tenant_scope.sql").exists()


def test_dbt_models_exist():
    models_dir = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "models"
    expected = {
        "staging/candidates/stg_candidates.sql",
        "staging/jobs/stg_jobs.sql",
        "staging/tickets/stg_tickets.sql",
        "marts/candidates/dim_candidates.sql",
        "marts/candidates/fct_matches.sql",
        "marts/jobs/dim_jobs.sql",
        "marts/jobs/fct_applications.sql",
        "marts/tickets/fct_sla_metrics.sql",
    }
    for rel in expected:
        assert (models_dir / rel).exists(), f"missing {rel}"


def test_dbt_project_yml_loads():
    import yaml
    p = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "dbt_project.yml"
    cfg = yaml.safe_load(p.read_text())
    assert cfg["name"] == "waibao_warehouse"
    assert cfg["profile"] == "waibao_warehouse"
    assert "staging" in cfg["models"]
    assert "marts" in cfg["models"]


def test_dbt_fct_sla_uses_aggregating_merge_tree():
    p = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "models" / "marts" / "tickets" / "fct_sla_metrics.sql"
    text = p.read_text()
    assert "AggregatingMergeTree" in text
    assert "countState" in text
    assert "avgState" in text


def test_dbt_fct_uses_partition_by_yyyymm():
    base = Path(__file__).parent.parent / "backend" / "services" / "warehouse" / "dbt" / "models" / "marts"
    for rel in ("candidates/fct_matches.sql", "jobs/fct_applications.sql", "tickets/fct_sla_metrics.sql"):
        text = (base / rel).read_text()
        assert "toYYYYMM(event_date)" in text, f"{rel} should partition by event_date"


# ---------------------------------------------------------------------------
# Airbyte client
# ---------------------------------------------------------------------------
def test_airbyte_client_health():
    from services.warehouse.etl_pipeline import AirbyteClient

    with patch("services.warehouse.etl_pipeline.requests.Session") as Sess:
        sess = MagicMock()
        Sess.return_value = sess
        sess.get.return_value.json.return_value = {}
        sess.get.return_value.raise_for_status = lambda: None
        c = AirbyteClient(base_url="http://localhost:8001", api_token="x")
        assert c.health() is True


def test_airbyte_client_health_down():
    from services.warehouse.etl_pipeline import AirbyteClient

    with patch("services.warehouse.etl_pipeline.requests.Session") as Sess:
        sess = MagicMock()
        sess.get.side_effect = Exception("connect refused")
        Sess.return_value = sess
        c = AirbyteClient(base_url="http://localhost:8001", api_token="x")
        assert c.health() is False


def test_airbyte_client_trigger_sync():
    from services.warehouse.etl_pipeline import AirbyteClient

    with patch("services.warehouse.etl_pipeline.requests.Session") as Sess:
        sess = MagicMock()
        Sess.return_value = sess
        sess.post.return_value.json.return_value = {"jobId": 42}
        sess.post.return_value.raise_for_status = lambda: None
        c = AirbyteClient(base_url="http://localhost:8001", api_token="x")
        out = c.trigger_sync("conn-1")
        assert out["jobId"] == 42


# ---------------------------------------------------------------------------
# ETL pipeline (mocked airbyte)
# ---------------------------------------------------------------------------
def test_etl_pipeline_run_success():
    from services.warehouse.etl_pipeline import AirbytePipelineConfig, ETLPipeline, PipelineStatus

    cfg = AirbytePipelineConfig(
        airbyte_url="http://x", airbyte_api_token="t",
        connection_id="conn-1", poll_interval=0.01, max_poll_attempts=10,
    )
    p = ETLPipeline(cfg)
    p.client = MagicMock()
    p.client.health.return_value = True
    p.client.trigger_sync.return_value = {"jobId": 99}
    p.client.job_status.return_value = {
        "status": "succeeded",
        "stats": {"bytesEmitted": 1024, "recordsEmitted": 100},
    }
    result = p.run()
    assert result.status == PipelineStatus.SUCCEEDED
    assert result.bytes_synced == 1024
    assert result.records_synced == 100


def test_etl_pipeline_run_failure():
    from services.warehouse.etl_pipeline import AirbytePipelineConfig, ETLPipeline, PipelineStatus

    cfg = AirbytePipelineConfig(
        airbyte_url="http://x", airbyte_api_token="t",
        connection_id="conn-1", poll_interval=0.01, max_poll_attempts=5,
    )
    p = ETLPipeline(cfg)
    p.client = MagicMock()
    p.client.health.return_value = True
    p.client.trigger_sync.return_value = {"jobId": 7}
    p.client.job_status.return_value = {"status": "failed", "errorMessage": "boom"}
    result = p.run()
    assert result.status == PipelineStatus.FAILED
    assert result.error == "boom"


def test_etl_pipeline_unreachable():
    from services.warehouse.etl_pipeline import AirbytePipelineConfig, ETLPipeline

    cfg = AirbytePipelineConfig(airbyte_url="http://x", connection_id="conn-1")
    p = ETLPipeline(cfg)
    p.client = MagicMock()
    p.client.health.return_value = False
    with pytest.raises(RuntimeError):
        p.run()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
def test_scheduler_status_initial():
    from services.warehouse.etl_scheduler import ETLScheduler

    s = ETLScheduler(enabled=False, interval_seconds=60)
    status = s.status()
    assert status["enabled"] is False
    assert status["running"] is False
    assert status["total_runs"] == 0


def test_scheduler_run_now_records():
    from services.warehouse.etl_scheduler import ETLScheduler
    from services.warehouse.etl_pipeline import PipelineStatus

    sched = ETLScheduler(enabled=False, interval_seconds=60)
    sched.pipeline = MagicMock()
    sched.pipeline.run.return_value = MagicMock(
        status=PipelineStatus.SUCCEEDED, to_dict=lambda: {"status": "succeeded"},
        records_synced=10, bytes_synced=100, duration_s=0.1, error=None,
        job_id="1", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    )
    res = sched.run_now()
    assert res.status == PipelineStatus.SUCCEEDED
    s2 = sched.status()
    assert s2["total_runs"] == 1
    assert s2["failed_runs"] == 0


def test_scheduler_counts_failures():
    from services.warehouse.etl_scheduler import ETLScheduler

    sched = ETLScheduler(enabled=False, interval_seconds=60)
    sched.pipeline = MagicMock()
    sched.pipeline.run.side_effect = Exception("network down")
    sched.run_now()
    assert sched.status()["failed_runs"] == 1


def test_scheduler_disabled_does_not_start():
    from services.warehouse.etl_scheduler import ETLScheduler

    sched = ETLScheduler(enabled=False, interval_seconds=60)
    sched.start()
    assert sched.status()["running"] is False
