"""Tests for the Feature Flag service (v6.0 T2103).

Covers:
- Hash bucket distribution (uniformity across 10k users at 50% rollout)
- Whitelist (user/org override) takes precedence over rollout
- Blacklist override forces the flag off
- Admin enabled=true + rollout>=100% means 全网生效
- Cache TTL behaviour (60s)
- Rollout progression: 10% -> 50% -> 100% does not exclude previously
  included users (monotonic inclusion is the standard contract)
- Audit log entries written on every mutation
- API endpoint surface (FastAPI route smoke)
"""

from __future__ import annotations

import json
import time
from collections import Counter
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.platform import feature_flag as ff
from services.platform.feature_flag import (
    CACHE_TTL_S,
    FeatureFlag,
    FlagOverride,
    _bucket,
    _decide,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_for_tests()
    yield
    reset_for_tests()


# ---------------------------------------------------------------------------
# Hash bucket — distribution uniformity
# ---------------------------------------------------------------------------

def test_bucket_is_deterministic():
    a = _bucket("user-1", "realtime_voice")
    b = _bucket("user-1", "realtime_voice")
    assert a == b
    assert 0 <= a < 100


def test_bucket_differs_for_different_users():
    buckets = {_bucket(f"user-{i}", "ai_interview") for i in range(200)}
    # Collisions are allowed; we just want meaningful spread across buckets.
    assert len(buckets) >= 60


def test_bucket_distribution_uniform_at_50_percent():
    """Across 10k synthetic users, ~50% should fall into the rollout."""
    n = 10_000
    included = sum(1 for i in range(n) if _bucket(f"u{i}", "ff") < 50)
    ratio = included / n
    # 100k samples worth of distribution: tolerance +/- 2%
    assert 0.48 <= ratio <= 0.52, f"expected ~50%, got {ratio:.3f}"


def test_bucket_distribution_uniform_at_10_percent():
    n = 10_000
    included = sum(1 for i in range(n) if _bucket(f"u{i}", "ff") < 10)
    ratio = included / n
    assert 0.085 <= ratio <= 0.115


def test_bucket_distribution_uniform_at_100_percent():
    n = 1000
    included = sum(1 for i in range(n) if _bucket(f"u{i}", "ff") < 100)
    assert included == n


def test_bucket_distribution_uniform_at_0_percent():
    n = 1000
    included = sum(1 for i in range(n) if _bucket(f"u{i}", "ff") < 0)
    assert included == 0


# ---------------------------------------------------------------------------
# CRUD + decision logic
# ---------------------------------------------------------------------------

def _flag(name="realtime_voice", rollout=0, enabled=False, rules=None):
    ff.upsert_flag({"name": name, "rollout_percent": rollout, "enabled": enabled,
                    "rules": rules or {}, "description": name})


def test_unknown_flag_defaults_to_off():
    assert ff.is_enabled("never_created") is False


def test_disabled_flag_is_off():
    _flag("realtime_voice", rollout=50, enabled=False)
    assert ff.is_enabled("realtime_voice", user_id="u1") is False


def test_enabled_full_rollout_means_full_network():
    _flag("realtime_voice", rollout=100, enabled=True)
    # Across many users, no user should be excluded.
    for i in range(200):
        assert ff.is_enabled("realtime_voice", user_id=f"u{i}") is True


def test_rollout_subset_is_decisioned_via_hash():
    _flag("ai_interview", rollout=10, enabled=False)
    # Ensure we get a mix of True / False (not all same).
    decisions = [ff.is_enabled("ai_interview", user_id=f"u{i}") for i in range(500)]
    assert any(decisions) and not all(decisions)


def test_rollout_10_to_50_to_100_monotonic_inclusion():
    """Standard contract: increasing rollout never excludes a previously included user."""
    _flag("new_matching_v3", rollout=10, enabled=False)
    included_at_10 = {f"u{i}" for i in range(5000) if ff.is_enabled("new_matching_v3", user_id=f"u{i}")}

    ff.upsert_flag({"name": "new_matching_v3", "rollout_percent": 50, "enabled": False})
    included_at_50 = {f"u{i}" for i in range(5000) if ff.is_enabled("new_matching_v3", user_id=f"u{i}")}

    ff.upsert_flag({"name": "new_matching_v3", "rollout_percent": 100, "enabled": False})
    included_at_100 = {f"u{i}" for i in range(5000) if ff.is_enabled("new_matching_v3", user_id=f"u{i}")}

    assert included_at_10.issubset(included_at_50)
    assert included_at_50.issubset(included_at_100)
    assert len(included_at_100) == 5000


def test_whitelist_user_override_wins_over_rollout():
    _flag("video_resume", rollout=0, enabled=False)
    # Force-on override
    ff.set_override({"flag_name": "video_resume", "user_id": "u-vip", "value": True, "reason": "vip"})
    assert ff.is_enabled("video_resume", user_id="u-vip") is True
    # Other users still off
    assert ff.is_enabled("video_resume", user_id="u-other") is False


def test_blacklist_user_override_wins_over_enabled_full():
    _flag("realtime_voice", rollout=100, enabled=True)
    ff.set_override({"flag_name": "realtime_voice", "user_id": "u-bad", "value": False,
                     "reason": "compliance review"})
    assert ff.is_enabled("realtime_voice", user_id="u-bad") is False
    # Other users still on
    assert ff.is_enabled("realtime_voice", user_id="u-other") is True


def test_org_override_takes_effect():
    _flag("ai_interview", rollout=0, enabled=False)
    ff.set_override({"flag_name": "ai_interview", "org_id": "org_partner_42", "value": True,
                     "reason": "pilot partner"})
    # Any user inside org_partner_42 should see the flag on.
    assert ff.is_enabled("ai_interview", user_id="anyone", org_id="org_partner_42") is True
    assert ff.is_enabled("ai_interview", user_id="anyone", org_id="org_other") is False


def test_user_override_beats_org_override():
    """User-level override has higher precedence than org-level override."""
    _flag("video_resume", rollout=0, enabled=False)
    ff.set_override({"flag_name": "video_resume", "org_id": "org_x", "value": True, "reason": ""})
    ff.set_override({"flag_name": "video_resume", "user_id": "u-inside-org-x", "value": False,
                     "reason": "individual block"})
    assert ff.is_enabled("video_resume", user_id="u-inside-org-x", org_id="org_x") is False
    assert ff.is_enabled("video_resume", user_id="u-other-inside-org-x", org_id="org_x") is True


def test_remove_override_restores_default():
    _flag("realtime_voice", rollout=100, enabled=True)
    ff.set_override({"flag_name": "realtime_voice", "user_id": "u-1", "value": False, "reason": ""})
    assert ff.is_enabled("realtime_voice", user_id="u-1") is False
    removed = ff.remove_override("realtime_voice", user_id="u-1")
    assert removed == 1
    assert ff.is_enabled("realtime_voice", user_id="u-1") is True


def test_set_override_replaces_existing_for_same_target():
    _flag("realtime_voice", rollout=0, enabled=False)
    ff.set_override({"flag_name": "realtime_voice", "user_id": "u1", "value": True, "reason": "v1"})
    ff.set_override({"flag_name": "realtime_voice", "user_id": "u1", "value": False, "reason": "v2"})
    overrides = ff.list_overrides("realtime_voice")
    assert len(overrides) == 1
    assert overrides[0]["value"] is False


# ---------------------------------------------------------------------------
# Rules (cohort / region)
# ---------------------------------------------------------------------------

def test_rule_orgs_whitelist():
    _flag("ablation_study", rollout=0, enabled=False, rules={"orgs": ["org_a", "org_b"]})
    assert ff.is_enabled("ablation_study", user_id="u1", org_id="org_a") is True
    assert ff.is_enabled("ablation_study", user_id="u1", org_id="org_c") is False


def test_rule_user_id_range():
    _flag("ablation_study", rollout=0, enabled=False,
          rules={"min_user_id": 1000, "max_user_id": 2000})
    assert ff.is_enabled("ablation_study", user_id="500") is False
    assert ff.is_enabled("ablation_study", user_id="1500") is True
    assert ff.is_enabled("ablation_study", user_id="3000") is False


def test_rule_max_user_id_excludes():
    _flag("ablation_study", rollout=0, enabled=False, rules={"max_user_id": 999})
    assert ff.is_enabled("ablation_study", user_id="5000") is False


# ---------------------------------------------------------------------------
# Decide endpoint payload
# ---------------------------------------------------------------------------

def test_decide_payload_includes_reason():
    _flag("realtime_voice", rollout=100, enabled=True)
    d = ff.decide("realtime_voice", user_id="u1")
    assert d["enabled"] is True
    assert d["rollout_percent"] == 100
    assert d["global_enabled"] is True


def test_decide_unknown_flag_returns_missing_reason():
    d = ff.decide("nonexistent", user_id="u1")
    assert d["enabled"] is False
    assert d["reason"] == "missing"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_decision_is_cached(monkeypatch):
    _flag("realtime_voice", rollout=100, enabled=True)
    # First call: populates cache.
    assert ff.is_enabled("realtime_voice", user_id="u1") is True
    # Re-call should hit cache; flag mutation that invalidates cache would
    # change the answer — prove the second call returns the cached value.
    from services.platform.feature_flag import _cache as cache
    # Set an explicit short-TTL value with the same key.
    cache.set("ff:realtime_voice:u=u1:o=", {"enabled": False}, ttl_s=60)
    # Even though the underlying flag is enabled, the cached decision wins.
    assert ff.is_enabled("realtime_voice", user_id="u1") is False


def test_invalidation_after_upsert():
    _flag("realtime_voice", rollout=0, enabled=False)
    assert ff.is_enabled("realtime_voice", user_id="u1") is False
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 100, "enabled": True})
    # upsert invalidates cache entries for that flag.
    assert ff.is_enabled("realtime_voice", user_id="u1") is True


