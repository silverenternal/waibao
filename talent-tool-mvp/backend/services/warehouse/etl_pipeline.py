"""T2801 — Airbyte ETL pipeline (Python orchestrator).

- 在 Airbyte 上配置 source (Postgres CDC) + destination (ClickHouse)
- 用 Airbyte HTTP API 触发同步, 监控状态, 失败告警
- 提供手动 / 定时入口
- dbt 紧接着做维度建模
"""
from __future__ import annotations

import enum
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger("waibao.warehouse.etl")


class PipelineStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AirbytePipelineConfig:
    """从环境变量读. 走 12-factor."""
    airbyte_url: str = field(
        default_factory=lambda: os.getenv("AIRBYTE_URL", "http://localhost:8001")
    )
    airbyte_api_token: str = field(
        default_factory=lambda: os.getenv("AIRBYTE_API_TOKEN", "")
    )
    connection_id: str = field(
        default_factory=lambda: os.getenv("AIRBYTE_CONNECTION_ID", "")
    )
    request_timeout: float = 30.0
    poll_interval: float = 2.0
    max_poll_attempts: int = 1800  # 1h 上限


@dataclass
class PipelineResult:
    job_id: str
    status: PipelineStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_s: Optional[float] = None
    bytes_synced: Optional[int] = None
    records_synced: Optional[int] = None
    error: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_s": self.duration_s,
            "bytes_synced": self.bytes_synced,
            "records_synced": self.records_synced,
            "error": self.error,
        }


class AirbyteClient:
    """Airbyte OSS HTTP API 薄封装."""

    def __init__(self, base_url: str, api_token: str = "", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._session = requests.Session()
        if api_token:
            self._session.headers["Authorization"] = f"Bearer {api_token}"
        self._session.headers["Content-Type"] = "application/json"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path.lstrip('/')}"

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        r = self._session.get(self._url(path), params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        r = self._session.post(self._url(path), json=json or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # -------------------------------------------------------- high level
    def health(self) -> bool:
        try:
            self.get("health")
            return True
        except Exception:  # noqa: BLE001
            return False

    def list_sources(self) -> list[dict[str, Any]]:
        return self.get("sources/list").get("sources", [])

    def list_destinations(self) -> list[dict[str, Any]]:
        return self.get("destinations/list").get("destinations", [])

    def list_connections(self) -> list[dict[str, Any]]:
        return self.get("connections/list").get("connections", [])

    def trigger_sync(self, connection_id: str) -> dict[str, Any]:
        return self.post("connections/sync", {"connectionId": connection_id})

    def job_status(self, job_id: int) -> dict[str, Any]:
        return self.get("jobs/get", id=job_id)

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        return self.post("jobs/cancel", {"id": job_id})


class ETLPipeline:
    """ETL 编排: Airbyte sync + 简单 dbt run 触发.

    不阻塞 dbt 的实际执行细节 — 那由 dbt 调度 (Airflow / Dagster / cron) 负责.
    这里只关心 Airbyte sync + 健康检查 + 监控.
    """

    def __init__(self, config: Optional[AirbytePipelineConfig] = None) -> None:
        self.config = config or AirbytePipelineConfig()
        self.client = AirbyteClient(
            base_url=self.config.airbyte_url,
            api_token=self.config.airbyte_api_token,
            timeout=self.config.request_timeout,
        )
        self._last_result: Optional[PipelineResult] = None

    # -------------------------------------------------------- low level
    def _wait_for_job(self, job_id: int) -> PipelineResult:
        started = datetime.now(timezone.utc)
        for attempt in range(self.config.max_poll_attempts):
            try:
                js = self.client.job_status(job_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("poll job %s failed (attempt %s): %s", job_id, attempt, e)
                time.sleep(self.config.poll_interval)
                continue

            status = js.get("status", "running")
            if status in ("succeeded", "failed", "cancelled"):
                finished = datetime.now(timezone.utc)
                stats = js.get("stats", {}) or {}
                return PipelineResult(
                    job_id=str(job_id),
                    status=PipelineStatus(status),
                    started_at=started,
                    finished_at=finished,
                    duration_s=(finished - started).total_seconds(),
                    bytes_synced=int(stats.get("bytesEmitted", 0)) or None,
                    records_synced=int(stats.get("recordsEmitted", 0)) or None,
                    error=(js.get("errorMessage") or None),
                    raw=js,
                )
            time.sleep(self.config.poll_interval)

        raise TimeoutError(f"Airbyte job {job_id} did not finish in time")

    # -------------------------------------------------------- public
    def run(self) -> PipelineResult:
        if not self.config.connection_id:
            raise ValueError("AIRBYTE_CONNECTION_ID not set")
        if not self.client.health():
            raise RuntimeError(f"Airbyte API not reachable at {self.config.airbyte_url}")

        logger.info("Triggering Airbyte sync for connection=%s",
                    self.config.connection_id)
        resp = self.client.trigger_sync(self.config.connection_id)
        job_id = int(resp.get("jobId") or resp.get("id") or 0)
        if not job_id:
            raise RuntimeError(f"Airbyte did not return a jobId: {resp}")

        result = self._wait_for_job(job_id)
        self._last_result = result
        if result.status == PipelineStatus.SUCCEEDED:
            logger.info(
                "Airbyte job %s done in %.1fs (records=%s)",
                job_id, result.duration_s or 0, result.records_synced,
            )
        else:
            logger.error("Airbyte job %s ended with %s: %s",
                         job_id, result.status.value, result.error)
        return result

    def dry_run(self) -> dict[str, Any]:
        """健康检查: 不真正同步, 仅返回 source/destination/connection 状态."""
        return {
            "airbyte_url": self.config.airbyte_url,
            "reachable": self.client.health(),
            "sources": [s.get("name") for s in self.client.list_sources()],
            "destinations": [d.get("name") for d in self.client.list_destinations()],
            "connections": [
                {
                    "id": c.get("connectionId"),
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "schedule": c.get("schedule"),
                }
                for c in self.client.list_connections()
            ],
        }

    @property
    def last_result(self) -> Optional[PipelineResult]:
        return self._last_result


# ---------------------------------------------------------------- singleton
_pipeline: Optional[ETLPipeline] = None


def get_pipeline() -> ETLPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ETLPipeline()
    return _pipeline


def reset_pipeline() -> None:
    global _pipeline
    _pipeline = None
