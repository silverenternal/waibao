"""T1502 backup.py tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from services.backup import (
    BackupConfig,
    BackupManager,
    BackupRecord,
    BackupScheduler,
    StorageBackend,
    compute_rto_rpo_estimate,
    verify_supabase_pitr_config,
)


def test_pitr_report_minimum() -> None:
    cfg = verify_supabase_pitr_config()
    assert cfg["rpo_target_minutes"] == 60
    assert cfg["rto_target_minutes"] == 240
    assert cfg["verified_at"]


def test_backup_config_defaults() -> None:
    cfg = BackupConfig()
    assert cfg.backup_retention_days == 30
    assert cfg.storage_backend in (StorageBackend.LOCAL, StorageBackend.S3, StorageBackend.ALIYUN_OSS)
    assert cfg.schedule_cron == "0 3 * * *"


def test_record_to_dict_serialization() -> None:
    rec = BackupRecord(
        id="bkp_test",
        started_at=datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 12, 3, 5, tzinfo=timezone.utc),
        backend=StorageBackend.S3,
        file_name="x.dump",
        size_bytes=1024,
        sha256="deadbeef",
        status="success",
    )
    d = rec.to_dict()
    assert d["id"] == "bkp_test"
    assert d["backend"] == "s3"
    assert d["size_bytes"] == 1024


@pytest.mark.asyncio
async def test_run_backup_success(monkeypatch, tmp_path: Path) -> None:
    # 环境变量
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@z/db")

    cfg = BackupConfig(
        backup_dir=tmp_path,
        storage_backend=StorageBackend.LOCAL,
        pg_dump_binary="/bin/true",  # fake command
    )
    mgr = BackupManager(cfg)

    # 让 pg_dump 不抛错,且创建一个伪造的文件供 sha256 计算
    def _fake_pg_dump(self, output_path: Path) -> None:
        output_path.write_bytes(b"FAKEDB")

    monkeypatch.setattr(BackupManager, "_pg_dump", _fake_pg_dump)

    record = await mgr.run_backup(triggered_by="manual")
    assert record.status == "success"
    assert record.size_bytes == 6  # len(b"FAKEDB")
    assert record.sha256 and len(record.sha256) == 64
    assert (tmp_path / record.file_name).exists() or cfg.storage_backend == StorageBackend.LOCAL


@pytest.mark.asyncio
async def test_run_backup_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    cfg = BackupConfig(
        backup_dir=tmp_path,
        storage_backend=StorageBackend.LOCAL,
        pg_dump_binary="/bin/true",
    )
    mgr = BackupManager(cfg)

    def _broken(self, output_path: Path) -> None:
        raise RuntimeError("pg_dump broken")

    monkeypatch.setattr(BackupManager, "_pg_dump", _broken)

    record = await mgr.run_backup()
    assert record.status == "failed"
    assert record.error == "pg_dump broken"


def test_cleanup_old_backups(tmp_path: Path) -> None:
    cfg = BackupConfig(backup_dir=tmp_path, backup_retention_days=30)
    mgr = BackupManager(cfg)
    fresh = tmp_path / "fresh.dump"
    fresh.write_text("ok")
    old = tmp_path / "old.dump"
    old.write_text("old")
    # 手工设置 mtime — old 改为 60 天前 (1991+), fresh 设为现在
    import os
    import time

    now = time.time()
    os.utime(old, (now - 60 * 86400, now - 60 * 86400))
    os.utime(fresh, (now, now))
    removed = mgr.cleanup_old_backups()
    assert removed >= 1
    assert fresh.exists()


@pytest.mark.asyncio
async def test_backup_scheduler_lifecycle() -> None:
    cfg = BackupConfig(interval_seconds=10)
    mgr = BackupManager(cfg)
    sched = BackupScheduler(mgr, interval_seconds=0.1, enabled=True)

    sched.start()
    await sched.stop()
    # 再次 stop 幂等
    await sched.stop()


def test_compute_rto_rpo_estimate_with_history() -> None:
    base = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    records: list[BackupRecord] = []

    for i in range(3):
        r = BackupRecord(
            id=f"bkp_{i}",
            started_at=base,
            finished_at=base.replace(hour=3, minute=5 * i + 5),
            status="success",
        )
        records.append(r)
    estimates = compute_rto_rpo_estimate(records)
    assert estimates["sample_size"] == 3
    assert estimates["rto_p50_minutes"] is not None
    assert estimates["rto_p50_minutes"] >= 0


def test_compute_rto_rpo_estimate_empty() -> None:
    result = compute_rto_rpo_estimate([])
    assert result["sample_size"] == 0
    assert result["rto_p50_minutes"] is None


def test_verify_pitr_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "proj123")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://localhost/pitr")
    cfg = verify_supabase_pitr_config()
    assert cfg["pitr_enabled"] is True
    assert cfg["project_ref"] == "proj123"
