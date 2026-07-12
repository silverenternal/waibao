"""PII 字段加密服务测试 — T1202."""
from __future__ import annotations

import pytest

from services.pii_field_encryption import (
    FieldSpec,
    PIIFieldService,
    PII_FIELDS,
    decrypt_dict,
    encrypt_dict,
    get_pii_field_service,
    list_pii_fields,
    pii_encrypted_fields,
    resolve_canonical,
)


@pytest.fixture(autouse=True)
def reset_service():
    import services.pii_field_encryption as mod

    mod._singleton = PIIFieldService()
    yield


def test_field_registry_canonical_fields():
    assert "full_name" in PII_FIELDS
    assert "email" in PII_FIELDS
    assert "phone" in PII_FIELDS
    assert "id_card" in PII_FIELDS
    assert "address" in PII_FIELDS
    assert "bank_card" in PII_FIELDS
    assert "resume_text" in PII_FIELDS


def test_field_registry_aliases():
    spec = resolve_canonical("id_card_no")
    assert spec is not None
    assert spec.name in ("id_card", "id_card_no")


def test_list_pii_fields_by_level():
    fields = list_pii_fields(level_min=4)
    assert "id_card" in fields
    assert "email" not in fields  # L2


def test_encrypt_decrypt_roundtrip():
    svc = get_pii_field_service()
    token = svc.encrypt_pii("alice@example.com", "email")
    assert token != "alice@example.com"
    assert svc.decrypt_pii(token, "email") == "alice@example.com"


def test_encrypt_pii_unknown_field_raises():
    svc = get_pii_field_service()
    with pytest.raises(ValueError):
        svc.encrypt_pii("secret", "nonexistent_field")


def test_encrypt_pii_none_returns_none():
    svc = get_pii_field_service()
    assert svc.encrypt_pii(None, "email") is None  # type: ignore[arg-type]


def test_decrypt_pii_none_returns_none():
    svc = get_pii_field_service()
    assert svc.decrypt_pii(None, "email") is None  # type: ignore[arg-type]


def test_encrypt_dict_basic_fields():
    data = {"full_name": "Alice", "email": "a@x.com", "headline": "Engineer"}
    enc = encrypt_dict(data)
    assert enc["full_name"] != "Alice"
    assert enc["email"] != "a@x.com"
    assert enc["headline"] == "Engineer"  # L1 不加密


def test_decrypt_dict_roundtrip():
    data = {"full_name": "Alice", "email": "a@x.com"}
    enc = encrypt_dict(data)
    dec = decrypt_dict(enc)
    assert dec["full_name"] == "Alice"
    assert dec["email"] == "a@x.com"


def test_decrypt_dict_skips_plaintext():
    """解密时若值不是密文,静默跳过 — 兼容未加密旧数据."""
    data = {"full_name": "AlreadyPlain", "email": "plain@x.com"}
    dec = decrypt_dict(data)
    assert dec == data


def test_id_card_high_level():
    """L4 字段必须加密."""
    svc = get_pii_field_service()
    token = svc.encrypt_pii("110101199003078888", "id_card")
    assert token != "110101199003078888"
    assert svc.decrypt_pii(token, "id_card") == "110101199003078888"


def test_audit_logged_on_encrypt():
    from compliance.audit import get_audit_logger

    audit = get_audit_logger()
    before = len(audit.query(action="pii_encrypt", limit=200))
    svc = get_pii_field_service()
    svc.encrypt_pii("Alice", "full_name")
    after = len(audit.query(action="pii_encrypt", limit=200))
    assert after >= before + 1


def test_audit_logged_on_decrypt():
    from compliance.audit import get_audit_logger

    audit = get_audit_logger()
    svc = get_pii_field_service()
    token = svc.encrypt_pii("Alice", "full_name")
    before = len(audit.query(action="pii_decrypt", limit=200))
    svc.decrypt_pii(token, "full_name")
    after = len(audit.query(action="pii_decrypt", limit=200))
    assert after >= before + 1


def test_decorator_async_decrypts_result():
    """装饰器:async 函数返回值自动解密."""
    svc = get_pii_field_service()
    enc_name = svc.encrypt_pii("Alice", "full_name")
    enc_email = svc.encrypt_pii("a@x.com", "email")

    @pii_encrypted_fields(["full_name", "email"])
    async def fetch_user() -> dict:
        return {"full_name": enc_name, "email": enc_email, "id": 1}

    import asyncio
    result = asyncio.run(fetch_user())
    assert result["full_name"] == "Alice"
    assert result["email"] == "a@x.com"
    assert result["id"] == 1


def test_decorator_sync_encrypts_kwargs():
    @pii_encrypted_fields(["full_name"], direction="encrypt")
    def save_user(data: dict) -> dict:
        return {"saved": True, "data": data}

    result = save_user(data={"full_name": "Bob", "email": "b@x.com"})
    assert result["data"]["full_name"] != "Bob"
    assert result["data"]["email"] == "b@x.com"  # email 不在 fields 里,未加密


def test_audit_disable():
    svc = PIIFieldService()
    svc.enable_audit(False)
    from compliance.audit import get_audit_logger

    audit = get_audit_logger()
    before = len(audit.query(action="pii_encrypt", limit=200))
    svc.encrypt_pii("Quiet", "full_name")
    after = len(audit.query(action="pii_encrypt", limit=200))
    assert after == before