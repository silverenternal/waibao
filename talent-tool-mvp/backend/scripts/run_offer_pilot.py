"""Offer Pilot Runner — T1802.

跑 10 个真实候选人 Offer 数据,通过 offer_calculator + negotiation_advisor 全流程:
    1. calculate_total_comp
    2. compute_percentile + market_band
    3. generate_negotiation_script (5 场景化)
    4. 输出对比 + negotiation script

输出:
    backend/reports/offer_pilot_YYYY-MM-DD.json
    backend/reports/offer_pilot_summary.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.jobseeker.offer_calculator import (  # noqa: E402
    OfferInput,
    calculate_total_comp,
    compare_offers,
    get_market_band,
    compute_percentile,
)
from services.jobseeker.negotiation_advisor import (  # noqa: E402
    generate_negotiation_script,
)

logger = logging.getLogger("recruittech.scripts.offer_pilot")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"

# 5 个谈判场景
SCENARIO_PRESETS = {
    "scenario_a_below_p50": {
        "role_for_market": "backend_engineer",
        "scenario_name": "Below p50 — 市场分位偏低",
        "rationale": "候选人当前 offer 在市场 p50 以下,数据驱动的论点:market gap。",
    },
    "scenario_b_competing_offer": {
        "role_for_market": None,
        "scenario_name": "Compete — 多家 offer 互 match",
        "rationale": "候选人有 2-3 家 offer,要求 match 最高。",
    },
    "scenario_c_signing_bonus": {
        "role_for_market": None,
        "scenario_name": "Signing — 争取签字费",
        "rationale": "无签字费 → 抵消其他 offer 签字费或搬家成本。",
    },
    "scenario_d_equity_vesting": {
        "role_for_market": None,
        "scenario_name": "Equity — 调整 vesting/refresh",
        "rationale": "担心股票风险,争取 front-load 或 refresh。",
    },
    "scenario_e_walkaway": {
        "role_for_market": None,
        "scenario_name": "Walkaway — 走人底线",
        "rationale": "HR 反复压价,设置 firm floor + 48h 答复。",
    },
}


def _scenario_for_candidate(idx: int) -> str:
    return list(SCENARIO_PRESETS.keys())[idx % len(SCENARIO_PRESETS)]


def _to_offer_input(real: dict) -> OfferInput:
    return OfferInput(
        title=real["title"],
        company=real["company_alias"],
        role_level=real["level"],
        location=real["location"],
        currency=real["currency"],
        base_salary=real["base_salary"],
        bonus=0,
        bonus_target_pct=real.get("bonus_target_pct", 0),
        equity_value=real["equity_value"],
        equity_vesting_years=real["equity_vesting_years"],
        benefits=real["benefits"],
        signing_bonus=real.get("signing_bonus", 0),
        pto_days=real.get("pto_days", 0),
        extras={
            "candidate_name": "Anonymous Candidate",
            "candidate_phone": "+xx-xxx-xxxx-xxxx",
            "real_offer_id": real["id"],
        },
    )


def _load_real_offers() -> list[dict]:
    candidates = [
        Path(__file__).resolve().parents[1] / "data" / "real_offers.json",
        Path("/home/hugo/codes/waibao/talent-tool-mvp/backend/data/real_offers.json"),
    ]
    for p in candidates:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("offers", [])
    logger.warning("real_offers.json 不存在,使用 inline 兜底数据")
    return []


async def run_offer(real: dict, scenario: str) -> dict:
    offer = _to_offer_input(real)
    total = calculate_total_comp(offer)
    role = real["candidate_role"]
    band = get_market_band(role, real["location"], real["level"].capitalize()) or [25, 35, 50, 70, 100]
    # 把 total.gross 转 band 单位
    value_in_market_unit = total.gross / (10_000.0 if real["location"] == "CN" else 1000.0)
    percentile = compute_percentile(value_in_market_unit, band)
    market_data = {"band": band, "value_in_market_unit": value_in_market_unit, "percentile": percentile, "role": role}

    language = "en" if real["location"] == "US" else "zh"
    script = await generate_negotiation_script(
        offer,
        market_data=market_data,
        language=language,
    )
    return {
        "real_offer_id": real["id"],
        "candidate_role": role,
        "location": real["location"],
        "currency": real["currency"],
        "hr_expected_total": real.get("expected_total_cny"),
        "actual_monthly_net": real.get("actual_monthly_net_cny"),
        "calculator_result": {
            "gross": total.gross,
            "tax": total.tax,
            "social": total.social,
            "net": total.net,
            "monthly_net": total.monthly_net,
            "effective_tax_rate": total.effective_tax_rate,
            "total_comp": total.total_comp,
            "total_with_signing": total.total_with_signing,
            "equity_pv": total.equity_pv,
            "benefits": total.benefits,
        },
        "market": {
            "band": band,
            "percentile": percentile,
            "value_in_market_unit": value_in_market_unit,
        },
        "scenario": scenario,
        "scenario_meta": SCENARIO_PRESETS.get(scenario, {}),
        "negotiation": {
            "current_total": script.current_total,
            "target_total": script.target_total,
            "walkaway_threshold": script.walkaway_threshold,
            "overall_advice": script.overall_advice,
            "talking_points": script.talking_points,
            "email_template_excerpt": script.email_template[:300],
            "tactics": [
                {"title": t.title, "expected_uplift_pct": t.expected_uplift_pct, "risk": t.risk}
                for t in script.tactics
            ],
            "counter_examples": script.counter_examples,
            "next_steps": script.next_steps,
            "provider": script.provider,
        },
    }


async def run_all(offers: list[dict]) -> dict:
    if not offers:
        return {"task": "T1802 - offer pilot", "error": "no offers loaded"}
    results = []
    for i, o in enumerate(offers):
        scenario = _scenario_for_candidate(i)
        r = await run_offer(o, scenario)
        results.append(r)
        print(f"  ✓ {o['id']} {o['candidate_role']:22s} region={o['location']} scenario={scenario}")
    # 横向 compare (用前 5 个)
    compare_input = [_to_offer_input(o) for o in offers[:5]]
    cmp = compare_offers(compare_input)
    return {
        "task": "T1802 - offer pilot",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_offers": len(results),
        "scenarios_tested": list(SCENARIO_PRESETS.keys()),
        "results": results,
        "comparison_top5": {
            "best_by_total": cmp.best_by_total,
            "best_by_monthly_net": cmp.best_by_monthly_net,
            "rank": cmp.rank,
            "radar": cmp.radar,
            "market": cmp.market,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-json", type=str, default=None)
    p.add_argument("--output-md", type=str, default=None)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    offers = _load_real_offers()
    if args.limit:
        offers = offers[: args.limit]
    print(f"[offer-pilot] running {len(offers)} real offers...")
    out = asyncio.run(run_all(offers))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    json_path = Path(args.output_json or (REPORT_DIR / f"offer_pilot_{today}.json"))
    md_path = Path(args.output_md or (REPORT_DIR / f"offer_pilot_summary_{today}.md"))

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Markdown
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# T1802 - Offer Pilot 报告\n\n")
        f.write(f"生成时间: {out.get('generated_at')}\n\nOffer 数: {out.get('n_offers')}\n\n")
        f.write("## 各 Offer 计算 + 谈判摘要\n\n")
        f.write("| ID | 岗位 | 地区 | 总包(local) | 月到手 | 排名分位 | 场景 | 建议 (节选) |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for r in out.get("results", []):
            cr = r["calculator_result"]
            advice = (r["negotiation"]["overall_advice"] or "")[:60].replace("|", "/")
            f.write(
                f"| {r['real_offer_id']} | {r['candidate_role']} | {r['location']} | "
                f"{cr['total_comp']:.0f} {r['currency']} | {cr['monthly_net']:.0f} | "
                f"p{r['market']['percentile']} | {r['scenario']} | {advice} |\n"
            )
        if "comparison_top5" in out:
            cmp = out["comparison_top5"]
            f.write("\n## Top-5 横向对比\n\n")
            f.write(f"- **最大总包**: {cmp['best_by_total']}\n- **最高月到手**: {cmp['best_by_monthly_net']}\n\n")
            f.write("### Rank\n\n")
            for r in cmp.get("rank", []):
                f.write(
                    f"{r['rank']}. {r['title']} — {r['currency']} {r['total_comp_local']:.0f} "
                    f"(≈CNY {r['total_comp_cny_equiv']:.0f})\n"
                )
    print(f"\n[offer-pilot] JSON: {json_path}")
    print(f"[offer-pilot] MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