def test_cache_ttl_is_60_seconds():
    assert CACHE_TTL_S == 60.0


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def test_audit_records_create():
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 10, "enabled": False},
                   actor="alice")
    rows = ff.audit_log(flag_name="realtime_voice")
    assert any(r["action"] == "create" and r["actor"] == "alice" for r in rows)


def test_audit_records_update_and_override():
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 10, "enabled": False})
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 50, "enabled": False},
                   actor="bob")
    ff.set_override({"flag_name": "realtime_voice", "user_id": "u1", "value": True,
                     "reason": "vip"}, actor="bob")
    rows = ff.audit_log(flag_name="realtime_voice")
    actions = [r["action"] for r in rows]
    assert "update" in actions
    assert "override_set" in actions


def test_audit_records_delete():
    ff.upsert_flag({"name": "ablation_study", "rollout_percent": 0, "enabled": False})
    ff.delete_flag("ablation_study", actor="alice")
    rows = ff.audit_log(flag_name="ablation_study")
    assert any(r["action"] == "delete" for r in rows)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_upsert_rejects_bad_rollout():
    with pytest.raises(ff.FeatureFlagError):
        ff.upsert_flag({"name": "bad", "rollout_percent": 150})


def test_upsert_requires_name():
    with pytest.raises(ff.FeatureFlagError):
        ff.upsert_flag({"rollout_percent": 10})


