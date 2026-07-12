"""Compliance / Legal / GDPR API 测试 — T1201."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_compliance_state():
    """每个测试前清空内存中保存的 consent / audit."""
    import compliance.consent as cmod
    from compliance.consent import ConsentService

    cmod._singleton = ConsentService()
    yield


# ---------------------------------------------------------------------------
# /api/legal
# ---------------------------------------------------------------------------

def test_legal_root():
    from api.legal import router

    # 简单通过路径可达性测试
    paths = [r.path for r in router.routes]
    assert "/legal" in paths
    assert "/legal/versions" in paths
    assert "/legal/{doc_type}" in paths


def test_legal_doc_resolve_lang():
    from api.legal import _resolve_lang

    assert _resolve_lang("zh-CN") == "zh-CN"
    assert _resolve_lang("en-US") == "en-US"
    assert _resolve_lang("ja-JP") == "ja-JP"
    assert _resolve_lang("en") == "en-US"
    assert _resolve_lang("ja") == "ja-JP"
    assert _resolve_lang("zh") == "zh-CN"
    assert _resolve_lang(None) == "zh-CN"
    assert _resolve_lang("garbage") == "zh-CN"  # 不识别 → fallback zh-CN


def test_get_legal_doc_terms_en():
    from api.legal import get_legal_doc

    res = get_legal_doc("terms", lang="en-US")
    # 异步 → 协程
    import asyncio
    data = asyncio.run(res)
    assert data["type"] == "terms"
    assert data["lang"] == "en-US"
    assert "Terms of Service" in data["content"]


def test_get_legal_doc_terms_zh():
    from api.legal import get_legal_doc

    import asyncio
    data = asyncio.run(get_legal_doc("terms", lang="zh-CN"))
    assert data["type"] == "terms"
    assert "服务条款" in data["content"]


def test_get_legal_doc_terms_ja():
    from api.legal import get_legal_doc

    import asyncio
    data = asyncio.run(get_legal_doc("terms", lang="ja-JP"))
    assert data["type"] == "terms"
    assert "利用規約" in data["content"]


def test_get_legal_doc_unknown_type():
    from fastapi import HTTPException

    from api.legal import get_legal_doc

    import asyncio
    try:
        asyncio.run(get_legal_doc("foo", lang="en-US"))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_list_legal_versions():
    from api.legal import list_legal_versions
    import asyncio

    data = asyncio.run(list_legal_versions())
    assert "versions" in data
    types = [v["type"] for v in data["versions"]]
    assert "terms" in types
    assert "privacy" in types
    assert "dpa" in types
    assert "cookies" in types


# ---------------------------------------------------------------------------
# /api/gdpr/consent — 业务逻辑(不通过 HTTP)
# ---------------------------------------------------------------------------

def test_consent_record_then_query():
    from compliance.consent import get_consent_service

    svc = get_consent_service()
    svc.record_consent_simple("u1", "analytics", True, ip="1.1.1.1", user_agent="test")
    status = svc.get_consent_status("u1")
    assert status["has_record"] is True
    assert status["decisions"]["analytics"] is True


def test_consent_withdraw_clears_status():
    from compliance.consent import get_consent_service

    svc = get_consent_service()
    svc.record_consent_simple("u2", "marketing", True)
    svc.withdraw_consent("u2", "marketing")
    status = svc.get_consent_status("u2")
    assert "marketing" not in status["decisions"]


# ---------------------------------------------------------------------------
# /api/gdpr/banner — 无需登录
# ---------------------------------------------------------------------------

def test_banner_no_login_zh():
    from api.gdpr import get_banner
    import asyncio

    data = asyncio.run(get_banner(lang="zh-CN"))
    assert "title" in data
    assert "categories" in data
    codes = [c["code"] for c in data["categories"]]
    assert "necessary" in codes
    assert "analytics" in codes
    assert "cross_border" in codes


def test_banner_no_login_en():
    from api.gdpr import get_banner
    import asyncio

    data = asyncio.run(get_banner(lang="en-US"))
    assert data["locale"] == "en-US"
    assert data["title"] == "We value your privacy"


# ---------------------------------------------------------------------------
# /api/gdpr/privacy summary
# ---------------------------------------------------------------------------

def test_privacy_summary_includes_t1201():
    from api.gdpr import privacy_policy
    import asyncio

    data = asyncio.run(privacy_policy())
    assert "user_rights" in data
    # T1201 新增了 withdraw 路径
    assert any("撤回同意" in r or "withdraw" in r.lower() for r in data["user_rights"])
    assert "encryption" in data
    assert "policy_versions" in data