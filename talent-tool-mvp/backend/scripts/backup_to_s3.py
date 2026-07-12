#!/usr/bin/env python3
"""T1502 — Daily logical backup to S3.

Usage:
    python scripts/backup_to_s3.py             # do backup
    python scripts/backup_to_s3.py --dry-run   # check configuration
    python scripts/backup_to_s3.py --verify-only   # check PITR config

Required environment:
    DATABASE_URL                  (Supabase pooler / direct)
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    BACKUP_S3_BUCKET              (waibao-prod-backups or staging variant)

Optional:
    BACKUP_S3_PREFIX              (default: postgresql/)
    BACKUP_FORCE_PITR             (verify-only: report that PITR is OK)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Make backend importable when run from repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.backup import (  # noqa: E402
    BackupConfig,
    BackupManager,
    StorageBackend,
    verify_supabase_pitr_config,
)


async def _main(mode: str) -> int:
    cfg = BackupConfig(
        backup_dir=BACKEND_ROOT / "backups",
        storage_backend=StorageBackend.S3,
        s3_bucket=os.getenv("BACKUP_S3_BUCKET", "waibao-backups"),
        s3_prefix=os.getenv("BACKUP_S3_PREFIX", "postgresql/"),
        enabled=True,
    )
    mgr = BackupManager(cfg)

    if mode == "verify":
        report = verify_supabase_pitr_config()
        report["storage_backend"] = cfg.storage_backend.value
        report["s3_bucket"] = cfg.s3_bucket
        print(json.dumps(report, indent=2, default=str))
        return 0

    if mode == "dry-run":
        # 不执行 dump,只校验环境
        if not os.getenv("DATABASE_URL"):
            print("ERROR: DATABASE_URL not set", file=sys.stderr)
            return 2
        if not os.getenv("BACKUP_S3_BUCKET"):
            print("ERROR: BACKUP_S3_BUCKET not set", file=sys.stderr)
            return 2
        print("DRY-RUN OK — would upload to s3://%s/%s" % (
            cfg.s3_bucket, cfg.s3_prefix,
        ))
        return 0

    record = await mgr.run_backup(triggered_by="manual")
    print(json.dumps(record.to_dict(), indent=2, default=str))
    return 0 if record.status == "success" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup PostgreSQL to S3")
    parser.add_argument("--dry-run", action="store_const", const="dry-run", dest="mode", default="run")
    parser.add_argument("--verify-only", action="store_const", const="verify", dest="mode")
    args = parser.parse_args()
    return asyncio.run(_main(args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