def test_set_override_requires_user_or_org():
    with pytest.raises(ff.FeatureFlagError):
        ff.set_override({"flag_name": "realtime_voice", "value": True})


# ---------------------------------------------------------------------------
# FastAPI route smoke
# ---------------------------------------------------------------------------

def test_admin_route_smoke():
    from main import app  # noqa: WPS433 — import here to avoid collection cost
    client = TestClient(app)
    # Need to seed a flag first because TestClient doesn't run startup hooks.
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 50, "enabled": False})

    r = client.get("/api/admin/feature-flags")
    assert r.status_code == 200
    assert any(f["name"] == "realtime_voice" for f in r.json())

    r = client.put("/api/admin/feature-flags/ai_interview",
                   json={"name": "ai_interview", "rollout_percent": 25, "enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    r = client.get("/api/admin/feature-flags/ai_interview/decide",
                   params={"user_id": "u1"})
    assert r.status_code == 200
    assert "enabled" in r.json()

    r = client.post("/api/admin/feature-flags/ai_interview/override",
                    json={"flag_name": "ai_interview", "user_id": "u-vip",
                          "value": True, "reason": "vip"})
    assert r.status_code == 200
    assert r.json()["value"] is True

    r = client.delete("/api/admin/feature-flags/ai_interview/override",
                      params={"user_id": "u-vip"})
    assert r.status_code == 200
    assert r.json()["removed"] == 1

    r = client.delete("/api/admin/feature-flags/ai_interview")
    assert r.status_code == 200


def test_admin_route_returns_404_for_missing_flag():
    from main import app  # noqa: WPS433
    client = TestClient(app)
    r = client.get("/api/admin/feature-flags/never_exists")
    assert r.status_code == 404


def test_admin_route_audit_endpoint():
    from main import app  # noqa: WPS433
    client = TestClient(app)
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 25, "enabled": False},
                   actor="alice")
    r = client.get("/api/admin/feature-flags/audit",
                   params={"flag_name": "realtime_voice"})
    assert r.status_code == 200
    rows = r.json()
    assert any(row["action"] in {"create", "update"} for row in rows)


# ---------------------------------------------------------------------------
# Bucket vs decision — sanity
# ---------------------------------------------------------------------------

def test_bucket_decide_uses_subject_or_org_id():
    """If neither user_id nor org_id supplied, rollout bucket is bypassed.
    The global ``enabled`` toggle still fires."""
    _flag("realtime_voice", rollout=50, enabled=False)
    # No subject — bucket step is skipped; default-off because enabled=False.
    assert ff.is_enabled("realtime_voice") is False
    # enabled=True with partial rollout but no subject — falls through to
    # the global enabled toggle and returns True. Operators rely on this
    # behaviour to "lift the gate" for cron / server-side callers.
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 50, "enabled": True})
    assert ff.is_enabled("realtime_voice") is True
    # With a subject, the rollout bucket applies.
    some_on = any(
        ff.is_enabled("realtime_voice", user_id=f"u{i}") for i in range(500)
    )
    some_off = any(
        not ff.is_enabled("realtime_voice", user_id=f"u{i}") for i in range(500)
    )
    assert some_on and some_off


def test_audit_log_returns_newest_first():
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 0, "enabled": False})
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 25, "enabled": False})
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 50, "enabled": False})
    rows = ff.audit_log(flag_name="realtime_voice")
    # The first row should be the most recent update (rollout=50).
    assert rows[0]["after"]["rollout_percent"] == 50


def test_list_flags_includes_seeded_flags():
    ff.upsert_flag({"name": "realtime_voice", "rollout_percent": 10, "enabled": False})
    ff.upsert_flag({"name": "ai_interview", "rollout_percent": 0, "enabled": False})
    names = {f["name"] for f in ff.list_flags()}
    assert {"realtime_voice", "ai_interview"}.issubset(names)