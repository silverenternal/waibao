"""Consent Service 测试 — T1201."""
from __future__ import annotations

from compliance.consent import (
    ConsentDecision,
    ConsentService,
    get_consent_service,
)


def setup_function(_):
    """每个测试前重置单例."""
    import compliance.consent as mod

    mod._singleton = ConsentService()


def test_record_consent_simple():
    svc = get_consent_service()
    record = svc.record_consent_simple(
        user_id="u1",
        consent_type="analytics",
        granted=True,
        ip="192.0.2.1",
        user_agent="Mozilla/5.0",
    )
    assert record.user_id == "u1"
    assert record.decisions[0].category == "analytics"
    assert record.decisions[0].granted is True


def test_get_consent_status_empty():
    svc = get_consent_service()
    status = svc.get_consent_status("nobody")
    assert status["has_record"] is False
    assert status["decisions"] == {}


def test_get_consent_status_after_record():
    svc = get_consent_service()
    svc.record_consent_simple("u2", "necessary", True)
    svc.record_consent_simple("u2", "marketing", True)
    svc.record_consent_simple("u2", "marketing", False)  # 撤回
    status = svc.get_consent_status("u2")
    assert status["has_record"] is True
    assert status["decisions"]["necessary"] is True
    assert status["decisions"]["marketing"] is False  # 撤回后为 False


def test_withdraw_consent_specific_category():
    svc = get_consent_service()
    svc.record_consent_simple("u3", "analytics", True)
    svc.record_consent_simple("u3", "marketing", True)
    svc.withdraw_consent("u3", "analytics")
    status = svc.get_consent_status("u3")
    assert "analytics" not in status["decisions"]
    assert status["decisions"]["marketing"] is True


def test_withdraw_all_consent():
    svc = get_consent_service()
    svc.record_consent_simple("u4", "analytics", True)
    svc.record_consent_simple("u4", "marketing", True)
    svc.withdraw_consent("u4")
    status = svc.get_consent_status("u4")
    assert status["decisions"] == {}
    assert status["withdrawn_at"] is not None


def test_has_consent():
    svc = get_consent_service()
    svc.record_consent_simple("u5", "marketing", True)
    assert svc.has_consent("u5", "marketing") is True
    assert svc.has_consent("u5", "analytics") is False


def test_banner_zh():
    svc = get_consent_service()
    banner = svc.build_banner("zh")
    assert banner.title == "我们重视您的隐私"
    assert "marketing" in {c["code"] for c in banner.categories}


def test_banner_en():
    svc = get_consent_service()
    banner = svc.build_banner("en")
    assert banner.title == "We value your privacy"


def test_subject_id_hash_unreversible():
    svc = get_consent_service()
    h = svc.hash_subject("alice@example.com")
    assert len(h) == 32
    # 同一输入 → 同一 hash
    assert svc.hash_subject("alice@example.com") == h
    # 不同输入 → 不同 hash
    assert svc.hash_subject("bob@example.com") != h


def test_ip_hashed_not_stored():
    svc = get_consent_service()
    svc.record_consent_simple("u6", "analytics", True, ip="1.2.3.4")
    record = svc.get_record("u6")
    assert record.ip_hash is not None
    assert record.ip_hash != "1.2.3.4"


def test_export_user_data_gdpr():
    svc = get_consent_service()
    svc.record_consent_simple("u7", "analytics", True)
    data = svc.export_user_data("u7")
    assert data["found"] is True
    assert "subject_id_hash" in data
    assert "decisions" in data


def test_consent_audit_logged():
    """每次 record / withdraw 都会写 audit log."""
    from compliance.audit import get_audit_logger

    audit = get_audit_logger()
    before = len(audit.query(resource="consent", limit=100))
    svc = get_consent_service()
    svc.record_consent_simple("u8", "analytics", True)
    svc.withdraw_consent("u8", "analytics")
    after = len(audit.query(resource="consent", limit=100))
    # 至少新增 2 条
    assert after >= before + 2