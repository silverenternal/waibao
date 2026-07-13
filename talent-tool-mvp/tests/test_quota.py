"""T2602 - Plan / quota tests.

Validates:
  * Default plan selection (free / pro / enterprise)
  * ``enforce_request`` returns True until the minute-bucket is exhausted
    and then False for the remainder of the window.
  * Different tenants do not share the bucket.
  * ``enforce_resource`` properly tracks ai_tokens / day counters.
  * The store can be reset between tests.
  * plan metadata surfaces reasonable defaults for a SaaS offer (Free/Pro/Ent).
"""
from __future__ import annotations

import time
import uuid

import pytest

from services.platform.quota import (
    DEFAULT_PLAN,
    PlanLimits,
    QuotaStore,
    enforce_request,
    enforce_resource,
    get_plan,
    get_quota_store,
    list_plans,
    reset_quota_store,
)


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

class TestPlans:
    def test_three_plans_defined(self):
        names = {p.name for p in list_plans()}
        assert {"free", "pro", "enterprise"}.issubset(names)

    def test_plan_hierarchy(self):
        free = get_plan("free")
        pro = get_plan("pro")
        ent = get_plan("enterprise")
        assert free.requests_per_minute < pro.requests_per_minute < ent.requests_per_minute
        assert free.ai_tokens_per_month < pro.ai_tokens_per_month < ent.ai_tokens_per_month
        assert free.storage_gb < pro.storage_gb < ent.storage_gb
        assert free.seats < pro.seats < ent.seats

    def test_unknown_plan_returns_free(self):
        assert get_plan("nope").name == "free"

    def test_default_plan_is_free(self):
        assert DEFAULT_PLAN == "free"

    def test_plan_dict_roundtrip(self):
        plan = get_plan("pro")
        d = plan.as_dict()
        assert d["name"] == "pro"
        assert d["requests_per_minute"] == 1000


# ---------------------------------------------------------------------------
# QuotaStore sliding window
# ---------------------------------------------------------------------------

class TestQuotaStore:
    def setup_method(self):
        reset_quota_store()
        self.store = get_quota_store()

    def test_first_n_requests_allowed(self):
        tid = uuid.uuid4()
        for _ in range(10):
            ok, remaining = self.store.incr_request(tid)
            assert ok is True
            assert remaining >= 0

    def test_minute_bucket_overflow_rejects(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="free"):
            # Free plan = 100/minute. Simulate 101 requests.
            self.store.reset()
            for _ in range(100):
                ok, _ = self.store.incr_request(tid)
                assert ok is True
            ok, remaining = self.store.incr_request(tid)
            assert ok is False
            assert remaining == 0

    def test_pro_plan_high_budget(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="pro"):
            # Pro = 1000/min. Burn 500; still allowed.
            for _ in range(500):
                ok, _ = self.store.incr_request(tid)
                assert ok is True

    def test_enterprise_plan_very_high(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="enterprise"):
            for _ in range(2000):
                ok, _ = self.store.incr_request(tid)
                assert ok is True

    def test_tenants_have_independent_buckets(self):
        from services.platform.tenant_context import with_tenant
        a, b = uuid.uuid4(), uuid.uuid4()
        with with_tenant(a, plan="free"):
            for _ in range(100):
                ok_a, _ = self.store.incr_request(a)
                assert ok_a is True
            ok_a, _ = self.store.incr_request(a)
            assert ok_a is False
        with with_tenant(b, plan="free"):
            for _ in range(50):
                ok_b, _ = self.store.incr_request(b)
                assert ok_b is True

    def test_reset_clears_state(self):
        tid = uuid.uuid4()
        for _ in range(50):
            self.store.incr_request(tid)
        self.store.reset()
        for _ in range(10):
            ok, _ = self.store.incr_request(tid)
            assert ok is True


# ---------------------------------------------------------------------------
# Resource counters
# ---------------------------------------------------------------------------

class TestResourceCounters:
    def setup_method(self):
        reset_quota_store()
        self.store = get_quota_store()

    def test_ai_tokens_track(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="pro"):
            ok, _ = self.store.incr_tokens(tid, delta=200_000)
            assert ok is True
            ok, _ = self.store.incr_tokens(tid, delta=2_000_000)
            assert ok is False

    def test_ai_tokens_default_plan_caps(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="free"):
            ok, _ = self.store.incr_tokens(tid, delta=200_000)
            assert ok is True           # free == 200k tokens
            ok, _ = self.store.incr_tokens(tid, delta=10_000)
            assert ok is False

    def test_day_counter(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="free"):
            for _ in range(20_000):
                ok, _ = self.store.incr_day(tid, limit=0)
                assert ok is True
            ok, _ = self.store.incr_day(tid, limit=0)
            assert ok is False

    def test_day_counter_override(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="enterprise"):
            for _ in range(100):
                ok, _ = self.store.incr_day(tid, limit=100)
                assert ok is True
            ok, _ = self.store.incr_day(tid, limit=100)
            assert ok is False


# ---------------------------------------------------------------------------
# enforce_* helpers
# ---------------------------------------------------------------------------

class TestEnforcementHelpers:
    def setup_method(self):
        reset_quota_store()

    def test_enforce_request_returns_bool(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="enterprise"):
            ok = enforce_request(tid)
            assert isinstance(ok, bool)
            assert ok is True

    def test_enforce_resource_unknown_allowed(self):
        """Unknown resource names fail open."""
        ok = enforce_resource(uuid.uuid4(), "vibes")
        assert ok is True

    def test_enforce_resource_ai_tokens(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="free"):
            ok = enforce_resource(tid, "ai_tokens", delta=200_000)
            assert ok is True
            ok = enforce_resource(tid, "ai_tokens", delta=1)
            assert ok is False

    def test_enforce_resource_day(self):
        from services.platform.tenant_context import with_tenant
        tid = uuid.uuid4()
        with with_tenant(tid, plan="free"):
            for _ in range(20_000):
                ok = enforce_resource(tid, "day")
                assert ok is True
            ok = enforce_resource(tid, "day")
            assert ok is False


# ---------------------------------------------------------------------------
# PlanLimits dataclass
# ---------------------------------------------------------------------------

class TestPlanLimitsDataclass:
    def test_construct(self):
        p = PlanLimits(
            name="x",
            requests_per_minute=10,
            requests_per_day=100,
            ai_tokens_per_month=1000,
            storage_gb=5,
            seats=2,
        )
        assert p.name == "x"
        assert p.as_dict()["requests_per_minute"] == 10

    def test_frozen(self):
        p = get_plan("pro")
        with pytest.raises(Exception):
            p.requests_per_minute = 1  # type: ignore[misc]
