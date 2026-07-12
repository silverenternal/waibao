"""compliance.consent 单元测试."""
from __future__ import annotations

import pytest

from backend.compliance.consent import (
    ConsentBanner,
    ConsentDecision,
    ConsentService,
)


@pytest.fixture()
def service() -> ConsentService:
    return ConsentService()


def test_hash_subject_deterministic() -> None:
    a = ConsentService.hash_subject("user@example.com")
    b = ConsentService.hash_subject("user@example.com")
    assert a == b
    assert len(a) == 32
    # 不同 salt 产生不同哈希
    c = ConsentService.hash_subject("user@example.com", salt="other")
    assert a != c


def test_record_consent_creates_record(service: ConsentService) -> None:
    decisions = [
        ConsentDecision(category="necessary", granted=True, version="v1"),
        ConsentDecision(category="analytics", granted=False, version="v1"),
    ]
    record = service.record_consent(
        user_id="u1",
        subject_id="user@example.com",
        decisions=decisions,
        ip="10.0.0.1",
    )
    assert record.user_id == "u1"
    assert len(record.decisions) == 2
    assert record.withdrawn_at is None


def test_record_consent_merges_same_category(service: ConsentService) -> None:
    service.record_consent(
        user_id="u1",
        subject_id="x",
        decisions=[ConsentDecision(category="analytics", granted=False)],
    )
    updated = service.record_consent(
        user_id="u1",
        subject_id="x",
        decisions=[ConsentDecision(category="analytics", granted=True)],
    )
    analytics = [d for d in updated.decisions if d.category == "analytics"]
    assert len(analytics) == 1
    assert analytics[0].granted is True


def test_has_consent(service: ConsentService) -> None:
    service.record_consent(
        user_id="u1",
        subject_id="x",
        decisions=[ConsentDecision(category="marketing", granted=True)],
    )
    assert service.has_consent("u1", "marketing") is True
    assert service.has_consent("u1", "analytics") is False


def test_withdraw_all_and_single(service: ConsentService) -> None:
    service.record_consent(
        user_id="u1",
        subject_id="x",
        decisions=[
            ConsentDecision(category="marketing", granted=True),
            ConsentDecision(category="analytics", granted=True),
        ],
    )
    service.withdraw("u1", category="marketing")
    assert service.has_consent("u1", "marketing") is False
    assert service.has_consent("u1", "analytics") is True

    service.withdraw("u1")
    assert service.has_consent("u1", "analytics") is False
    rec = service.get_record("u1")
    assert rec is not None
    assert rec.withdrawn_at is not None


def test_build_banner_locales(service: ConsentService) -> None:
    en_banner = service.build_banner(locale="en", policy_version="v2")
    zh_banner = service.build_banner(locale="zh", policy_version="v2")
    assert isinstance(en_banner, ConsentBanner)
    assert isinstance(zh_banner, ConsentBanner)
    assert en_banner.policy_version == "v2"
    assert zh_banner.policy_version == "v2"
    codes = {c["code"] for c in en_banner.categories}
    assert "necessary" in codes
    assert "cross_border" in codes


def test_export_user_data(service: ConsentService) -> None:
    service.record_consent(
        user_id="u1",
        subject_id="x",
        decisions=[ConsentDecision(category="necessary", granted=True)],
    )
    payload = service.export_user_data("u1")
    assert payload["found"] is True
    assert payload["subject_id_hash"] == ConsentService.hash_subject("x")


def test_empty_decisions_rejected(service: ConsentService) -> None:
    with pytest.raises(ValueError):
        service.record_consent(user_id="u1", subject_id="x", decisions=[])