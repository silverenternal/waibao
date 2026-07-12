"""T1702 — Pilot 月度报告生成 (PDF).

支持两种后端:

1. ``reportlab`` (生产环境,真正 PDF)
2. 纯文本 fallback (本地无 reportlab 时,生成 .txt 报告,扩展名仍为 .pdf,
   内容为可打印的纯文本,便于 CI / 无依赖环境跑通)

入口:
- ``generate_monthly_report(program_id, output_path)``
- ``generate_monthly_report_text(program_id)`` -> str (PDF / 纯文本)
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.integrations.pilot_service import (
    NPS_TARGET,
    WEEKLY_ACTIVE_TARGET,
    generate_report,
)

logger = logging.getLogger("recruittech.services.pilot_report")


# ---------------------------------------------------------------------------
# 纯文本 fallback (确保始终可生成报告)
# ---------------------------------------------------------------------------


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _bar(value: float, width: int = 20) -> str:
    """简单 ASCII 进度条 (0..1)."""
    if value < 0:
        value = 0.0
    if value > 1:
        value = 1.0
    filled = int(round(value * width))
    return "[" + "#" * filled + "-" * (width - filled) + f"] {value * 100:.0f}%"


def generate_monthly_report_text(program_id: str) -> str:
    """生成月度报告 (纯文本格式,便于 fallback / 邮件正文)."""
    report = generate_report(program_id)
    stats = report.stats
    lines: list[str] = []

    lines.append("=" * 70)
    lines.append(f"  Pilot 月度报告 — {report.program_name}")
    lines.append("=" * 70)
    lines.append(f"报告时间: {report.generated_at}")
    if report.organisation_name:
        lines.append(f"客户组织: {report.organisation_name}")
    lines.append(f"项目状态: {report.status}")
    lines.append(f"开始时间: {report.started_at or 'N/A'}")
    lines.append(f"结束时间: {report.ended_at or '进行中'}")
    lines.append(f"目标 NPS: ≥{report.target_nps}")
    lines.append(f"目标周活: ≥{_format_percent(report.target_weekly_active)}")
    lines.append("")

    # KPI 总览
    lines.append("-" * 70)
    lines.append("关键指标 / Key Metrics")
    lines.append("-" * 70)
    lines.append(f"  NPS              : {stats.nps if stats.nps is not None else 'N/A'}  (目标 ≥{report.target_nps})")
    lines.append(f"  NPS 样本         : {stats.nps_responses}")
    lines.append(f"    Promoter (9-10): {stats.promoters}")
    lines.append(f"    Passive  (7-8) : {stats.passives}")
    lines.append(f"    Detractor (0-6): {stats.detractors}")
    lines.append(f"  邀请总数         : {stats.invitations_total}")
    lines.append(f"  已接受           : {stats.invitations_accepted}")
    lines.append(f"  接受率           : "
                 f"{_format_percent(stats.invitations_accepted / stats.invitations_total) if stats.invitations_total else 'N/A'}")
    lines.append(f"  周活用户         : {stats.weekly_active_users}")
    wau = stats.weekly_active_rate
    lines.append(f"  周活率           : {_format_percent(wau)}  {_bar(wau) if wau is not None else ''}")
    lines.append(f"  反馈总数         : {stats.feedback_total}")
    lines.append("")

    # 目标达成
    lines.append("-" * 70)
    lines.append("目标达成 / Targets Met")
    lines.append("-" * 70)
    for key, ok in (stats.targets_met or {}).items():
        lines.append(f"  [{'✓' if ok else '✗'}] {key}")
    lines.append("")

    # 分类统计
    if stats.feedback_by_category:
        lines.append("-" * 70)
        lines.append("反馈按类别 / Feedback by Category")
        lines.append("-" * 70)
        for cat, cnt in sorted(stats.feedback_by_category.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat:<20s} {cnt}")
        lines.append("")

    # 功能使用
    if stats.feedback_by_feature:
        lines.append("-" * 70)
        lines.append("反馈按功能 / Feedback by Feature")
        lines.append("-" * 70)
        for feat, cnt in sorted(stats.feedback_by_feature.items(), key=lambda x: -x[1]):
            lines.append(f"  {feat:<24s} {cnt}")
        lines.append("")

    # Top 痛点
    if stats.top_pain_points:
        lines.append("-" * 70)
        lines.append(f"Top 痛点 (≤{len(stats.top_pain_points)})")
        lines.append("-" * 70)
        for i, p in enumerate(stats.top_pain_points, 1):
            lines.append(f"  {i}. {p['tag']}  ({p['count']} 次)")
            for sample in p.get("samples", []):
                lines.append(f"     · {sample}")
        lines.append("")

    # 最近反馈
    if report.feedback_samples:
        lines.append("-" * 70)
        lines.append("最近反馈样本 (≤20)")
        lines.append("-" * 70)
        for f in report.feedback_samples[:20]:
            head = f"[{f.get('category', '?')}] score={f.get('score')}"
            lines.append(f"  {head}")
            comment = (f.get("comment") or "").strip()
            if comment:
                lines.append(f"    {comment[:120]}")
        lines.append("")

    # Notes
    if report.notes:
        lines.append("-" * 70)
        lines.append("CS / PM 备注")
        lines.append("-" * 70)
        for n in report.notes:
            lines.append(f"  - {n}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("  End of Report — waibao Pilot Team")
    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF 生成 (reportlab)
# ---------------------------------------------------------------------------


def _try_pdf_bytes(report_id: str, program_name: str, text: str) -> Optional[bytes]:
    """尝试用 reportlab 生成真正 PDF;失败返回 None."""
    try:
        from reportlab.lib import colors  # type: ignore[import-not-found]
        from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore[import-not-found]
        from reportlab.lib.units import cm  # type: ignore[import-not-found]
        from reportlab.pdfbase import pdfmetrics  # type: ignore[import-not-found]
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-not-found]
        from reportlab.platypus import (  # type: ignore[import-not-found]
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("pilot_report: reportlab unavailable, fallback to text (%s)", exc)
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Pilot Report {program_name}",
        author="waibao Pilot Team",
    )

    # 尝试注册中文字体;失败回退 Helvetica
    body_style: Any
    title_style: Any
    try:
        font_paths = [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
            "/Library/Fonts/PingFang.ttc",
        ]
        for fp in font_paths:
            if Path(fp).exists():
                pdfmetrics.registerFont(TTFont("CNFont", fp))
                body_style = ParagraphStyle(
                    "cn", fontName="CNFont", fontSize=10, leading=14
                )
                title_style = ParagraphStyle(
                    "cntitle", fontName="CNFont", fontSize=18, leading=22,
                    textColor=colors.HexColor("#0f172a"),
                )
                break
        else:
            raise RuntimeError("no CN font")
    except Exception:
        styles = getSampleStyleSheet()
        body_style = styles["BodyText"]
        title_style = styles["Title"]

    story: list[Any] = []
    story.append(Paragraph(f"Pilot 月度报告 — {program_name}", title_style))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"Report ID: <font color='#475569'>{report_id}</font>", body_style))
    story.append(Paragraph(
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        body_style,
    ))
    story.append(Spacer(1, 0.5 * cm))

    # 把纯文本按行渲染
    for raw_line in text.splitlines():
        if not raw_line.strip():
            story.append(Spacer(1, 0.3 * cm))
            continue
        safe = raw_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buf.getvalue()


def generate_monthly_report(
    program_id: str,
    output_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """生成月度报告 PDF,写入 ``output_path`` (默认 ``./pilot_report_<id>.pdf``).

    Returns:
        dict: ``{path, bytes, format, generated_at, report}``
    """
    report = generate_report(program_id)
    text = generate_monthly_report_text(program_id)
    pdf_bytes = _try_pdf_bytes(
        report_id=program_id, program_name=report.program_name, text=text,
    )

    out_path = Path(output_path) if output_path else Path(f"pilot_report_{program_id}.pdf")
    if pdf_bytes is not None:
        out_path.write_bytes(pdf_bytes)
        fmt = "pdf"
    else:
        # fallback: 写纯文本 (扩展名保留 .pdf 但内容是文本,便于识别)
        out_path.write_text(text, encoding="utf-8")
        fmt = "text"

    return {
        "path": str(out_path),
        "bytes": len(pdf_bytes) if pdf_bytes else len(text.encode("utf-8")),
        "format": fmt,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report": report.to_dict(),
    }


__all__ = ["generate_monthly_report", "generate_monthly_report_text"]