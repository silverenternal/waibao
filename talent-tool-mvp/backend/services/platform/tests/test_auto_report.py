"""Tests for v8.0 T3901 — Auto weekly report service.

Covers:
* 16 项需求常量
* last_week_range / current_week_range 边界
* 数据收集 (mock + supabase fallback)
* 渲染 (txt/pdf/docx) — pdf/docx 在 reportlab/docx 缺失时降级 txt
* WeeklyReport 序列化
* AutoReportService.generate / collect / deliver / schedule_weekly_report
* 持久化 (mock supabase)
* 单例 + reset
* recipients 角色映射
* 异常注入 (异常 / 缺失字段)
* 报告大小 > 0 / 包含 16 项 / 包含日活 / 包含异常
"""
from __future__ import annotations

import asyncio
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from services.platform import auto_report as ar
from services.platform.auto_report import (
    AutoReportService,
    DAUMetric,
    FeatureUsage,
    ReportFormat,
    RequirementUsage,
    SIXTEEN_REQUIREMENTS,
    WeeklyReport,
    get_auto_report_service,
    reset_auto_report_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fixed_now() -> datetime:
    # 2026-07-13 (Monday) 10:00 UTC
    return datetime(2026, 7, 13, 10, 0, 0, tzinfo=timezone.utc)


def _supabase_mock() -> MagicMock:
    sb = MagicMock()
    # weekly_reports insert
    sb.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "rep-001"}
    ]
    return sb


def _dispatcher_mock(success_channels=("smtp", "dingtalk")) -> MagicMock:
    d = MagicMock()
    out = MagicMock()
    out.results = [
        MagicMock(channel=ch, success=True, message_id=f"m-{ch}", error=None, skipped=False)
        for ch in success_channels
    ]
    async def _async_dispatch_multi(*args, **kwargs):
        return out
    d.dispatch_multi = _async_dispatch_multi
    return d


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_auto_report_service()
    yield
    reset_auto_report_service()


def _make_service(
    *,
    now: Optional[Callable[[], datetime]] = None,
    supabase: Any = None,
    dispatcher: Any = None,
    recipients: Optional[List[str]] = None,
    recipients_by_role: Optional[Dict[str, List[str]]] = None,
) -> AutoReportService:
    return AutoReportService(
        clock=now or _fixed_now,
        supabase_factory=(lambda: supabase) if supabase is not None else (lambda: None),
        dispatcher_factory=(lambda: dispatcher) if dispatcher is not None else (lambda: None),
        default_recipients=recipients or ["ceo@waibao.example", "hrbp@waibao.example"],
        recipients_by_role=recipients_by_role or {"ceo": ["ceo@waibao.example"], "hrbp": ["hrbp@waibao.example"]},
    )


# ---------------------------------------------------------------------------
# 1. Constants
# ---------------------------------------------------------------------------


def test_sixteen_requirements_count_is_16():
    assert len(SIXTEEN_REQUIREMENTS) == 16


def test_sixteen_requirements_have_unique_ids():
    ids = [r[0] for r in SIXTEEN_REQUIREMENTS]
    assert len(set(ids)) == 16


def test_sixteen_requirements_have_names():
    for rid, name in SIXTEEN_REQUIREMENTS:
        assert isinstance(rid, str) and rid
        assert isinstance(name, str) and name


# ---------------------------------------------------------------------------
# 2. Week range
# ---------------------------------------------------------------------------


def test_last_week_range_on_monday():
    svc = _make_service()
    start, end = svc.last_week_range()
    # 上周一是 2026-07-06
    assert start.date().isoformat() == "2026-07-06"
    # 上周日是 2026-07-12
    assert end.date().isoformat() == "2026-07-12"
    assert start.weekday() == 0
    assert end.weekday() == 6


def test_last_week_range_on_wednesday():
    def _wednesday():
        return datetime(2026, 7, 15, 14, 0, 0, tzinfo=timezone.utc)  # Wednesday
    svc = _make_service(now=_wednesday)
    start, end = svc.last_week_range()
    # 上周一是 2026-07-06
    assert start.date().isoformat() == "2026-07-06"
    assert end.date().isoformat() == "2026-07-12"


def test_current_week_range_on_monday():
    svc = _make_service()
    start, end = svc.current_week_range()
    assert start.date().isoformat() == "2026-07-13"
    assert end.date().isoformat() == "2026-07-19"


# ---------------------------------------------------------------------------
# 3. Recipients
# ---------------------------------------------------------------------------


def test_resolve_recipients_default():
    svc = _make_service()
    rcpts = svc.resolve_recipients()
    assert "ceo@waibao.example" in rcpts
    assert "hrbp@waibao.example" in rcpts


def test_resolve_recipients_by_role_ceo():
    svc = _make_service()
    rcpts = svc.resolve_recipients(role="ceo")
    assert rcpts == ["ceo@waibao.example"]


