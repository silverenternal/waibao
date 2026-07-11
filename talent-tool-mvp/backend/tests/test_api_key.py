"""T803 - API Key 单元测试."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from services.api_key import (
    KEY_PREFIX_LITERAL,
    KEY_TOTAL_LEN,
    VALID_SCOPES,
    GeneratedKey,
    InMemoryRateLimiter,
    RateLimitGuard,
    check_scope,
    generate_key,
    to_public,
    validate_scopes,
    verify_key,
)


# ---------------------------------------------------------------------------
# generate_key / verify_key
# ---------------------------------------------------------------------------


def test_key_format():
    g = generate_key("demo", organisation_id="org-1")
    assert isinstance(g, GeneratedKey)
    assert g.plaintext.startswith(KEY_PREFIX_LITERAL)
    assert len(g.plaintext) == KEY_TOTAL_LEN
    assert g.key_prefix == g.plaintext[:12]
    assert len(g.key_prefix) == 12


def test_keys_are_unique():
    a = generate_key("a", organisation_id="o")
    b = generate_key("b", organisation_id="o")
    assert a.plaintext != b.plaintext
    assert a.key_hash != b.key_hash


def test_verify_roundtrip():
    g = generate_key("demo", organisation_id="o")
    record = {
        "id": g.id,
        "organisation_id": "o",
        "key_hash": g.key_hash,
        "scopes": ["candidates:read"],
        "rate_limit_per_min": 60,
        "revoked_at": None,
        "expires_at": None,
    }
    v = verify_key(g.plaintext, record)
    assert v is not None
    assert v.organisation_id == "o"
    assert "candidates:read" in v.scopes


def test_verify_rejects_wrong():
    g = generate_key("demo", organisation_id="o")
    record = {
        "id": g.id,
        "organisation_id": "o",
        "key_hash": g.key_hash,
        "scopes": [],
        "rate_limit_per_min": 60,
    }
    assert verify_key("wb_live_WRONG", record) is None
    assert verify_key("", record) is None


def test_verify_rejects_revoked():
    g = generate_key("demo", organisation_id="o")
    record = {
        "id": g.id,
        "organisation_id": "o",
        "key_hash": g.key_hash,
        "scopes": [],
        "rate_limit_per_min": 60,
        "revoked_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    assert verify_key(g.plaintext, record) is None


def test_verify_rejects_expired():
    g = generate_key("demo", organisation_id="o")
    expired = (
        datetime.now(tz=timezone.utc)
        .replace(year=2000, month=1, day=1)
        .isoformat()
    )
    record = {
        "id": g.id,
        "organisation_id": "o",
        "key_hash": g.key_hash,
        "scopes": [],
        "rate_limit_per_min": 60,
        "expires_at": expired,
    }
    assert verify_key(g.plaintext, record) is None


# ---------------------------------------------------------------------------
# check_scope / validate_scopes
# ---------------------------------------------------------------------------


def test_check_scope_exact():
    from services.api_key import VerifiedKey

    v = VerifiedKey(
        id="x", organisation_id="o",
        scopes=["candidates:read"], rate_limit_per_min=10,
    )
    assert check_scope(v, "candidates:read") is True
    assert check_scope(v, "tickets:write") is False


def test_check_scope_wildcard():
    from services.api_key import VerifiedKey

    v = VerifiedKey(
        id="x", organisation_id="o",
        scopes=["*"], rate_limit_per_min=10,
    )
    assert check_scope(v, "candidates:read") is True
    assert check_scope(v, "tickets:write") is True


def test_validate_scopes():
    assert validate_scopes(["candidates:read", "tickets:write"]) == [
        "candidates:read",
        "tickets:write",
    ]
    with pytest.raises(ValueError):
        validate_scopes(["unknown:scope"])


def test_valid_scopes_constant_complete():
    expected = {
        "candidates:read",
        "candidates:write",
        "roles:read",
        "matches:write",
        "tickets:write",
    }
    assert expected == VALID_SCOPES


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_in_memory_rate_limit():
    rl = InMemoryRateLimiter()
    # 5 个 token,前 5 次 OK,第 6 次拒绝
    for _ in range(5):
        assert rl.allow("k1", 5) is True
    # 立即再请求一次,桶耗尽
    assert rl.allow("k1", 5) is False


@pytest.mark.asyncio
async def test_rate_limit_guard_memory():
    guard = RateLimitGuard(redis_client=None)
    for _ in range(3):
        assert await guard.allow("k1", 3) is True
    assert await guard.allow("k1", 3) is False


@pytest.mark.asyncio
async def test_rate_limit_guard_redis_fallback(monkeypatch):
    """无 Redis 时退化到内存."""
    guard = RateLimitGuard(redis_client=None)
    assert await guard.allow("k", 2) is True


# ---------------------------------------------------------------------------
# Plaintext 仅创建瞬间返回
# ---------------------------------------------------------------------------


def test_plaintext_only_in_generated():
    g = generate_key("x", organisation_id="o")
    out = to_public(
        {
            "id": g.id,
            "name": "x",
            "key_prefix": g.key_prefix,
            "scopes": [],
            "rate_limit_per_min": 60,
            "expires_at": None,
            "revoked_at": None,
            "last_used_at": None,
            "created_at": None,
        }
    )
    assert "plaintext" not in out
    assert "key_hash" not in out
    # 仅展示 prefix
    assert out["key_prefix"] == g.key_prefix
