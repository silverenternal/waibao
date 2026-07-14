"""T5015 — Field-level PII encryption coverage tests (KMS-backed).

Verifies the pii_encrypt registry covers every PII-bearing table required
by the task and that encrypt/decrypt round-trips with the versioned
envelope format.
"""
from __future__ import annotations

import pytest

from compliance.kms import KMSManager, reset_kms
from compliance.pii_encrypt import (
    ENVELOPE_VERSION,
    PII_TABLE_FIELDS,
    PIIEncryptService,
    fields_for,
    get_pii_service,
    list_pii_tables,
    reset_pii_service,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_kms()
    reset_pii_service()
    yield
    reset_kms()
    reset_pii_service()


# ---------------------------------------------------------------------------
# Registry coverage — every table+field the task names must be present
# ---------------------------------------------------------------------------
REQUIRED_PII_FIELDS = {
    "users": {"email", "phone", "id_card"},
    "candidates": {"name", "email", "phone", "cv_text"},
    "journal": {"content"},
    "chat_messages": {"content"},
}


@pytest.mark.parametrize("table,required", sorted(REQUIRED_PII_FIELDS.items()))
def test_required_pii_table_fields_present(table, required):
    actual = set(PII_TABLE_FIELDS.get(table, ()))
    missing = required - actual
    assert not missing, f"{table} missing PII fields: {missing}"


def test_registry_covers_resume_and_offers():
    assert "raw_text" in PII_TABLE_FIELDS["resumes"]
    assert "salary" in PII_TABLE_FIELDS["offers"]


def test_list_pii_tables_sorted_and_nonempty():
    tables = list_pii_tables()
    assert tables == sorted(tables)
    assert len(tables) >= 8


def test_fields_for_unknown_table_empty():
    assert fields_for("does_not_exist") == ()


# ---------------------------------------------------------------------------
# Envelope encrypt/decrypt
# ---------------------------------------------------------------------------
def test_encrypt_value_produces_envelope():
    kms = KMSManager(provider="local")
    svc = PIIEncryptService(kms=kms)
    ct = svc.encrypt_value("alice@example.com")
    assert ct.startswith(f"{ENVELOPE_VERSION}:")
    # envelope carries the active DEK id
    dek_id = kms.current_dek().key_id
    assert f"{ENVELOPE_VERSION}:{dek_id}:" in ct


def test_encrypt_decrypt_roundtrip():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    ct = svc.encrypt_value("secret-pii-value")
    assert svc.decrypt_value(ct) == "secret-pii-value"


def test_decrypt_legacy_raw_fernet_token():
    # A raw Fernet token without envelope prefix should still decrypt.
    from cryptography.fernet import Fernet

    kms = KMSManager(provider="local")
    f = Fernet(kms.current_dek().key.encode() if isinstance(kms.current_dek().key, str) else kms.current_dek().key)
    raw = f.encrypt(b"legacy").decode("ascii")
    svc = PIIEncryptService(kms=kms)
    assert svc.decrypt_value(raw) == "legacy"


def test_encrypt_row_table_aware():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    row = {"id": 1, "email": "a@b.com", "phone": "13800000000", "id_card": "110101199001011234"}
    enc = svc.encrypt_row("users", row)
    assert enc["id"] == 1  # non-PII untouched
    assert enc["email"] != "a@b.com"
    assert enc["phone"] != "13800000000"
    assert enc["id_card"] != "110101199011234"[:8]
    dec = svc.decrypt_row("users", enc)
    assert dec["email"] == "a@b.com"
    assert dec["phone"] == "13800000000"
    assert dec["id_card"] == "110101199001011234"


def test_encrypt_row_idempotent_on_already_encrypted():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    row = {"email": "a@b.com"}
    enc1 = svc.encrypt_row("users", row)
    enc2 = svc.encrypt_row("users", enc1)  # should not double-encrypt
    assert enc1["email"] == enc2["email"]


def test_encrypt_rows_batch():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    rows = [{"content": "hello"}, {"content": "world"}]
    enc = svc.encrypt_rows("journal", rows)
    assert all(r["content"] != o["content"] for r, o in zip(enc, rows))
    dec = svc.decrypt_rows("journal", enc)
    assert [r["content"] for r in dec] == ["hello", "world"]


def test_encrypt_value_none_passthrough():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    assert svc.encrypt_value(None) is None  # type: ignore[arg-type]
    assert svc.encrypt_value("") == ""


def test_encrypt_value_rejects_non_string():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    with pytest.raises(TypeError):
        svc.encrypt_value(123)  # type: ignore[arg-type]


def test_coverage_report_shape():
    svc = PIIEncryptService(kms=KMSManager(provider="local"))
    rep = svc.coverage_report()
    assert rep["envelope_version"] == ENVELOPE_VERSION
    assert rep["provider"] == "local"
    assert rep["tables_covered"] >= 8
    assert rep["fields_covered"] >= 12
    assert "dek" in rep


def test_get_pii_service_singleton():
    a = get_pii_service()
    b = get_pii_service()
    assert a is b


def test_pii_encryptor_uses_kms_dek():
    """PIIEncryptor (the low-level class) must pull its key from KMS."""
    from compliance.encryption import PIIEncryptor

    kms = KMSManager(provider="local")
    enc = PIIEncryptor(kms=kms)
    tok = enc.encrypt("x")
    assert enc.decrypt(tok) == "x"
