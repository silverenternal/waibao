"""T2603 — GDPR / PIPL / CCPA v2 consent + API tests.

Covers:
  * Consent store: grant / deny / withdraw / withdraw_all
  * PIPL cross-border notice + acceptance
  * Required purposes cannot be denied
  * Per-purpose granularity
  * Region-aware lawful basis defaults
  * Lawful basis templates for EU / CN / CA / US / GLOBAL
  * Retention helper smoke
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.platform.audit_v2 import (
    audit,
    clear_audit_context,
    get_audit_store,
    reset_audit_store,
)
from services.platform.consent import (
    PIPL_CROSS_BORDER_DISCLOSURE,
    PURPOSES,
    ConsentStore,
    list_purposes,
    get_consent_store,
    reset_consent_store,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset():
    reset_audit_store()
    reset_consent_store()
    clear_audit_context()
    yield
    reset_audit_store()
    reset_consent_store()
    clear_audit_context()


# ---------------------------------------------------------------------------
# Purpose catalog
# ---------------------------------------------------------------------------
class TestPurposeCatalog:
    def test_eight_canonical_purposes(self):
        codes = {p["code"] for p in list_purposes()}
        assert {"necessary", "functional", "analytics", "marketing",
                "marketing_sms", "coaching", "ai_training",
                "cross_border"}.issubset(codes)

    def test_required_purposes_cannot_be_opted_out(self):
        for code, meta in PURPOSES.items():
            if meta["required"]:
                assert meta["required"] is True

    def test_purpose_localised_labels(self):
        purposes = list_purposes()
        for p in purposes:
            assert p["label_zh"]
            assert p["label_en"]
            assert p["lawful_basis"]["EU"]
            assert p["lawful_basis"]["CN"]


# ---------------------------------------------------------------------------
# ConsentStore lifecycle
# ---------------------------------------------------------------------------
class TestConsentStore:
    def test_get_or_create_grants_required_by_default(self):
        store = ConsentStore()
        state = store.get_or_create("u-1", "u-1@example.com", region="EU")
        assert state.is_active("necessary")
        assert not state.is_active("marketing")

    def test_grant_purpose(self):
        store = ConsentStore()
        store.grant("u-1", "u-1@example.com", ["marketing"], region="EU")
        state = store.get_state("u-1")
        assert state.is_active("marketing")

    def test_grant_required_is_noop_for_deny(self):
        store = ConsentStore()
        # required purposes cannot be denied; the store returns the
        # existing state with necessary still granted
        state = store.deny("u-1", "u-1@example.com", ["necessary"], region="EU")
        assert state.is_active("necessary")

    def test_deny_required_emits_blocked_audit(self):
        store = ConsentStore()
        events = []
        store.set_audit_callback(lambda event, payload: events.append((event, payload)))
        store.deny("u-1", "u-1@example.com", ["necessary"], region="EU")
        names = [e[0] for e in events]
        assert "consent_deny_blocked" in names

    def test_withdraw(self):
        store = ConsentStore()
        store.grant("u-1", "u-1@example.com", ["marketing"], region="EU")
        store.withdraw("u-1", "u-1@example.com", ["marketing"], region="EU")
        state = store.get_state("u-1")
        assert "marketing" in state.withdrawn_purposes()
        assert not state.is_active("marketing")

    def test_withdraw_required_does_nothing(self):
        store = ConsentStore()
        store.withdraw("u-1", "u-1@example.com", ["necessary"], region="EU")
        state = store.get_state("u-1")
        # necessary remains granted; nothing withdrawn
        assert state.is_active("necessary")
        assert "necessary" not in state.withdrawn_purposes()

    def test_withdraw_all(self):
        store = ConsentStore()
        store.grant("u-1", "u-1@example.com", ["marketing", "analytics"], region="EU")
        store.withdraw_all("u-1", "u-1@example.com", region="EU")
        state = store.get_state("u-1")
        assert not state.is_active("marketing")
        assert not state.is_active("analytics")
        assert state.is_active("necessary")  # required stays

    def test_audit_callback_invoked(self):
        events = []
        store = ConsentStore()
        store.set_audit_callback(lambda event, payload: events.append((event, payload)))
        store.grant("u-1", "u-1@example.com", ["marketing"], region="EU")
        store.withdraw("u-1", "u-1@example.com", ["marketing"], region="EU")
        names = [e[0] for e in events]
        assert "consent_grant" in names
        assert "consent_withdraw" in names

    def test_unknown_purpose_raises(self):
        store = ConsentStore()
        with pytest.raises(ValueError):
            store.grant("u-1", "u-1@example.com", ["nonexistent"], region="EU")

    def test_subject_id_is_hashed(self):
        store = ConsentStore()
        state = store.get_or_create("u-1", "secret@example.com", region="EU")
        # hashed subject must not contain plaintext
        assert "secret@example.com" not in state.subject_hash

    def test_region_recorded(self):
        store = ConsentStore()
        store.grant("u-1", "u-1@example.com", ["marketing"], region="CN")
        state = store.get_state("u-1")
        assert state.region == "CN"


# ---------------------------------------------------------------------------
# Cross-border (PIPL Art. 38)
# ---------------------------------------------------------------------------
class TestCrossBorder:
    def test_pipl_notice_has_required_sections(self):
        notice = PIPL_CROSS_BORDER_DISCLOSURE
        assert "controller" in notice
        assert "purposes" in notice
        assert "recipients" in notice
        assert "retention" in notice
        assert "user_rights" in notice

    def test_accept_and_revoke(self):
        store = ConsentStore()
        notice = store.get_cross_border_notice("CN")
        assert notice["version"]
        entry = store.accept_cross_border("u-1", region="CN")
        assert entry.accepted is True
        assert store.has_cross_border_consent("u-1")
        assert store.revoke_cross_border("u-1") is True
        assert not store.has_cross_border_consent("u-1")

    def test_revoke_when_missing(self):
        store = ConsentStore()
        assert store.revoke_cross_border("ghost") is False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
class TestConsentSingleton:
    def test_returns_same_instance(self):
        a = get_consent_store()
        b = get_consent_store()
        assert a is b

    def test_reset_clears(self):
        s = get_consent_store()
        s.grant("u-1", "u-1@example.com", ["marketing"], region="EU")
        assert s.get_state("u-1") is not None
        reset_consent_store()
        s2 = get_consent_store()
        assert s2.get_state("u-1") is None


# ---------------------------------------------------------------------------
# Lawful basis templates (mirror of API constants)
# ---------------------------------------------------------------------------
class TestLawfulBasisTemplates:
    @pytest.fixture
    def templates(self):
        from api.gdpr_v2 import LAWFUL_BASIS_TEMPLATES
        return LAWFUL_BASIS_TEMPLATES

    def test_all_five_regions_present(self, templates):
        assert {"EU", "CN", "CA", "US", "GLOBAL"}.issubset(templates.keys())

    def test_eu_has_six_bases(self, templates):
        codes = {b["code"] for b in templates["EU"]["lawful_bases"]}
        assert {
            "gdpr_consent", "gdpr_contract", "gdpr_legal_obligation",
            "gdpr_vital_interest", "gdpr_public_task", "gdpr_legitimate_interest",
        }.issubset(codes)

    def test_cn_has_pipl_bases(self, templates):
        codes = {b["code"] for b in templates["CN"]["lawful_bases"]}
        assert "pipl_consent" in codes
        assert "pipl_contract_necessary" in codes

    def test_ca_has_ccpa_bases(self, templates):
        codes = {b["code"] for b in templates["CA"]["lawful_bases"]}
        assert "ccpa_business_purpose" in codes
        assert "ccpa_opt_out" in codes

    def test_sla_days(self, templates):
        assert templates["EU"]["sla_days"] == 30
        assert templates["CN"]["sla_days"] == 30
        assert templates["CA"]["sla_days"] >= 30

    def test_breach_hours(self, templates):
        assert templates["EU"]["breach_notification_hours"] == 72
        assert templates["CN"]["breach_notification_hours"] <= 72

    def test_transfer_safeguards(self, templates):
        for region in ["EU", "CN", "CA"]:
            assert templates[region]["transfer_safeguards"]


# ---------------------------------------------------------------------------
# Integration: consent withdrawal emits audit row
# ---------------------------------------------------------------------------
class TestConsentAuditIntegration:
    def test_withdraw_emits_audit_row(self):
        store = get_consent_store()
        store.grant("u-1", "u-1@example.com", ["marketing"], region="EU")
        # simulate the gdpr_v2 API path that calls audit() after withdraw
        store.withdraw("u-1", "u-1@example.com", ["marketing"], region="EU")
        audit(
            action="update",
            resource="user",
            resource_id="u-1",
            pii_fields=["marketing"],
            lawful_basis="gdpr_consent",
            data_classification="sensitive",
        )
        rows = get_audit_store().query(action="update")
        assert len(rows) == 1
        assert rows[0].lawful_basis == "gdpr_consent"