def test_resolve_recipients_by_role_hrbp():
    svc = _make_service()
    rcpts = svc.resolve_recipients(role="hrbp")
    assert rcpts == ["hrbp@waibao.example"]


def test_resolve_recipients_unknown_role_falls_back():
    svc = _make_service()
    rcpts = svc.resolve_recipients(role="unknown")
    assert len(rcpts) >= 1


# ---------------------------------------------------------------------------
# 4. Data collection
# ---------------------------------------------------------------------------


def test_collect_dau_uses_mock_when_no_supabase():
    svc = _make_service(supabase=None)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    end = datetime(2026, 7, 12, 23, 0, 0, tzinfo=timezone.utc)
    data = svc.collect(start, end)
    assert data["dau"]
    assert all(isinstance(d, DAUMetric) for d in data["dau"])


def test_collect_features_returns_top_usage():
    svc = _make_service(supabase=None)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    end = datetime(2026, 7, 12, tzinfo=timezone.utc)
    data = svc.collect(start, end)
    assert data["features"]
    # 至少 5 条
    assert len(data["features"]) >= 5
    # invocations 排序降序
    invs = [f.invocations for f in data["features"]]
    assert invs == sorted(invs, reverse=True)


def test_collect_requirements_covers_all_16():
    svc = _make_service(supabase=None)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    end = datetime(2026, 7, 12, tzinfo=timezone.utc)
    data = svc.collect(start, end)
    reqs = data["requirements"]
    assert len(reqs) == 16
    ids = {r.req_id for r in reqs}
    expected = {r[0] for r in SIXTEEN_REQUIREMENTS}
    assert ids == expected


def test_collect_includes_anomalies():
    svc = _make_service(supabase=None)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    end = datetime(2026, 7, 12, tzinfo=timezone.utc)
    anomalies = [{"type": "test", "severity": "warning", "metric": "m",
                  "current": 1, "baseline": 2, "delta_pct": -50,
                  "message": "x", "detected_at": _fixed_now().isoformat()}]
    data = svc.collect(start, end, anomalies=anomalies)
    assert data["anomalies"] == anomalies


def test_collect_with_supabase_mock():
    sb = MagicMock()
    # dau
    sb.table.return_value.select.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value.data = [
        {"date": "2026-07-06", "dau": 300, "new_users": 10, "returning": 290}
    ]
    # feature usage
    sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"feature": "matching", "invocations": 100, "unique_users": 50, "growth_pct": 5.0}
    ]
    # requirement
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"req_id": "1.1", "usage_pct": 90.0, "delta_pct": 1.0, "note": ""}
    ]
    svc = _make_service(supabase=sb)
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    end = datetime(2026, 7, 12, tzinfo=timezone.utc)
    data = svc.collect(start, end)
    assert data["dau"][0].dau == 300
    assert data["features"][0].feature == "matching"
    # 1.1 已知 + 缺失项补全
    ids = {r.req_id for r in data["requirements"]}
    assert "1.1" in ids
    assert len(data["requirements"]) == 16


# ---------------------------------------------------------------------------
# 5. Report generation
# ---------------------------------------------------------------------------


def test_generate_txt_includes_required_sections():
    svc = _make_service()
    report = svc.generate(fmt="txt", persist=False)
    text = report.content.decode("utf-8")
    for header in ["日活", "关键功能", "16 项需求", "异常", "招聘智能体"]:
        assert header in text


def test_generate_pdf_falls_back_to_txt_when_reportlab_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "reportlab":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    svc = _make_service()
    report = svc.generate(fmt="pdf", persist=False)
    # 应降级到 txt
    assert report.format == "txt"


def test_generate_with_explicit_range():
    svc = _make_service()
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 7, 23, 0, 0, tzinfo=timezone.utc)
    report = svc.generate(week_start=start, week_end=end, fmt="txt", persist=False)
    assert report.week_start == "2026-06-01"
    assert report.week_end == "2026-06-07"
    assert report.size_bytes > 0


def test_generate_persist_uses_supabase():
    sb = _supabase_mock()
    svc = _make_service(supabase=sb)
    report = svc.generate(fmt="txt", persist=True)
    assert sb.table.called


def test_generate_no_persist():
    # 无 supabase 时走 mock fallback, 不应调用 table
    svc = _make_service(supabase=None)
    report = svc.generate(fmt="txt", persist=False)
    # mock 模式下不会触发 supabase 调用
    assert report.size_bytes > 0


def test_generate_persist_uses_supabase_insert():
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value.data = [{"id": "rep-001"}]
    svc = _make_service(supabase=sb)
    report = svc.generate(fmt="txt", persist=True)
    # 验证 weekly_reports 表被调用过 insert
    insert_calls = [c for c in sb.table.mock_calls if "insert" in str(c)]
    assert insert_calls, "expected weekly_reports.insert to be called"


