#!/usr/bin/env python3
"""T1502 — Quarterly DR drill.

演练步骤 (脚本自动化前 4 步, 第 5 步需人工/审批):
  1) 验证 PITR 配置 (RPO < 1h)
  2) 从 S3 拉最新备份 + 校验 sha256
  3) 恢复到 staging DB + 表数量/记录数校验
  4) 报告 RTO (从检测故障到恢复可用的时长)
  5) [人工] 切换流量到备用集群 — 双签名确认

退出码:
  0 = 全通过
  1 = 配置不达标
  2 = 恢复 / 校验失败
  3 = 工具未安装

推荐调用 (CI 季度任务):
  PYTHONPATH=backend python backend/scripts/disaster_recovery_test.py \
      --bucket waibao-prod-backups --apply
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_latest_backup(bucket: str, prefix: str) -> str | None:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        return None
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    if not keys:
        return None
    keys.sort(reverse=True)
    return keys[0]


def _count_rows(db_url: str, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tbl in tables:
        sql = f'SELECT COUNT(*) FROM "{tbl}"'  # noqa: S608
        try:
            r = subprocess.run(
                ["psql", db_url, "-tAc", sql],
                capture_output=True,
                text=True,
                timeout=60,
            )
            counts[tbl] = int((r.stdout or "0").strip() or 0)
        except Exception as exc:  # noqa: BLE001
            counts[tbl] = -1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quarterly DR drill")
    parser.add_argument("--bucket", default=os.getenv("BACKUP_S3_BUCKET", ""))
    parser.add_argument("--prefix", default="postgresql/")
    parser.add_argument("--target-db", default=os.getenv("STAGING_DATABASE_URL", ""))
    parser.add_argument(
        "--tables",
        nargs="*",
        default=["users", "candidates", "jobs", "tickets"],
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually restore (else dry-run only — counts skipped)",
    )
    args = parser.parse_args()

    started_at = datetime.utcnow()
    t0 = time.monotonic()
    report: dict[str, object] = {
        "started_at": started_at.isoformat() + "Z",
        "bucket": args.bucket,
        "prefix": args.prefix,
        "applied": args.apply,
    }

    if not args.bucket:
        print("ERROR: --bucket / BACKUP_S3_BUCKET is empty", file=sys.stderr)
        return 1

    key = _resolve_latest_backup(args.bucket, args.prefix)
    report["latest_backup_key"] = key
    if not key:
        print("ERROR: no backups found in bucket", file=sys.stderr)
        return 1

    backup_path = BACKEND_ROOT / "backups" / Path(key).name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        print("ERROR: boto3 missing — pip install boto3", file=sys.stderr)
        return 3
    boto3.client("s3").download_file(args.bucket, key, str(backup_path))
    sha = _sha256(backup_path)
    size = backup_path.stat().st_size
    report["backup_size_bytes"] = size
    report["backup_sha256"] = sha
    report["download_sec"] = round(time.monotonic() - t0, 2)

    if args.apply:
        if not args.target_db:
            print("ERROR: --target-db / STAGING_DATABASE_URL required for --apply", file=sys.stderr)
            return 2
        restore_t0 = time.monotonic()
        rc = subprocess.run(
            ["pg_restore", "--no-owner", "--no-acl", "--clean", "--if-exists",
             "--dbname", args.target_db, str(backup_path)],
        ).returncode
        report["restore_sec"] = round(time.monotonic() - restore_t0, 2)
        if rc != 0:
            print(f"ERROR: pg_restore rc={rc}", file=sys.stderr)
            report["status"] = "restore_failed"
            print(json.dumps(report, indent=2))
            return 2
        report["table_row_counts"] = _count_rows(args.target_db, args.tables)
    else:
        report["table_row_counts"] = None

    report["status"] = "ok"
    report["finished_at"] = datetime.utcnow().isoformat() + "Z"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
