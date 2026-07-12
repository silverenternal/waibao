#!/usr/bin/env python3
"""T1702 — Pilot 月度报告生成脚本.

Usage:
    python scripts/generate_pilot_report.py <program_id> [--out path/to/report.pdf]

行为:
- 直接连接 Supabase (通过 ``api.deps.get_supabase_admin``) 拉取 program 详情
- 调用 ``services.integrations.pilot_report.generate_monthly_report`` 生成报告
- 报告格式: reportlab -> PDF; 不可用 -> 纯文本 fallback

退出码:
  0  成功
  2  参数错误
  3  program 不存在
  4  生成失败
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 把 backend 目录加入 sys.path, 保证 `from services.* import ...` 能解析
BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_pilot_report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate pilot monthly report (PDF / text fallback)."
    )
    parser.add_argument("program_id", help="pilot_programs.id (uuid)")
    parser.add_argument(
        "--out", "-o",
        default=None,
        help="输出文件路径 (默认 ./pilot_report_<id>.pdf)",
    )
    args = parser.parse_args(argv)

    if not args.program_id:
        print("ERROR: program_id required", file=sys.stderr)
        return 2

    try:
        from services.integrations.pilot_report import generate_monthly_report  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to import pilot_report: {exc}", file=sys.stderr)
        return 4

    try:
        result = generate_monthly_report(args.program_id, output_path=args.out)
    except LookupError as exc:
        print(f"ERROR: pilot program not found: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_monthly_report failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    print(f"OK: generated {result['format']} report")
    print(f"  path         : {result['path']}")
    print(f"  bytes        : {result['bytes']}")
    print(f"  generated_at : {result['generated_at']}")
    print(f"  final NPS    : {result['report']['stats'].get('nps')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())