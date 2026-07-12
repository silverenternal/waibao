"""Offer Calculator — T1302.

支持三地区税务 + 福利折现 + 股权现值:

    calculate_total_comp(offer, region) -> AnnualTotal
    compare_offers(offers) -> Comparison (雷达图)

地区:
    - CN 中国大陆(个税 + 五险一金)
    - US 美国(Federal + State 含 SS/Medicare)
    - SG 新加坡(简化累进)

输入 offer 字段:
    base_salary       月薪/12 或年薪(取决于 currency_unit,默认 year)
    bonus             年终(现金,固定部分)
    bonus_target_pct  目标年终占比 (e.g. 0.2)
    equity_value      股权现值 (例如 vesting 4 年, 已 vest 部分;我们以现值 100% 计入)
    equity_vesting_years
    benefits          福利市价 (e.g. 商业保险/餐补/年假折现) - 直接相加
    signing_bonus     一次性
    location          CN / US / SG

输出 AnnualTotal:
    gross, tax, net, benefits_value, equity_pv, total, monthly_net
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger("recruittech.services.offer_calculator")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
VALID_REGIONS = {"CN", "US", "SG"}


@dataclass(slots=True)
class OfferInput:
    """一份 offer 的输入字段."""

    title: str = ""
    company: str = ""
    role_level: str = ""
    location: str = "CN"
    currency: str = "CNY"   # CNY / USD / SGD — 仅用于显示,内部统一折算为人民币等价值(CNY)
    base_salary: float = 0.0
    bonus: float = 0.0
    bonus_target_pct: float = 0.0
    equity_value: float = 0.0
    equity_vesting_years: int = 4
    benefits: float = 0.0
    signing_bonus: float = 0.0
    pto_days: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnnualTotal:
    """折算后的年薪详情."""

    location: str
    currency: str
    gross: float            # 应发(未税)
    tax: float              # 估算年度个税
    social: float           # 五险一金 / SS+Medicare 雇主部分
    net: float              # 税后到手
    benefits: float         # 福利折现
    equity_pv: float        # 股权按 vesting 折现(年化)
    bonus: float
    signing_bonus: float
    total_comp: float       # gross + benefits + equity + bonus
    total_with_signing: float
    monthly_net: float      # 月到手
    effective_tax_rate: float
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OfferComparison:
    """多 Offer 比较结果."""

    offers: list[AnnualTotal]
    best_by_total: str          # title of best (or "")
    best_by_monthly_net: str
    radar: dict[str, list[float]]  # {"base": [v1, v2], "net": [...], ...}
    rank: list[dict[str, Any]]     # 按 total_comp 排序
    market: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 汇率(简单常量 — 实际项目接汇率 API)
# ---------------------------------------------------------------------------
RATE_TO_CNY = {
    "CNY": 1.0,
    "USD": 7.20,   # 1 USD ≈ 7.2 CNY
    "SGD": 5.35,   # 1 SGD ≈ 5.35 CNY
    "HKD": 0.92,
    "EUR": 7.85,
}


# ---------------------------------------------------------------------------
# CN 税务模型(2024 综合所得累进表)
# 年应纳税所得额 X (元):
#   <=36000  3%
#   36000-144000 10%
#   144000-300000 20%
#   300000-420000 25%
#   420000-660000 30%
#   660000-960000 35%
#   >960000  45%
# 起征点 60000 / 年 (5000/月)
# 五险一金个人部分约 10.5% 缴费基数封顶 3 倍社平
# ---------------------------------------------------------------------------
def _cn_tax(gross_annual: float, social_personal: float) -> tuple[float, float]:
    """返回 (tax, social_personal)."""
    taxable = max(0.0, gross_annual - 60000 - social_personal)
    brackets = [
        (36000, 0.03, 0),
        (144000, 0.10, 2520),
        (300000, 0.20, 16920),
        (420000, 0.25, 31920),
        (660000, 0.30, 52920),
        (960000, 0.35, 85920),
        (float("inf"), 0.45, 181920),
    ]
    tax = 0.0
    for limit, rate, quick in brackets:
        if taxable <= limit:
            tax = taxable * rate - quick
            break
    social = min(gross_annual * 0.105, 30000 * 3 * 0.105 * 12)  # 简化:封顶 ≈ 37800/年
    return max(0.0, tax), social


# ---------------------------------------------------------------------------
# US 税务(Federal 2024 + FICA 7.65% + State 简化)
# 联邦累进:
#   <=11600 10%
#   11600-47150 12%
#   47150-100525 22%
#   100525-191950 24%
#   191950-243725 32%
#   243725-609350 35%
#   >609350 37%
# FICA: 6.2% SS (封顶 $168600) + 1.45% Medicare (无封顶) + 0.9% 高收入附加
# Standard deduction 2024 单人 $14600,夫妇 $29200;这里简化按单人
# State 取最高常见 9.3% (CA)
# ---------------------------------------------------------------------------
def _us_tax(gross_annual_usd: float) -> tuple[float, float]:
    deduction = 14600.0
    taxable_fed = max(0.0, gross_annual_usd - deduction)
    brackets = [
        (11600, 0.10, 0),
        (47150, 0.12, 1160),
        (100525, 0.22, 5426),
        (191950, 0.24, 17168.5),
        (243725, 0.32, 39110.5),
        (609350, 0.35, 55678.5),
        (float("inf"), 0.37, 183647.25),
    ]
    fed_tax = 0.0
    for limit, rate, quick in brackets:
        if taxable_fed <= limit:
            fed_tax = taxable_fed * rate - quick
            break
    # FICA
    social_security = min(gross_annual_usd, 168600.0) * 0.062
    medicare = gross_annual_usd * 0.0145 + max(0.0, gross_annual_usd - 200000.0) * 0.009
    state_tax = max(0.0, taxable_fed * 0.093)  # 简化
    total = fed_tax + social_security + medicare + state_tax
    fica_employer = social_security + gross_annual_usd * 0.0145  # 入 social 字段
    return max(0.0, total), fica_employer


# ---------------------------------------------------------------------------
# SG 税务(居民简化)
# 0-20000 0%
# 20000-30000 2%
# 30000-40000 3.5%
# 40000-80000 7%
# 80000-120000 11.5%
# 120000-160000 15%
# 160000-200000 18%
# 200000-240000 19%
# 240000-280000 19.5%
# 280000-320000 20%
# >320000 22%
# CPF 雇员 20%(封顶 月薪 SGD 8000 = OMR 8000+)
# ---------------------------------------------------------------------------
def _sg_tax(gross_annual_sgd: float) -> tuple[float, float]:
    brackets = [
        (20000, 0.0, 0),
        (30000, 0.02, 0),
        (40000, 0.035, 200),
        (80000, 0.07, 750),
        (120000, 0.115, 3550),
        (160000, 0.15, 8150),
        (200000, 0.18, 14150),
        (240000, 0.19, 21350),
        (280000, 0.195, 28950),
        (320000, 0.20, 36750),
        (float("inf"), 0.22, 44750),
    ]
    tax = 0.0
    for limit, rate, offset in brackets:
        if gross_annual_sgd <= limit:
            tax = gross_annual_sgd * rate - offset
            break
    # CPF 雇员 20%,封顶 OMR 8000/月 → 年 96000,封顶后部分为 0
    cpf_employee = min(gross_annual_sgd, 96000.0) * 0.20
    return max(0.0, tax), cpf_employee


# ---------------------------------------------------------------------------
# 计算函数
# ---------------------------------------------------------------------------
def _to_cny(amount: float, currency: str) -> float:
    rate = RATE_TO_CNY.get((currency or "CNY").upper(), 1.0)
    return round(amount * rate, 2)


def _annualize_bonus(bonus: float, pct: float, base: float) -> float:
    """处理固定 bonus + 目标 bonus."""
    return float(bonus or 0) + float(base) * float(pct or 0)


def _equity_pv(equity_value: float, years: int) -> float:
    """股权当前价值 -> 年化(平均到 vesting 年限)。"""
    years = max(1, years or 4)
    return round(float(equity_value or 0) / years, 2)


def calculate_total_comp(offer: OfferInput | dict[str, Any]) -> AnnualTotal:
    """核心计算:返回 AnnualTotal,所有数字统一按 offer.currency 显示。

    注:由于后台需要做全球薪资横向对比,实际数字按 local currency 显示,
    但附加了一个 cny_equivalent 字段会方便做雷达图横比。
    """
    if isinstance(offer, dict):
        offer = OfferInput(**{k: v for k, v in offer.items() if k in OfferInput.__annotations__})

    region = (offer.location or "CN").upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"unsupported region: {region}")
    currency = (offer.currency or ("CNY" if region == "CN" else "USD" if region == "US" else "SGD")).upper()

    base = float(offer.base_salary or 0)
    bonus_annual = _annualize_bonus(offer.bonus, offer.bonus_target_pct, base)
    equity_pv_local = _equity_pv(offer.equity_value, offer.equity_vesting_years)
    benefits = float(offer.benefits or 0)
    signing = float(offer.signing_bonus or 0)

    if region == "CN":
        social_personal = 0.0  # 计算函数返回的 soc 作为 social(= 雇主+个人都大致这个数)
        tax, social = _cn_tax(base + bonus_annual, 0)
        # 雇主侧五险一金另算,这里一并入 social 字段(便于"实发"估算)
        social_employer_extra = (base + bonus_annual) * 0.165
        social_total = social + social_employer_extra
        net = (base + bonus_annual) - tax - social
        gross = base + bonus_annual
        total_comp = gross + equity_pv_local + benefits
        total_with_signing = total_comp + signing
        notes = ["CN:综合所得 + 五险一金估算,雇主部分约 16.5% 折入"]
    elif region == "US":
        tax, fica_employer = _us_tax(base + bonus_annual)
        # employee FICA 已含在 tax
        net = (base + bonus_annual) - tax
        gross = base + bonus_annual
        social_total = fica_employer
        total_comp = gross + equity_pv_local + benefits
        total_with_signing = total_comp + signing
        notes = ["US:估算 2024 联邦 + State (CA 9.3%) + FICA,Standard Deduction 14600"]
    else:  # SG
        tax, cpf_employee = _sg_tax(base + bonus_annual)
        net = (base + bonus_annual) - tax - cpf_employee
        gross = base + bonus_annual
        social_total = (base + bonus_annual) * 0.17  # 雇主 CPF 17%
        total_comp = gross + equity_pv_local + benefits
        total_with_signing = total_comp + signing
        notes = ["SG:简化累进 + CPF 雇员 20%(封顶年 OMR 96000)"]

    effective_tax_rate = (tax / gross) if gross > 0 else 0.0

    return AnnualTotal(
        location=region,
        currency=currency,
        gross=round(gross, 2),
        tax=round(tax, 2),
        social=round(social_total, 2),
        net=round(net, 2),
        benefits=round(benefits, 2),
        equity_pv=round(equity_pv_local, 2),
        bonus=round(bonus_annual, 2),
        signing_bonus=round(signing, 2),
        total_comp=round(total_comp, 2),
        total_with_signing=round(total_with_signing, 2),
        monthly_net=round(net / 12.0, 2),
        effective_tax_rate=round(effective_tax_rate, 4),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 比较 + 雷达
# ---------------------------------------------------------------------------
def compare_offers(offers: list[dict[str, Any] | OfferInput]) -> OfferComparison:
    """横向对比多份 offer,返回雷达 + 排序。"""
    if not offers:
        return OfferComparison(offers=[], best_by_total="", best_by_monthly_net="", radar={}, rank=[])

    totals: list[AnnualTotal] = [calculate_total_comp(o) for o in offers]
    titles = [getattr(o, "title", "") for o in offers]

    # 统一折算到 CNY 当量,用于公平横向比较
    def to_cny(t: AnnualTotal) -> float:
        rate = RATE_TO_CNY.get(t.currency, 1.0)
        return t.total_comp * rate

    cny_vals = [to_cny(t) for t in totals]
    max_total = max(cny_vals) if cny_vals else 1.0
    max_net = max((t.monthly_net * RATE_TO_CNY.get(t.currency, 1.0) for t in totals), default=1.0)
    max_eq = max((t.equity_pv * RATE_TO_CNY.get(t.currency, 1.0) for t in totals), default=1.0)
    max_benefit = max((t.benefits * RATE_TO_CNY.get(t.currency, 1.0) for t in totals), default=1.0)
    max_gross = max((t.gross * RATE_TO_CNY.get(t.currency, 1.0) for t in totals), default=1.0)

    # 雷达图数据(0-100 标准化)
    radar = {
        "base": [round((t.gross * RATE_TO_CNY.get(t.currency, 1.0)) / max(max_gross, 1) * 100, 1) for t in totals],
        "net_monthly": [
            round((t.monthly_net * RATE_TO_CNY.get(t.currency, 1.0)) / max(max_net, 1) * 100, 1) for t in totals
        ],
        "equity_pv": [
            round((t.equity_pv * RATE_TO_CNY.get(t.currency, 1.0)) / max(max_eq, 1) * 100, 1) for t in totals
        ],
        "benefits": [
            round((t.benefits * RATE_TO_CNY.get(t.currency, 1.0)) / max(max_benefit, 1) * 100, 1) for t in totals
        ],
        "total_comp": [round((c / max(max_total, 1)) * 100, 1) for c in cny_vals],
    }

    # 排序(cny 当量)
    ranked_idx = sorted(range(len(totals)), key=lambda i: cny_vals[i], reverse=True)
    rank: list[dict[str, Any]] = []
    for rank_i, idx in enumerate(ranked_idx, start=1):
        rank.append(
            {
                "rank": rank_i,
                "title": titles[idx] or f"Offer {idx + 1}",
                "company": getattr(offers[idx], "company", ""),
                "location": totals[idx].location,
                "currency": totals[idx].currency,
                "total_comp_local": totals[idx].total_comp,
                "total_comp_cny_equiv": round(cny_vals[idx], 0),
                "monthly_net_local": totals[idx].monthly_net,
                "score_cny_equiv": cny_vals[idx],
            }
        )

    return OfferComparison(
        offers=totals,
        best_by_total=rank[0]["title"] if rank else "",
        best_by_monthly_net=max(
            ((getattr(o, "title", ""), t.monthly_net) for o, t in zip(offers, totals)),
            key=lambda kv: kv[1] * RATE_TO_CNY.get(totals[0].currency, 1.0),
        )[0] if offers else "",
        radar=radar,
        rank=rank,
        market={"rate_to_cny": RATE_TO_CNY, "total_offers": len(offers)},
    )


# ---------------------------------------------------------------------------
# market 薪资分位(简化的内置数据集;真实接 levels.fyi / 薪资 API)
# ---------------------------------------------------------------------------
MARKET_BANDS: dict[str, dict[str, list[int]]] = {
    "backend_engineer": {
        "CN_Senior": [25, 35, 50, 70, 100],   # p10 p25 p50 p75 p90 万元
        "US_Senior": [110, 145, 180, 220, 280],  # 千美元
        "SG_Senior": [80, 100, 130, 165, 210],  # 千 SGD
    },
    "frontend_engineer": {
        "CN_Senior": [22, 30, 42, 58, 80],
        "US_Senior": [100, 130, 165, 200, 250],
        "SG_Senior": [70, 90, 120, 150, 190],
    },
    "data_scientist": {
        "CN_Senior": [28, 38, 55, 78, 110],
        "US_Senior": [120, 155, 195, 240, 300],
        "SG_Senior": [85, 105, 140, 175, 220],
    },
    "product_manager": {
        "CN_Senior": [28, 40, 60, 90, 130],
        "US_Senior": [120, 150, 190, 240, 300],
        "SG_Senior": [90, 115, 150, 195, 250],
    },
}


def get_market_band(role: str, region: str, level: str = "Senior") -> list[int] | None:
    """获取某岗位 + 地区的分位区间 [p10, p25, p50, p75, p90] (单位为万元或千美元)。"""
    role_data = MARKET_BANDS.get(role) or MARKET_BANDS.get("backend_engineer") or {}
    key = f"{region.upper()}_{level.capitalize()}"
    return role_data.get(key) or list(role_data.values())[0] if role_data else None


def compute_percentile(value_cny_wan: float, band: list[int]) -> int:
    """根据 value(万元)和 band,估算 0-100 分位。"""
    if not band:
        return 50
    p10, p25, p50, p75, p90 = band
    if value_cny_wan <= p10:
        return 10
    if value_cny_wan <= p25:
        return 10 + int((value_cny_wan - p10) / (p25 - p10) * 15)
    if value_cny_wan <= p50:
        return 25 + int((value_cny_wan - p25) / (p50 - p25) * 25)
    if value_cny_wan <= p75:
        return 50 + int((value_cny_wan - p50) / (p75 - p50) * 25)
    if value_cny_wan <= p90:
        return 75 + int((value_cny_wan - p75) / (p90 - p75) * 15)
    return min(95, 90 + int((value_cny_wan - p90) / max(p90, 1) * 5))
