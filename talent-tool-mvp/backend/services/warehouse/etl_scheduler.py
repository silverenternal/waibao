"""T2801 — ETL 定时调度 (每小时跑一次).

两种模式:
1. 内嵌模式: 启后台线程, 在 FastAPI 进程里跑 (开发用)
2. 外部模式: 单独 docker container 跑 (生产用)

为什么用 threading 而不是 APScheduler: 简单 / 无外部依赖, 与 FastAPI 生命周期绑定.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

from .etl_pipeline import ETLPipeline, PipelineResult, PipelineStatus, get_pipeline

logger = logging.getLogger("waibao.warehouse.scheduler")


class ETLScheduler:
    """简单 interval scheduler."""

    def __init__(
        self,
        pipeline: Optional[ETLPipeline] = None,
        interval_seconds: int = 3600,  # 每小时
        enabled: bool = True,
    ) -> None:
        self.pipeline = pipeline or get_pipeline()
        self.interval_seconds = int(os.getenv("ETL_INTERVAL_SECONDS", str(interval_seconds)))
        self.enabled = (
            enabled and os.getenv("ETL_SCHEDULER_ENABLED", "1") == "1"
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_result: Optional[PipelineResult] = None
        self._last_run_at: Optional[datetime] = None
        self._next_run_at: Optional[datetime] = None
        self._run_lock = threading.Lock()
        self._total_runs = 0
        self._failed_runs = 0

    # -------------------------------------------------------- core
    def _loop(self) -> None:
        logger.info("ETL scheduler started (interval=%ss, enabled=%s)",
                    self.interval_seconds, self.enabled)
        # 启动后等 30s 让其它服务先起
        if self._stop_event.wait(30):
            return
        while not self._stop_event.is_set():
            self._schedule_next_run()
            if not self._stop_event.wait(self.interval_seconds):
                self._run_once_safe()
        logger.info("ETL scheduler stopped")

    def _schedule_next_run(self) -> None:
        from datetime import timedelta
        self._next_run_at = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)

    def _run_once_safe(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            logger.warning("Previous ETL run still in progress, skipping this tick")
            return
        try:
            self._run_once()
        finally:
            self._run_lock.release()

    def _run_once(self) -> PipelineResult:
        self._last_run_at = datetime.now(timezone.utc)
        self._total_runs += 1
        try:
            result = self.pipeline.run()
            self._last_result = result
            if result.status == PipelineStatus.FAILED:
                self._failed_runs += 1
            return result
        except Exception as e:  # noqa: BLE001
            self._failed_runs += 1
            logger.error("ETL run crashed: %s\n%s", e, traceback.format_exc())
            fake = PipelineResult(
                job_id="scheduler-error",
                status=PipelineStatus.FAILED,
                started_at=self._last_run_at,
                finished_at=datetime.now(timezone.utc),
                error=str(e),
            )
            self._last_result = fake
            return fake

    # -------------------------------------------------------- public
    def start(self) -> None:
        if not self.enabled:
            logger.info("ETL scheduler disabled by config")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="etl-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def run_now(self) -> PipelineResult:
        """手动触发一次. 给管理 API / 测试用."""
        return self._run_once()

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "running": self._thread is not None and self._thread.is_alive(),
            "interval_seconds": self.interval_seconds,
            "total_runs": self._total_runs,
            "failed_runs": self._failed_runs,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "next_run_at": self._next_run_at.isoformat() if self._next_run_at else None,
            "last_result": self._last_result.to_dict() if self._last_result else None,
        }


# ---------------------------------------------------------------- singleton
_scheduler: Optional[ETLScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> ETLScheduler:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = ETLScheduler()
        return _scheduler


def start_scheduler_in_background() -> ETLScheduler:
    sched = get_scheduler()
    sched.start()
    return sched


def stop_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.stop()
            _scheduler = None
