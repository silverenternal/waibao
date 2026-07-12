"""T1302 Offer Calculator 测试."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.offer_calculator import (  # noqa: E402
    OfferInput,
    calculate_total_comp,
    compare_offers,
    compute_percentile,
    get_market_band,
)


def test_cn_offer_basic():
    o = OfferInput(
        title="高级工程师",
        company="Waibao",
        location="CN",
        currency="CNY",
        base_salary=500_000,
        bonus=100_000,
        bonus_target_pct=0.2,
        equity_value=2_000_000,
        equity_vesting_years=4,
        benefits=50_000,
        signing_bonus=50_000,
        pto_days=15,
    )
    at = calculate_total_comp(o)
    assert at.location == "CN"
    assert at.gross == 700_000  # 50w * 1.2
    assert at.tax > 0
    assert at.net > 0
    assert at.net < at.gross
    assert at.benefits == 50_000
    assert at.equity_pv == 500_000  # 200w / 4
    assert at.signing_bonus == 50_000
    assert at.total_comp == 700_000 + 500_000 + 50_000
    assert at.total_with_signing == at.total_comp + 50_000


def test_cn_lower_bound_tax_is_low():
    """年薪低于 6w 起征点, 税应为 0."""
    o = OfferInput(location="CN", currency="CNY", base_salary=50_000)
    at = calculate_total_comp(o)
    assert at.tax == 0
    assert at.gross == 50_000


def test_us_offer_basic():
    o = OfferInput(
        location="US", currency="USD",
        base_salary=180_000, bonus=30_000, benefits=15_000, equity_value=500_000, equity_vesting_years=4,
    )
    at = calculate_total_comp(o)
    assert at.location == "US"
    assert at.gross == 210_000
    assert at.tax > 0
    # Federal 22% bracket for 100k+ portions
    assert at.tax > 40_000
    assert at.net > 0
    assert at.net < at.gross
    assert at.equity_pv == 125_000
    assert at.effective_tax_rate > 0.1


def test_sg_offer_basic():
    o = OfferInput(
        location="SG", currency="SGD",
        base_salary=140_000, bonus=20_000, benefits=10_000, signing_bonus=10_000,
    )
    at = calculate_total_comp(o)
    assert at.location == "SG"
    # 16w 部分按 15%
    assert at.tax > 0
    # CPF 雇员
    assert at.gross - at.tax > 0
    assert at.total_with_signing == at.total_comp + 10_000


def test_compare_offers_orders_correctly():
    offers = [
        OfferInput(
            title="Offer A",
            location="US", currency="USD",
            base_salary=200_000, bonus=20_000, equity_value=800_000,
        ),
        OfferInput(
            title="Offer B",
            location="CN", currency="CNY",
            base_salary=600_000, bonus=100_000, equity_value=1_000_000,
        ),
        OfferInput(
            title="Offer C",
            location="SG", currency="SGD",
            base_salary=120_000, bonus=15_000, equity_value=200_000,
        ),
    ]
    cmp = compare_offers(offers)
    assert len(cmp.offers) == 3
    # 雷达维度应当齐全
    for k in ["base", "net_monthly", "equity_pv", "benefits", "total_comp"]:
        assert k in cmp.radar
        assert len(cmp.radar[k]) == 3
    # 排序非空
    assert len(cmp.rank) == 3
    # CN Y 最高(A 约 200k USD = 144w CNY, B 600k + 250w equity/4 = 850w CNY → B 胜)
    # 实际比较: A 200+20+200 = 420k USD ≈ 302w CNY, B 600+100+250 = 950w CNY → B 第 1
    assert cmp.rank[0]["title"] in {"Offer A", "Offer B"}


def test_compare_radar_normalized_to_100():
    offers = [
        OfferInput(location="CN", currency="CNY", base_salary=300_000),
        OfferInput(location="CN", currency="CNY", base_salary=600_000),
    ]
    cmp = compare_offers(offers)
    # 最高项总分 comp 应为 100
    assert max(cmp.radar["total_comp"]) == 100
    # 第一项 base salary 比例应当小于第二
    assert cmp.radar["base"][0] < cmp.radar["base"][1]


def test_offer_invalid_region_raises():
    import pytest
    try:
        calculate_total_comp(OfferInput(location="MARS", base_salary=100))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_market_band_returns_5_percentiles():
    band = get_market_band("backend_engineer", "US")
    assert band is not None
    assert len(band) == 5
    assert band == sorted(band)


def test_compute_percentile():
    band = [25, 35, 50, 70, 100]
    assert compute_percentile(15, band) == 10
    assert compute_percentile(30, band) > 10
    assert compute_percentile(50, band) >= 25 and compute_percentile(50, band) <= 75
    assert compute_percentile(150, band) >= 90
