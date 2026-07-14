"""T5015 — KMS abstraction + DEK management + 90-day rotation tests."""
from __future__ import annotations

import time

import pytest

from compliance.kms import (
    DEFAULT_DEK_TTL_DAYS,
    DEK,
    KMS_PROVIDERS,
    KMSManager,
    LocalKMSBackend,
    get_kms,
    reset_kms,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_kms()
    yield
    reset_kms()


# ---------------------------------------------------------------------------
# DEK model
# ---------------------------------------------------------------------------
def test_dek_age_and_expiry():
    d = DEK(key_id="k1", key="x", created_at=time.time() - 86400)
    assert d.age_days >= 1.0
    assert d.is_expired(ttl_days=90) is False
    assert d.is_expired(ttl_days=0) is True


def test_dek_public_dict_excludes_key():
    d = DEK(key_id="k1", key="supersecret", created_at=time.time(), wrapped_dek="w")
    pub = d.to_public_dict()
    assert "key" not in pub
    assert pub["key_id"] == "k1"
    assert pub["wrapped_dek"] == "w"


# ---------------------------------------------------------------------------
# LocalKMSBackend
# ---------------------------------------------------------------------------
def test_local_backend_generates_wrapped_dek():
    from cryptography.fernet import Fernet

    kek = Fernet.generate_key()
    backend = LocalKMSBackend(kek=kek)
    dek = backend.generate_dek()
    assert dek.key and dek.wrapped_dek
    assert dek.key != dek.wrapped_dek
    # unwrap must round-trip
    assert backend.unwrap_dek(dek.wrapped_dek) == dek.key


def test_local_backend_rejects_invalid_kek():
    with pytest.raises(ValueError):
        LocalKMSBackend(kek=b"not-a-fernet-key")


# ---------------------------------------------------------------------------
# KMSManager lifecycle + rotation
# ---------------------------------------------------------------------------
def test_kms_manager_has_active_dek():
    kms = KMSManager(provider="local")
    dek = kms.current_dek()
    assert isinstance(dek, DEK)
    assert dek.state == "active"


def test_kms_default_ttl_is_90_days():
    kms = KMSManager(provider="local")
    assert kms.ttl_days == DEFAULT_DEK_TTL_DAYS == 90


def test_kms_rotate_retires_previous_dek():
    kms = KMSManager(provider="local")
    old = kms.current_dek()
    new = kms.rotate()
    assert new.key_id != old.key_id
    # old dek must still be available for decrypt (retained)
    decryptable = kms.all_decrypt_deks()
    key_ids = {d.key_id for d in decryptable}
    assert old.key_id in key_ids
    assert new.key_id in key_ids


def test_kms_auto_rotates_on_expiry():
    kms = KMSManager(provider="local", ttl_days=90)
    first = kms.current_dek()
    # Backdate the active DEK so it appears expired.
    first.created_at = time.time() - (91 * 86400)
    rotated = kms.current_dek()
    assert rotated.key_id != first.key_id
    assert rotated.state == "active"


def test_kms_status_reports_expiry():
    kms = KMSManager(provider="local", ttl_days=30)
    status = kms.status()
    assert status["provider"] == "local"
    assert status["ttl_days"] == 30
    assert status["active_dek_id"] is not None
    assert status["active_dek_expires_in_days"] is not None
    assert status["next_rotation_due"] is not None


def test_kms_dek_for_decrypt_by_id():
    kms = KMSManager(provider="local")
    active = kms.current_dek()
    assert kms.dek_for_decrypt(active.key_id).key_id == active.key_id
    assert kms.dek_for_decrypt("nonexistent") is None


def test_kms_unknown_provider_falls_back_to_local():
    kms = KMSManager(provider="aws")  # boto3 not configured in test env
    assert kms.provider == "aws"
    # backend gracefully fell back to local
    assert kms.current_dek() is not None


def test_kms_providers_catalogue():
    assert set(KMS_PROVIDERS) == {"local", "aws", "vault", "aliyun"}


def test_get_kms_singleton():
    a = get_kms()
    b = get_kms()
    assert a is b


def test_kms_max_active_deks_bounds_retention():
    kms = KMSManager(provider="local", max_active_deks=2)
    kms.rotate()
    kms.rotate()
    kms.rotate()
    # active + at most (max_active - 1) retired = 2 total retained
    assert len(kms.all_decrypt_deks()) <= 2
