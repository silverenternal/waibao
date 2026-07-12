"""T1702 — Pilot 报告生成单测 (PDF + text fallback)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Reuse fake store
from tests.test_pilot import FakeStore  # type: ignore

# 把模块先 import, 让 monkeypatch.setattr 能解析
import services.integrations.pilot_service  # noqa: F401
import services.integrations.pilot_invitation  # noqa: F401
import api.deps  # noqa: F401


@pytest.fixture
def fake_supabase(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("api.deps.get_supabase_admin", lambda: store)
    monkeypatch.setattr("services.integrations.pilot_service.get_supabase_admin", lambda: store)
    monkeypatch.setattr("services.integrations.pilot_invitation.get_supabase_admin", lambda: store)
    return store


def test_generate_monthly_report_text_basic(fake_supabase):
    from services.integrations.pilot_report import generate_monthly_report_text

    fake_supabase.tables["organisations"] = [{"id": "org-1", "name": "Acme"}]
    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "Acme Pilot", "status": "active", "target_nps": 50,
         "max_users": 20, "metadata": {}, "organisation_id": "org-1"},
    ]
    fake_supabase.tables["pilot_invitations"] = [
        {"id": "i1", "program_id": "prog-1", "status": "accepted", "email": "a@x.com", "role": "employer"},
    ]
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": "好用",
         "feature_used": "matching", "user_id": "u1", "created_at": "2026-01-01"},
        {"id": "f2", "program_id": "prog-1", "category": "nps", "score": 5, "comment": "",
         "feature_used": None, "user_id": "u2", "created_at": "2026-01-02"},
        {"id": "f3", "program_id": "prog-1", "category": "bug", "score": None,
         "comment": "页面崩溃", "feature_used": None, "user_id": "u3", "created_at": "2026-01-03"},
    ]

    text = generate_monthly_report_text("prog-1")
    assert "Pilot 月度报告" in text
    assert "Acme Pilot" in text
    assert "Acme" in text  # organisation
    assert "NPS" in text
    assert "周活" in text
    assert "Top 痛点" in text
    assert "页面崩溃" in text


def test_generate_monthly_report_text_program_not_found(fake_supabase):
    from services.integrations.pilot_report import generate_monthly_report_text

    with pytest.raises(LookupError):
        generate_monthly_report_text("missing")


def test_generate_monthly_report_writes_file(fake_supabase, tmp_path):
    from services.integrations.pilot_report import generate_monthly_report

    fake_supabase.tables["organisations"] = [{"id": "org-1", "name": "Acme"}]
    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "Acme Pilot", "status": "active", "target_nps": 50,
         "max_users": 20, "metadata": {}, "organisation_id": "org-1"},
    ]
    fake_supabase.tables["pilot_invitations"] = []
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": "",
         "feature_used": None, "user_id": "u1", "created_at": "2026-01-01"},
    ]

    out = tmp_path / "report.pdf"
    result = generate_monthly_report("prog-1", output_path=str(out))
    assert Path(result["path"]).exists()
    # format 是 "pdf" 或 "text" (取决于环境是否装 reportlab)
    assert result["format"] in {"pdf", "text"}
    assert result["bytes"] > 0
    assert "report" in result


def test_generate_monthly_report_default_path(fake_supabase, tmp_path, monkeypatch):
    from services.integrations.pilot_report import generate_monthly_report

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-2", "name": "X", "status": "active", "target_nps": 50,
         "max_users": 5, "metadata": {}, "organisation_id": None},
    ]
    fake_supabase.tables["pilot_invitations"] = []
    fake_supabase.tables["pilot_feedback"] = []

    monkeypatch.chdir(tmp_path)
    result = generate_monthly_report("prog-2")
    assert Path(result["path"]).exists()
    assert Path(result["path"]).name.startswith("pilot_report_")


def test_generate_monthly_report_includes_notes_when_below_target(fake_supabase):
    from services.integrations.pilot_report import generate_monthly_report_text

    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "P", "status": "active", "target_nps": 50,
         "max_users": 5, "metadata": {}, "organisation_id": None},
    ]
    # 全部 detractor → NPS = -100 → 触发 note
    fake_supabase.tables["pilot_invitations"] = [
        {"id": "i1", "program_id": "prog-1", "status": "accepted", "email": "a@x.com", "accepted_at": "2026-01-01"},
    ]
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 0, "comment": "",
         "feature_used": None, "user_id": "u1", "created_at": "2026-01-01"},
    ]
    text = generate_monthly_report_text("prog-1")
    assert "备注" in text or "建议" in text or "CS / PM 备注" in text


def test_pdf_generation_with_reportlab(monkeypatch, fake_supabase):
    """如果 reportlab 可用, 走 PDF 路径."""
    fake_supabase.tables["pilot_programs"] = [
        {"id": "prog-1", "name": "X", "status": "active", "target_nps": 50,
         "max_users": 5, "metadata": {}, "organisation_id": None},
    ]
    fake_supabase.tables["pilot_invitations"] = []
    fake_supabase.tables["pilot_feedback"] = [
        {"id": "f1", "program_id": "prog-1", "category": "nps", "score": 10, "comment": "",
         "feature_used": None, "user_id": "u1", "created_at": "2026-01-01"},
    ]

    # reportlab 可能不可用, 这里测试 _try_pdf_bytes 返回值
    from services.integrations.pilot_report import _try_pdf_bytes

    text = "Sample report\nNPS: 50"
    pdf_bytes = _try_pdf_bytes("prog-1", "X", text)
    if pdf_bytes is not None:
        # PDF magic number
        assert pdf_bytes.startswith(b"%PDF")
    else:
        # 没装 reportlab — 不视为失败
        pytest.skip("reportlab not installed")


def test_format_percent_and_bar():
    from services.integrations.pilot_report import _format_percent, _bar

    assert _format_percent(None) == "N/A"
    assert _format_percent(0.5) == "50.0%"
    assert _bar(0.5).startswith("[")
    assert "50%" in _bar(0.5)


def test_cli_script_help():
    """验证 scripts/generate_pilot_report.py 的 argparse 配置."""
    import subprocess

    repo_root = Path(ROOT).parent
    script = repo_root / "scripts" / "generate_pilot_report.py"
    if not script.exists():
        pytest.skip("script not in expected location")
    # 跑 help 应该 exit code 0
    res = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 0
    assert "program_id" in res.stdout