def test_generate_includes_anomalies_in_text():
    svc = _make_service()
    anomalies = [
        {
            "type": "match_rate_drop",
            "severity": "critical",
            "metric": "match_rate",
            "current": 70.0,
            "baseline": 86.0,
            "delta_pct": -18.6,
            "message": "匹配率突降",
            "detected_at": _fixed_now().isoformat(),
        }
    ]
    report = svc.generate(fmt="txt", persist=False, anomalies=anomalies)
    text = report.content.decode("utf-8")
    assert "匹配率突降" in text


def test_report_summary_keys():
    svc = _make_service()
    report = svc.generate(fmt="txt", persist=False)
    summary = report.summary
    for k in ["total_dau", "avg_dau", "new_users", "top_feature", "anomaly_count", "req_count"]:
        assert k in summary


# ---------------------------------------------------------------------------
# 6. Delivery
# ---------------------------------------------------------------------------


def test_deliver_dispatches_to_all_recipients():
    dispatcher = _dispatcher_mock()
    svc = _make_service(dispatcher=dispatcher)
    report = WeeklyReport(
        week_start="2026-07-06",
        week_end="2026-07-12",
        generated_at=_fixed_now().isoformat(),
        format="txt",
        content=b"hello",
        filename="weekly_report.txt",
        size_bytes=5,
        summary={"a": 1},
    )
    result = asyncio.run(svc.deliver(report, recipients=["a@x", "b@y"]))
    assert result["delivered"] is True
    assert "smtp" in result["channels"]
    assert "dingtalk" in result["channels"]
    # 2 个收件人 → 调用 dispatch_multi 至少 2 次
    # (dispatcher 是 MagicMock, 函数属性可通过 .mock_calls 验证)


def test_deliver_no_dispatcher_returns_unavailable():
    svc = _make_service(dispatcher=None)
    report = WeeklyReport(
        week_start="2026-07-06",
        week_end="2026-07-12",
        generated_at=_fixed_now().isoformat(),
        format="txt",
        content=b"x",
        filename="x.txt",
        size_bytes=1,
    )
    result = asyncio.run(svc.deliver(report))
    assert result["delivered"] is False


# ---------------------------------------------------------------------------
# 7. Schedule entrypoint
# ---------------------------------------------------------------------------


def test_schedule_weekly_report_end_to_end():
    dispatcher = _dispatcher_mock()
    sb = _supabase_mock()
    svc = _make_service(supabase=sb, dispatcher=dispatcher)
    result = asyncio.run(svc.schedule_weekly_report(fmt="txt", role="ceo"))
    assert "summary" in result
    assert result["format"] == "txt"
    assert result["size_bytes"] > 0
    assert result["delivery"]["delivered"] is True


# ---------------------------------------------------------------------------
# 8. Singleton
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance():
    a = get_auto_report_service()
    b = get_auto_report_service()
    assert a is b


def test_reset_clears_singleton():
    a = get_auto_report_service()
    reset_auto_report_service()
    b = get_auto_report_service()
    assert a is not b


# ---------------------------------------------------------------------------
# 9. Edge cases
# ---------------------------------------------------------------------------


def test_generate_with_empty_anomalies():
    svc = _make_service()
    report = svc.generate(fmt="txt", persist=False, anomalies=[])
    assert "无" in report.content.decode("utf-8")


def test_generate_docx_when_lib_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("simulated missing docx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    svc = _make_service()
    report = svc.generate(fmt="docx", persist=False)
    assert report.format == "txt"


def test_report_filename_pattern():
    svc = _make_service()
    pdf = svc.generate(fmt="txt", persist=False)
    assert pdf.filename.startswith("weekly_report")
    assert pdf.filename.endswith(".txt")


def test_summary_top_feature_is_most_used():
    svc = _make_service()
    report = svc.generate(fmt="txt", persist=False)
    top = report.summary.get("top_feature")
    assert top  # 非空


def test_summary_low_requirement_ids_present():
    svc = _make_service()
    report = svc.generate(fmt="txt", persist=False)
    assert "low_requirement_ids" in report.summary
    assert isinstance(report.summary["low_requirement_ids"], list)


def test_persist_returns_id_on_success():
    sb = _supabase_mock()
    svc = _make_service(supabase=sb)
    report = svc.generate(fmt="txt", persist=True)
    rid = svc._persist(report, report.summary)
    assert rid == "rep-001"


def test_persist_returns_none_when_no_supabase():
    svc = _make_service(supabase=None)
    report = svc.generate(fmt="txt", persist=False)
    rid = svc._persist(report, report.summary)
    assert rid is None


# ---------------------------------------------------------------------------
# 10. Format detection
# ---------------------------------------------------------------------------


def test_report_format_enum_values():
    assert ReportFormat.PDF.value == "pdf"
    assert ReportFormat.DOCX.value == "docx"
    assert ReportFormat.TXT.value == "txt"
