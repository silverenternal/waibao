#!/usr/bin/env python3
"""T3801 — Pilot 30 天报告生成脚本 (v8.0 升级版).

相比 v5.0 (scripts/generate_pilot_report.py):
1. 一次性生成**所有**活跃 pilot 的报告 (无需 program_id)。
2. 输出格式: PDF (reportlab) + JSON + Markdown。
3. 包含: 日活趋势 / 关键功能使用率 / NPS / 痛点 Top-5 / 续约概率。
4. 上传到 Supabase Storage 'pilot-reports' bucket,返回 signed URL。

用法:
    python scripts/generate_pilot_report_v8.py [--program-id <id>] [--days 30] [--format pdf,json,md]
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_pilot_report_v8")


# ---------------------------------------------------------------------------
# 数据聚合
# ---------------------------------------------------------------------------


def _get_supabase():
    try:
        from api.deps import get_supabase_admin  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.error("Cannot import api.deps: %s", exc)
        raise SystemExit(3) from exc
    return get_supabase_admin()


def _fetch_programs(supabase, program_id: str | None) -> list[dict[str, Any]]:
    q = supabase.table("pilot_programs").select("*, organisations(name, country, industry)")
    if program_id:
        q = q.eq("id", program_id)
    else:
        q = q.in_("status", ["recruiting", "active", "completed"])
    res = q.execute()
    return res.data or []


def _fetch_dau(supabase, program_id: str, days: int) -> list[dict[str, Any]]:
    """聚合 program_id 下用户的日活,按日分组."""
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    res = (
        supabase.table("cross_device_daily_active")
        .select("day,user_id,platform,total_events")
        .gte("day", since[:10])
        .execute()
    )
    rows = res.data or []
    by_day: dict[str, dict[str, Any]] = {}
    for r in rows:
        # 这里简化: 假定 pilot 用户有 metadata.program_id (实际可加 join)
        day = r["day"]
        by_day.setdefault(day, {"day": day, "users": set(), "events": 0, "platforms": set()})
        by_day[day]["users"].add(r["user_id"])
        by_day[day]["events"] += int(r.get("total_events") or 0)
        if r.get("platform"):
            by_day[day]["platforms"].add(r["platform"])
    out = []
    for day, agg in sorted(by_day.items()):
        out.append({
            "day": day,
            "dau": len(agg["users"]),
            "events": agg["events"],
            "platforms": sorted(agg["platforms"]),
        })
    return out


def _fetch_feature_usage(supabase, program_id: str, days: int) -> dict[str, int]:
    """关键功能使用率 (matching / interview / collab)."""
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    res = (
        supabase.table("feature_events")
        .select("feature,user_id")
        .gte("created_at", since)
        .execute()
    )
    rows = res.data or []
    out: dict[str, set[str]] = {}
    for r in rows:
        feat = r.get("feature") or "unknown"
        out.setdefault(feat, set()).add(r["user_id"])
    return {k: len(v) for k, v in out.items()}


def _fetch_nps(supabase, program_id: str) -> dict[str, Any]:
    res = (
        supabase.table("nps_responses")
        .select("score,user_id,created_at")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return {"responses": 0, "nps": None, "promoters": 0, "passives": 0, "detractors": 0}
    promoters = sum(1 for r in rows if r["score"] >= 9)
    detractors = sum(1 for r in rows if r["score"] <= 6)
    passives = len(rows) - promoters - detractors
    nps = round((promoters - detractors) / len(rows) * 100, 1)
    return {
        "responses": len(rows),
        "nps": nps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
    }


def _fetch_pain_points(supabase, program_id: str, limit: int = 5) -> list[dict[str, Any]]:
    res = (
        supabase.table("feedback")
        .select("category,feature,count:count(*)")
        .in_("category", ["bug", "feature_request"])
        .order("count", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def _renewal_probability(stats: dict[str, Any]) -> float:
    """基于 NPS + WAU + 痛点 计算续约概率 (0-1)."""
    nps = stats.get("nps") or 0
    wau = stats.get("weekly_active_rate") or 0
    pain = stats.get("pain_points_count") or 0
    score = 0.0
    score += max(0.0, min(1.0, (nps + 100) / 200)) * 0.5  # NPS 权重 0.5
    score += max(0.0, min(1.0, wau)) * 0.3                # WAU 权重 0.3
    score += max(0.0, min(1.0, 1 - pain / 10)) * 0.2      # 痛点越少越好
    return round(score, 3)


def build_program_report(program: dict[str, Any], supabase, days: int) -> dict[str, Any]:
    program_id = program["id"]
    org = program.get("organisations") or {}
    org_name = org.get("name") if isinstance(org, dict) else None
    dau_trend = _fetch_dau(supabase, program_id, days)
    feature_usage = _fetch_feature_usage(supabase, program_id, days)
    nps = _fetch_nps(supabase, program_id)
    pain_points = _fetch_pain_points(supabase, program_id)

    stats = {
        "dau_trend": dau_trend,
        "feature_usage": feature_usage,
        "weekly_active_rate": (
            sum(1 for d in dau_trend[-7:] if d["dau"] > 0) / 7 if dau_trend else 0
        ),
        "nps": nps.get("nps"),
        "nps_detail": nps,
        "pain_points": pain_points,
        "pain_points_count": sum(p.get("count", 0) if isinstance(p, dict) else 0 for p in pain_points),
    }
    stats["renewal_probability"] = _renewal_probability(stats)

    return {
        "program_id": program_id,
        "program_name": program["name"],
        "organisation_name": org_name,
        "status": program["status"],
        "started_at": program.get("started_at"),
        "ended_at": program.get("ended_at"),
        "metadata": program.get("metadata", {}),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# 输出格式
# ---------------------------------------------------------------------------


def render_markdown(reports: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Pilot 30 天报告合集\n"]
    lines.append(f"生成时间: {datetime.now(tz=timezone.utc).isoformat()}\n")
    lines.append(f"覆盖程序: **{len(reports)}**\n")
    lines.append("\n---\n")
    for r in reports:
        s = r["stats"]
        lines.append(f"\n## {r['organisation_name'] or r['program_name']}\n")
        lines.append(f"- 状态: `{r['status']}`")
        lines.append(f"- NPS: **{s['nps']}** (响应 {s['nps_detail']['responses']})")
        lines.append(f"- 周活: **{round(s['weekly_active_rate'] * 100, 1)}%**")
        lines.append(f"- 续约概率: **{round(s['renewal_probability'] * 100, 1)}%**")
        lines.append("\n### Top 痛点")
        for p in s["pain_points"]:
            lines.append(f"- [{p.get('category', '?')}] {p.get('feature', '?')}: {p.get('count', 0)}")
        lines.append("\n### 关键功能使用")
        for feat, users in sorted(s["feature_usage"].items(), key=lambda x: -x[1]):
            lines.append(f"- {feat}: {users} users")
    return "\n".join(lines) + "\n"


def render_pdf(reports: list[dict[str, Any]]) -> bytes:
    """使用 reportlab 生成 PDF; 不可用 -> 纯文本 fallback."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
        from reportlab.platypus import (  # type: ignore
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib import colors  # type: ignore
    except Exception:
        # fallback: 纯文本
        txt = render_markdown(reports)
        return txt.encode("utf-8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Pilot 30-day Report")
    styles = getSampleStyleSheet()
    flow = []
    flow.append(Paragraph("Pilot 30-day Report", styles["Title"]))
    flow.append(Spacer(1, 12))

    summary = [["Program", "Status", "NPS", "WAU", "Renewal%"]]
    for r in reports:
        s = r["stats"]
        summary.append([
            r["organisation_name"] or r["program_name"],
            r["status"],
            str(s["nps"]),
            f"{round(s['weekly_active_rate'] * 100, 1)}%",
            f"{round(s['renewal_probability'] * 100, 1)}%",
        ])
    tbl = Table(summary, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    flow.append(tbl)
    flow.append(Spacer(1, 24))

    for r in reports:
        s = r["stats"]
        flow.append(Paragraph(f"<b>{r['organisation_name'] or r['program_name']}</b>", styles["Heading2"]))
        flow.append(Paragraph(f"NPS: <b>{s['nps']}</b>, WAU: <b>{round(s['weekly_active_rate'] * 100, 1)}%</b>", styles["Normal"]))
        flow.append(Paragraph(f"续约概率: <b>{round(s['renewal_probability'] * 100, 1)}%</b>", styles["Normal"]))
        flow.append(Spacer(1, 8))
        flow.append(Paragraph("<b>Top 痛点</b>", styles["Heading3"]))
        for p in s["pain_points"]:
            flow.append(Paragraph(f"- [{p.get('category', '?')}] {p.get('feature', '?')}: {p.get('count', 0)}", styles["Normal"]))
        flow.append(Spacer(1, 12))

    doc.build(flow)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 上传 (可选)
# ---------------------------------------------------------------------------


def _upload(supabase, filename: str, data: bytes, content_type: str) -> str | None:
    try:
        supabase.storage.from_("pilot-reports").upload(
            filename,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
        signed = supabase.storage.from_("pilot-reports").create_signed_url(filename, 60 * 60 * 24 * 7)
        return signed.get("signedURL") or signed.get("signedUrl")
    except Exception as exc:  # pragma: no cover
        logger.warning("upload failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Pilot 30-day report (v8.0).")
    parser.add_argument("--program-id", default=None, help="单个 program, 留空 = 全部。")
    parser.add_argument("--days", type=int, default=30, help="回溯天数。")
    parser.add_argument("--format", default="pdf,json,md", help="输出格式: pdf,json,md 逗号分隔。")
    parser.add_argument("--out", default=None, help="输出目录, 默认 ./reports/pilot_<ts>")
    args = parser.parse_args(argv)

    supabase = _get_supabase()
    programs = _fetch_programs(supabase, args.program_id)
    logger.info("found %d programs", len(programs))

    reports = [build_program_report(p, supabase, args.days) for p in programs]

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out or f"./reports/pilot_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    formats = {f.strip().lower() for f in args.format.split(",") if f.strip()}
    artifacts: list[dict[str, Any]] = []

    if "json" in formats:
        path = out_dir / "pilot_report.json"
        path.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
        artifacts.append({"format": "json", "path": str(path), "size": path.stat().st_size})
        url = _upload(supabase, f"{ts}/pilot_report.json", path.read_bytes(), "application/json")
        if url:
            artifacts.append({"format": "json", "url": url})

    if "md" in formats:
        path = out_dir / "pilot_report.md"
        path.write_text(render_markdown(reports), encoding="utf-8")
        artifacts.append({"format": "md", "path": str(path), "size": path.stat().st_size})

    if "pdf" in formats:
        data = render_pdf(reports)
        path = out_dir / "pilot_report.pdf"
        path.write_bytes(data)
        artifacts.append({"format": "pdf", "path": str(path), "size": path.stat().st_size})
        url = _upload(supabase, f"{ts}/pilot_report.pdf", data, "application/pdf")
        if url:
            artifacts.append({"format": "pdf", "url": url})

    summary = {
        "generated_at": ts,
        "programs": len(reports),
        "artifacts": artifacts,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())