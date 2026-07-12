"""T1302 Negotiation Advisor 测试."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.negotiation_advisor import (  # noqa: E402
    generate_negotiation_script,
)
from services.offer_calculator import OfferInput  # noqa: E402


def _mock_offer() -> OfferInput:
    return OfferInput(
        title="Senior BE",
        company="Waibao",
        location="CN",
        currency="CNY",
        base_salary=400_000,
        bonus=80_000,
        bonus_target_pct=0.2,
        equity_value=800_000,
        equity_vesting_years=4,
        benefits=30_000,
        signing_bonus=0,
        pto_days=10,
        extras={"candidate_name": "张三", "candidate_phone": "+86-138-0000-0000"},
    )


def test_negotiation_basic_mock():
    o = _mock_offer()
    script = asyncio.run(
        generate_negotiation_script(o, market_data={"role": "backend_engineer"})
    )
    assert script.offer_title == "Senior BE"
    assert script.region == "CN"
    assert script.currency == "CNY"
    assert script.target_total > script.current_total
    assert script.walkaway_threshold <= script.current_total
    assert script.percent_in_market >= 0 and script.percent_in_market <= 100
    assert 3 <= len(script.talking_points) <= 10
    assert script.email_template
    assert len(script.counter_examples) >= 1
    assert len(script.tactics) >= 1
    assert script.provider in {"mock", "openai", "anthropic", "deepseek", "zhipu", "tongyi", "moonshot"}


def test_negotiation_suggests_signing_bonus_when_zero():
    o = _mock_offer()  # signing_bonus == 0
    script = asyncio.run(generate_negotiation_script(o))
    has_signing = any("签字费" in t.title or "signing" in t.title.lower() for t in script.tactics)
    assert has_signing


def test_negotiation_suggests_pto_when_low():
    o = _mock_offer()  # pto_days = 10 < 15
    script = asyncio.run(generate_negotiation_script(o))
    has_pto = any("年假" in t.title or "PTO" in t.title or "休假" in t.title for t in script.tactics)
    assert has_pto


def test_negotiation_below_p50_asks_bigger_uplift():
    # 低于 p50 → 应该要 15%
    o = _mock_offer()
    script = asyncio.run(
        generate_negotiation_script(o, market_data={"percentile": 30, "band": [25, 35, 50, 70, 100]})
    )
    # market band 给出; script 应当识别到 30 落在 below_p50 分支
    assert script.percent_in_market == 30
    # 至少存在一条 uplift >= 0.10 的论点
    assert any(t.expected_uplift_pct >= 0.10 for t in script.tactics)


def test_negotiation_above_p90_asks_smaller_uplift():
    o = _mock_offer()
    script = asyncio.run(
        generate_negotiation_script(o, market_data={"percentile": 95, "band": [25, 35, 50, 70, 100]})
    )
    # 最高 uplift 应当在 0.03 - 0.05 区间内
    max_uplift = max((t.expected_uplift_pct for t in script.tactics), default=0)
    assert max_uplift <= 0.06


def test_negotiation_email_contains_target():
    o = _mock_offer()
    script = asyncio.run(generate_negotiation_script(o))
    assert str(script.target_total)[:5] in script.email_template or "{target}" not in script.email_template


def test_negotiation_counter_examples_format():
    o = _mock_offer()
    script = asyncio.run(generate_negotiation_script(o))
    for ex in script.counter_examples:
        assert "HR:" in ex
        assert "你:" in ex
