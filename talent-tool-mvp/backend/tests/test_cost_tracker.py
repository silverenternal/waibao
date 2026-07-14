"""v10.0 T5026 — Realtime cost tracker tests."""
from __future__ import annotations

import pytest

from services.platform.cost_tracker import (
    BudgetConfig,
    BudgetExceededError,
    BudgetTier,
    DEFAULT_PRICING,
    RealtimeCostTracker,
    TokenUsage,
    estimate_cost,
)


def test_estimate_cost_known_model():
    # gpt-4o: 2.5 / 1M in, 10 / 1M out
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert estimate_cost(usage, "gpt-4o") == pytest.approx(2.5 + 10.0)


def test_estimate_cost_unknown_model_is_zero():
    usage = TokenUsage(prompt_tokens=100, completion_tokens=100)
    assert estimate_cost(usage, "some-exotic-model") == 0.0


def test_record_accumulates_spend_and_tokens():
    t = RealtimeCostTracker()
    t.record("acme", provider="openai", model="gpt-4o",
             cost_usd=0.5, usage=TokenUsage(100, 50))
    t.record("acme", provider="openai", model="gpt-4o",
             cost_usd=0.3, usage=TokenUsage(10, 5))
    assert t.spent("acme") == pytest.approx(0.8)
    tokens = t.tokens("acme")
    assert tokens.prompt_tokens == 110
    assert tokens.completion_tokens == 55


def test_record_estimates_cost_from_usage_when_missing():
    t = RealtimeCostTracker()
    t.record("acme", provider="openai", model="gpt-4o",
             usage=TokenUsage(1_000_000, 0))
    assert t.spent("acme") == pytest.approx(2.5)


def test_budget_tier_transitions_fire_alert_once_per_transition():
    alerts = []
    t = RealtimeCostTracker(
        budgets={"acme": BudgetConfig(daily_budget_usd=10.0,
                                      warn_pct=0.5, throttle_pct=0.8)},
        alert_callback=lambda a: alerts.append(a),
    )
    # 5 USD -> 50% -> WARN (transition)
    t.record("acme", cost_usd=5.0)
    assert alerts[-1].tier == BudgetTier.WARN
    # +1 USD still WARN — no new alert
    n = len(alerts)
    t.record("acme", cost_usd=1.0)
    assert len(alerts) == n
    # to 9 USD -> 90% -> THROTTLE (transition)
    t.record("acme", cost_usd=3.0)
    assert alerts[-1].tier == BudgetTier.THROTTLE
    # to 11 -> BLOCK (transition)
    t.record("acme", cost_usd=2.0)
    assert alerts[-1].tier == BudgetTier.BLOCK


def test_block_tier_alerts_on_every_call():
    alerts = []
    t = RealtimeCostTracker(
        budgets={"acme": BudgetConfig(daily_budget_usd=1.0)},
        alert_callback=lambda a: alerts.append(a),
    )
    t.record("acme", cost_usd=2.0)  # BLOCK
    t.record("acme", cost_usd=1.0)  # still BLOCK -> alert again
    assert all(a.tier == BudgetTier.BLOCK for a in alerts)
    assert len(alerts) >= 2


def test_enforce_raises_on_block():
    t = RealtimeCostTracker(budgets={"acme": BudgetConfig(daily_budget_usd=1.0)})
    t.record("acme", cost_usd=2.0)
    with pytest.raises(BudgetExceededError):
        t.enforce("acme")


def test_enforce_ok_under_budget():
    t = RealtimeCostTracker(budgets={"acme": BudgetConfig(daily_budget_usd=100.0)})
    t.record("acme", cost_usd=1.0)
    t.enforce("acme")  # should not raise


def test_check_returns_current_tier():
    t = RealtimeCostTracker(budgets={"acme": BudgetConfig(daily_budget_usd=10.0,
                                                          warn_pct=0.5)})
    assert t.check("acme") == BudgetTier.OK
    t.record("acme", cost_usd=6.0)
    assert t.check("acme") == BudgetTier.WARN


def test_snapshot_structure():
    t = RealtimeCostTracker()
    t.record("acme", provider="openai", model="gpt-4o",
             cost_usd=1.0, usage=TokenUsage(10, 5))
    snap = t.snapshot("acme")
    assert snap["acme"]["spent_usd"] == 1.0
    assert snap["acme"]["tokens"]["total"] == 15
    assert "openai:gpt-4o" in snap["acme"]["breakdown"]


def test_snapshot_all_tenants():
    t = RealtimeCostTracker()
    t.record("a", cost_usd=1.0)
    t.record("b", cost_usd=2.0)
    snap = t.snapshot()
    assert set(snap) == {"a", "b"}


def test_ingest_event_from_providers_base():
    t = RealtimeCostTracker(budgets={"acme": BudgetConfig(daily_budget_usd=10.0)})
    alert = t.ingest_event({
        "tenant": "acme", "provider": "openai", "model": "gpt-4o",
        "cost_usd": 1.0, "prompt_tokens": 5, "completion_tokens": 5,
    })
    assert alert.tier == BudgetTier.OK
    assert t.tokens("acme").total == 10


def test_persistence_callback_invoked():
    persisted = []
    t = RealtimeCostTracker()
    t.set_persistence(lambda batch: persisted.extend(batch))
    t.record("acme", provider="openai", model="gpt-4o",
             cost_usd=0.1, usage=TokenUsage(1, 1))
    assert len(persisted) == 1
    assert persisted[0]["tenant_id"] == "acme"


def test_default_pricing_has_known_models():
    assert "gpt-4o" in DEFAULT_PRICING
    assert "claude-3-5-sonnet" in DEFAULT_PRICING
    assert "deepseek-chat" in DEFAULT_PRICING
