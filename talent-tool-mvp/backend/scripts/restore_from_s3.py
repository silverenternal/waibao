#!/usr/bin/env python3
"""T1502 — Restore logical backup from S3.

Usage:
    python scripts/restore_from_s3.py --key postgresql/waibao-20240715.dump \
        --target-db postgresql://user:pass@host:5432/restored

Notes:
- 默认模式: 只下载 + 校验 sha256,不实际执行 pg_restore (DRY-RUN)
- 用 --execute 实际执行 pg_restore; 使用时请确认目标 DB 已 dry-validated
- 演练场景下使用 staging DB, 切勿在生产 cluster 未经审批前执行
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def _download_s3(bucket: str, key: str, dest: Path) -> None:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit("boto3 not installed; pip install boto3") from exc
    client = boto3.client("s3")
    client.download_file(bucket, key, str(dest))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description="Restore PostgreSQL from S3")
    p.add_argument("--bucket", default=os.getenv("BACKUP_S3_BUCKET", "waibao-backups"))
    p.add_argument("--key", required=True, help="S3 object key, e.g. postgresql/waibao-*.dump")
    p.add_argument("--target-db", default=os.getenv("DATABASE_URL", ""),
                   help="PostgreSQL URL for the target database")
    p.add_argument("--execute", action="store_true",
                   help="Actually run pg_restore (else dry-run only)")
    args = p.parse_args()

    backup_dir = BACKEND_ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(args.key).name
    target = backup_dir / filename

    print(f"[restore] downloading s3://{args.bucket}/{args.key} -> {target}")
    _download_s3(args.bucket, args.key, target)
    sha = _sha256(target)
    size = target.stat().st_size
    print(f"[restore] ok size={size} sha256={sha[:12]}…")

    if not args.execute:
        print("[restore] dry-run — pass --execute to run pg_restore")
        return 0

    if not args.target_db:
        print("ERROR: --target-db is empty", file=sys.stderr)
        return 2

    cmd = [
        "pg_restore",
        "--no-owner",
        "--no-acl",
        "--clean",
        "--if-exists",
        "--dbname", args.target_db,
        str(target),
    ]
    print(f"[restore] executing: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"[restore] pg_restore failed rc={rc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
