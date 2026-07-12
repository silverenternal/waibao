"""Negotiation Advisor — T1302.

基于 LLM + 模板话术的薪资谈判策略生成。

    generate_negotiation_script(offer, market_data) -> Script
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from providers.llm.base import LLMProvider, Message
from providers.registry import get_llm_provider
from services.jobseeker.offer_calculator import (  # direct import — avoid circular via services.offer_calculator shim
    VALID_REGIONS,
    AnnualTotal,
    OfferInput,
    calculate_total_comp,
    compute_percentile,
    get_market_band,
)

logger = logging.getLogger("recruittech.services.negotiation_advisor")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class NegotiationTactic:
    """具体策略 / 论点."""

    title: str
    rationale: str
    expected_uplift_pct: float  # 期望 1-10% 涨幅
    risk: str  # low / medium / high


@dataclass(slots=True)
class NegotiationScript:
    """完整谈判脚本."""

    offer_title: str
    region: str
    currency: str
    current_total: float
    target_total: float
    percent_in_market: int          # 0-100 当前薪资分位
    market_band: list[int]
    overall_advice: str
    talking_points: list[str]      # 3-5 个核心论点
    email_template: str            # 邮件 / 微信话术
    counter_examples: list[str]    # 反例回应 (当 HR 用"预算紧/没先例"等)
    tactics: list[NegotiationTactic]
    walkaway_threshold: float      # 走人底线
    next_steps: list[str]
    provider: str = "mock"


# ---------------------------------------------------------------------------
# 启发式提升区间 / 论点(模板,真实由 LLM 润色)
# ---------------------------------------------------------------------------
_BASE_UPLIFT_PCT = {
    "below_p50": 0.15,   # 低于市场 p50,大胆要
    "p50_p75": 0.08,
    "p75_p90": 0.05,
    "above_p90": 0.03,
}


def _market_position(percentile: int) -> str:
    if percentile < 50:
        return "below_p50"
    if percentile < 75:
        return "p50_p75"
    if percentile < 90:
        return "p75_p90"
    return "above_p90"


def _heuristic_tactics(offer: OfferInput, total: AnnualTotal, percentile: int) -> list[NegotiationTactic]:
    pos = _market_position(percentile)
    base_uplift = _BASE_UPLIFT_PCT[pos]
    tactics: list[NegotiationTactic] = []

    # 论点 1: 市场分位 OR 竞争 offer
    if pos == "below_p50":
        tactics.append(
            NegotiationTactic(
                title="强调市场分位偏低",
                rationale=(
                    f"我当前 offer 在市场 p{percentile},显著低于同类岗位 p50。"
                    f"参考贵司同岗级别 / 类似城市的数据,期望上调 {round(base_uplift * 100)}%。"
                ),
                expected_uplift_pct=base_uplift,
                risk="low",
            )
        )
    tactics.append(
        NegotiationTactic(
            title="竞争优势:多 offer / 内部 counter",
            rationale="我有其他在流程中的 offer / 内部 offer,期望匹配最佳报价。",
            expected_uplift_pct=base_uplift if pos != "below_p50" else 0.05,
            risk="low",
        )
    )

    # 论点 2: 福利/股权
    if total.equity_pv < total.gross * 0.3:
        tactics.append(
            NegotiationTactic(
                title="股权补充现金缺口",
                rationale=(
                    "股权部分相对较短,如果现金包不能达成,可申请将部分股权前移 (front-load) "
                    "或拉长 vesting 缓冲风险。"
                ),
                expected_uplift_pct=0.03,
                risk="medium",
            )
        )

    # 论点 3: 签字费
    if offer.signing_bonus == 0:
        tactics.append(
            NegotiationTactic(
                title="争取 signing bonus",
                rationale="替换竞争对手的签字费 / 抵消现有 offer 的入职奖金门槛。",
                expected_uplift_pct=0.02,
                risk="low",
            )
        )

    # 论点 4: PTO / 远程
    if (offer.pto_days or 0) < 15:
        tactics.append(
            NegotiationTactic(
                title="休假与远程",
                rationale="争取 15-20 天年假 + 每周 1-2 天远程 + 灵活上班时间。",
                expected_uplift_pct=0.0,
                risk="low",
            )
        )

    return tactics


_EMAIL_TEMPLATE_CN = """\
尊敬的 {hr_name} {hr_title},

感谢贵司的 offer,整体架构和团队方向非常吸引我。基于一些务实因素(已获其他公司的竞争性 offer / 期望薪资对齐市场 p75 等),
希望在 {components} 上做一些调整,期望能再争取到 {target} 的总包(年度)。

如果现金包调整空间有限,也欢迎您用 {benefits} 等形式来补偿。
期待您的回复,方便我们尽快对齐。

谢谢!
{candidate_name}
{candidate_phone}"""

_EMAIL_TEMPLATE_EN = """\
Hi {hr_name},

Thank you again for the offer — the team, scope and product genuinely excite me.
I would like to revisit the compensation package based on competing offers and current market data (p75+).

Specifically, I'd appreciate if we could adjust {components} to bring the all-in total closer to {target}.

If cash is constrained, I'm open to alternative forms like {benefits}.

Looking forward to your thoughts so we can move forward together.

Best,
{candidate_name}
{candidate_phone}"""


def _heuristic_email(
    offer: OfferInput, total: AnnualTotal, target_total: float, *, language: str = "zh"
) -> str:
    use_en = (language or "zh").lower().startswith("en") or offer.location == "US"
    template = _EMAIL_TEMPLATE_EN if use_en else _EMAIL_TEMPLATE_CN
    components = ", ".join(["base salary", "bonus structure", "equity refresher"][:2]) + ("等" if not use_en else "")
    benefits = "signing bonus / extra PTO" if use_en else "签字费 / 额外年假 / 远程办公"
    return template.format(
        hr_name="Alex",
        hr_title="老师" if not use_en else "",
        components=components,
        target=f"{total.currency} {round(target_total, 0):,}",
        benefits=benefits,
        candidate_name=offer.extras.get("candidate_name", "候选人") if not use_en else offer.extras.get("candidate_name", "Candidate"),
        candidate_phone=offer.extras.get("candidate_phone", "+86-xxx-xxxx-xxxx"),
    )


_COUNTER_RESPONSES = [
    {
        "hr_says": "今年预算紧张,无法调整",
        "respond_cn": "理解预算周期。我可以接受 8-10% 上调 + 签字费,或明年 3 月按绩效重新评估包。",
        "respond_en": "Understood on the budget cycle. I'd accept a 8-10% bump plus signing bonus, "
        "or revisit in March at perf review.",
    },
    {
        "hr_says": "我们没有先例 / 超出 band",
        "respond_cn": "了解。可否给我一个明确的 band 数字?我可以围绕市场 p75 调整期望,而非简单按 fixed 上调。",
        "respond_en": "Understood. Could you share the band range so we can discuss in terms of market p75 "
        "rather than a fixed number?",
    },
    {
        "hr_says": "需要你点头入职才行",
        "respond_cn": "我们都需要确定性。我的底线是 {target},希望能在 48 小时内拿到反馈。",
        "respond_en": "We both need certainty on this. My floor is {target}; I can hold until 48h for feedback.",
    },
]


# ---------------------------------------------------------------------------
# LLM 增强版
# ---------------------------------------------------------------------------
async def generate_negotiation_script(
    offer: dict[str, Any] | OfferInput,
    *,
    market_data: dict[str, Any] | None = None,
    llm_provider: LLMProvider | None = None,
    language: str = "zh",
) -> NegotiationScript:
    """生成谈判脚本。

    Args:
        offer: 单个 OfferInput 或 dict
        market_data: 可选,自定义的市场数据 (含 band / percentile 等)
        llm_provider: 可选 LLM;为 None 时用模板
    """
    if isinstance(offer, dict):
        try:
            o = OfferInput(**{k: v for k, v in offer.items() if k in OfferInput.__annotations__})
        except Exception:
            o = OfferInput(base_salary=float(offer.get("base_salary", 0)),
                           location=offer.get("location", "CN"),
                           title=offer.get("title", ""),
                           company=offer.get("company", ""))
    else:
        o = offer

    region = (o.location or "CN").upper()
    currency = o.currency or ("CNY" if region == "CN" else "USD" if region == "US" else "SGD")
    total = calculate_total_comp(o)

    market_data = market_data or {}
    band = market_data.get("band") or get_market_band(market_data.get("role", "backend_engineer"), region) or [25, 35, 50, 70, 100]
    market_value = market_data.get("value_in_market_unit") or (total.gross / 10_000.0 if region == "CN" else total.gross / 1000.0)
    percentile = market_data.get("percentile") or compute_percentile(market_value, band)

    pos = _market_position(percentile)
    base_uplift = _BASE_UPLIFT_PCT[pos]
    target_total = round(total.total_comp * (1 + base_uplift) + max(0, 50_000 if region == "CN" else 5000), 0)
    walkaway = round(total.total_comp * 0.95, 0)

    tactics = _heuristic_tactics(o, total, percentile)
    email = _heuristic_email(o, total, target_total, language=language)

    overall_advice = (
        f"当前 offer 在市场 p{percentile} 的位置,建议目标总包 {currency} {round(target_total, 0):,} "
        f"(涨 {round(base_uplift * 100)}%),最低走人底线 {currency} {round(walkaway, 0):,}。"
    )

    # ---- LLM 增强 → 必要时替换整体 advice
    llm = llm_provider or _try_get_llm()
    if llm is not None and not _is_mock(llm):
        try:
            prompt = _build_prompt(o, total, target_total, percentile, band, language)
            resp = await llm.chat(
                messages=[Message(role="user", content=prompt)],
                model="gpt-4o-mini",
                temperature=0.4,
                max_tokens=900,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.content) if isinstance(resp.content, str) else (resp.content or {})
            if isinstance(data, dict):
                # 合并
                overall_advice = data.get("advice") or overall_advice
                email = data.get("email") or email
                extra_tp = data.get("talking_points") or []
                if extra_tp:
                    talking_points = list(dict.fromkeys([*extra_tp] + [
                        "用市场 p75 而非单一公司数据",
                        "将可选的 signing bonus / equity refresh 作为杠杆",
                        "明确底线 + 时间窗",
                    ]))
                else:
                    talking_points = [
                        "用市场 p75 而非单一公司数据",
                        "将可选的 signing bonus / equity refresh 作为杠杆",
                        "明确底线 + 时间窗",
                    ]
                provider = getattr(llm, "provider_name", "unknown")
            else:
                provider = getattr(llm, "provider_name", "mock")
                talking_points = [
                    "用市场 p75 而非单一公司数据",
                    "将可选的 signing bonus / equity refresh 作为杠杆",
                    "明确底线 + 时间窗",
                ]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"negotiation LLM enhance failed: {e}")
            provider = "mock"
            talking_points = [
                "用市场 p75 而非单一公司数据",
                "将可选的 signing bonus / equity refresh 作为杠杆",
                "明确底线 + 时间窗",
            ]
    else:
        provider = "mock"
        talking_points = [
            f"当前 offer 总包 {total.currency} {round(total.total_comp, 0):,},市场分位 p{percentile}",
            f"建议目标 {total.currency} {round(target_total, 0):,},涨幅 {round(base_uplift * 100)}%",
            "提供 1-2 个具体案例锚定(同类岗位 / 同公司近期 offer)",
            "把 signing bonus / PTO 作为低成本谈判筹码",
            "若现金包动不了,把股权前移 / refresh 写入 offer letter",
        ]

    counter = []
    for r in _COUNTER_RESPONSES:
        item = {"hr_says": r["hr_says"]}
        item["respond"] = (r["respond_en"] if language.lower().startswith("en") else r["respond_cn"]).format(
            target=f"{total.currency} {round(walkaway, 0):,}"
        )
        counter.append(item)

    return NegotiationScript(
        offer_title=o.title or o.company or "Offer",
        region=region,
        currency=currency,
        current_total=total.total_comp,
        target_total=target_total,
        percent_in_market=percentile,
        market_band=band,
        overall_advice=overall_advice,
        talking_points=talking_points,
        email_template=email,
        counter_examples=[f"HR:{c['hr_says']}\n你:{c['respond']}" for c in counter],
        tactics=tactics,
        walkaway_threshold=walkaway,
        next_steps=[
            "48 小时内用邮件 / 微信正式发起谈判",
            "若 7 天无回复 → 主动跟进一次",
            "如被明确拒,可接受 equity refresh 或 PTO 替代",
            "到达 walkaway 底线并 5 天无新 offer → 接受或继续看机会",
        ],
        provider=provider,
    )


def _build_prompt(
    o: OfferInput, t: AnnualTotal, target: float, percentile: int, band: list[int], language: str
) -> str:
    return (
        "你是一位资深的薪酬谈判教练。基于以下 offer 数据,生成一个务实且礼貌的谈判脚本。\n"
        f"岗位:{o.title or ''}\n公司:{o.company or ''}\n地区:{o.location}\n薪资:{t.currency} "
        f"年薪 {round(t.gross, 0)},股权折现 {round(t.equity_pv, 0)},福利 {round(t.benefits, 0)}\n"
        f"总包:{round(t.total_comp, 0)}\n"
        f"市场分位:p{percentile} / band={band}\n"
        f"目标:{round(target, 0)}\n语言:{language}\n\n"
        "输出严格 JSON:\n"
        "{\n"
        ' "advice": "1 段中文/英文整体建议",\n'
        ' "talking_points": ["..."],\n'
        ' "email": "邮件 / 微信话术原文"\n'
        "}"
    )


def _try_get_llm() -> LLMProvider | None:
    try:
        return get_llm_provider()
    except Exception:
        return None


def _is_mock(p: Any) -> bool:
    return (getattr(p, "provider_name", "") or "").lower() in {"", "mock"}


# ---------------------------------------------------------------------------
# T1802 - 5 个场景化谈判话术
# ---------------------------------------------------------------------------
# 来自合作方 HR 提供的真实谈判案例,每个场景对应:
#   - 触发条件 (when)
#   - 场景标签 + 风险等级
#   - 中文/英文话术(email + talking_points + 反例回应)
# ---------------------------------------------------------------------------
NEGOTIATION_SCENARIOS: dict[str, dict[str, Any]] = {
    "scenario_a_below_p50": {
        "label": "Below p50 — 市场分位偏低",
        "risk_level": "low",
        "applicable_when": "current_offer_total < market_band_p50",
        "anchor_uplift_pct": 0.12,
        "talking_points_cn": [
            "结合贵司同岗位级别 / 行业一线公司的数据,本次 offer 的现金包相对 p50 偏低约 8-15%",
            "我同步在面 X、Y 等公司,可提供的具体数字对比(已脱敏)",
            "可接受现金 + 签字费组合:总包目标上调 8-10%,签字费覆盖搬家 / 时间窗",
        ],
        "talking_points_en": [
            "Based on recent comp data for this level (tech leads / P6 / L5) the cash component is at p25-p40 in our market.",
            "I have active processes at X and Y; I'd like to match the highest all-in offer.",
            "Could we do 8-10% cash uplift + a meaningful signing bonus to bridge the gap?",
        ],
        "email_subject_cn": "关于 offer 调整的正式沟通",
        "email_subject_en": "Quick revisit on the offer package",
    },
    "scenario_b_competing_offer": {
        "label": "Compete — 多家 offer 互 match",
        "risk_level": "low",
        "applicable_when": "candidate_has_2plus_active_offers",
        "anchor_uplift_pct": 0.10,
        "talking_points_cn": [
            "诚实沟通:目前在 X 公司拿到口头 offer,薪资包比贵司当前 offer 高约 12%",
            "如果贵司能在 7 天内 match 到该总包,我可以立刻 sign 并撤回其他流程",
            "考虑用 signing bonus 替代长期激励的部分前移",
        ],
        "talking_points_en": [
            "To be transparent — I have a verbal offer from X with ~12% higher all-in comp.",
            "If you can match within 7 days, I'll sign immediately and withdraw from other processes.",
            "Open to structures like signing bonus in lieu of long-term equity refresh.",
        ],
        "email_subject_cn": "关于贵司 offer 与其他在途 offer 的对齐",
        "email_subject_en": "Aligning on the offer vs other active processes",
    },
    "scenario_c_signing_bonus": {
        "label": "Signing — 争取签字费",
        "risk_level": "low",
        "applicable_when": "current_signing_bonus == 0 AND candidate_relocating_or_has_competitor_signing",
        "anchor_uplift_pct": 0.02,  # 主要靠签字费
        "talking_points_cn": [
            "我需要搬家到 X 城市,粗算一次性搬家 + 租房押金 + 时间窗损失 ≈ 5-8 万",
            "贵司当前 offer 没有签字费,希望申请 5-8 万签字费以覆盖搬家 + 与其他 offer 对齐",
            "或者将一次性签字费分摊到首 6 个月月薪",
        ],
        "talking_points_en": [
            "I'm relocating from X to Y; one-time relocation costs are ~$15-25k.",
            "Could we add a signing bonus of $15-25k to offset relocation, or front-load the first 6 months?",
            "Either lump sum or amortized — flexible on structure.",
        ],
        "email_subject_cn": "搬家 + 签字费补偿",
        "email_subject_en": "Relocation + signing bonus request",
    },
    "scenario_d_equity_vesting": {
        "label": "Equity — 调整 vesting / refresh",
        "risk_level": "medium",
        "applicable_when": "equity_4y_no_refresh AND risk_averse_candidate",
        "anchor_uplift_pct": 0.05,
        "talking_points_cn": [
            "股票 4 年线性但每年都有 cliff + 无 refresh,这意味着我前 2 年承担较高下行风险",
            "能否调整为:前 2 年 30%-30%-20%-20% / 2 年后 grant refresh / 或 offer letter 写明 refresh 计划",
            "如果股权不变,现金包能否上调 3-5% 补偿风险溢价?",
        ],
        "talking_points_en": [
            "4-year linear vesting with no refresh means I take on downside risk in years 1-2.",
            "Could we move to 30-30-20-20 back-loading, commit to a refresh, or lift base 3-5%?",
            "Happy to take lower headline equity if the vesting profile is friendlier.",
        ],
        "email_subject_cn": "股权 vesting 节奏 + refresh 安排",
        "email_subject_en": "Equity vesting schedule + refresh discussion",
    },
    "scenario_e_walkaway": {
        "label": "Walkaway — 走人底线",
        "risk_level": "high",
        "applicable_when": "hr_pressure_repeatedly_AND_candidate_has_alternative",
        "anchor_uplift_pct": 0.0,  # 已经到 walkaway
        "talking_points_cn": [
            "感谢贵司在这个流程中的耐心。我清楚 HR 政策有边界,这个薪资包对我(和家人)是不够的。",
            "我的底线是 ¥X,税前。我可以 hold 这个 offer 到本周五 (48h),任何低于此的方案我会主动 withdraw。",
            "如果贵司内部有灵活空间(尤其 equity refresh / bonus 浮动),我非常愿意继续;但如果完全卡死,我会推进其他 offer。",
        ],
        "talking_points_en": [
            "I appreciate the time the team has invested. The current package is below my financial floor.",
            "My floor is $X total comp — I can hold until EOD Friday (48h); below this I withdraw.",
            "If there's any flexibility (RSU refresh, sign-on, performance bonus potential), I'd love to continue; otherwise I'll progress.",
        ],
        "email_subject_cn": "本次 offer 的最终回应",
        "email_subject_en": "Final response on the offer",
    },
}


def list_negotiation_scenarios() -> list[dict]:
    """列出全部 5 个场景元数据(供前端选择 / 文档展示)."""
    out = []
    for k, v in NEGOTIATION_SCENARIOS.items():
        out.append({
            "key": k,
            "label": v["label"],
            "risk_level": v["risk_level"],
            "applicable_when": v["applicable_when"],
            "anchor_uplift_pct": v["anchor_uplift_pct"],
            "email_subject_cn": v.get("email_subject_cn", ""),
            "email_subject_en": v.get("email_subject_en", ""),
        })
    return out


def select_scenario_for_offer(offer: dict | OfferInput, market_data: dict | None = None) -> str:
    """根据 offer + market 自动选择最合适的 5 场景之一(供 UI 默认推荐)。"""
    if isinstance(offer, dict):
        try:
            o = OfferInput(**{k: v for k, v in offer.items() if k in OfferInput.__annotations__})
        except Exception:
            o = OfferInput(base_salary=float(offer.get("base_salary", 0)), location=offer.get("location", "CN"))
    else:
        o = offer

    band = (market_data or {}).get("band") or get_market_band((market_data or {}).get("role", "backend_engineer"), o.location) or [25, 35, 50, 70, 100]
    value_in_market_unit = (market_data or {}).get("value_in_market_unit") or (o.base_salary / 10_000.0 if o.location == "CN" else o.base_salary / 1000.0)
    percentile = (market_data or {}).get("percentile") or compute_percentile(value_in_market_unit, band)

    if percentile < 50:
        return "scenario_a_below_p50"
    if o.signing_bonus == 0:
        return "scenario_c_signing_bonus"
    if o.equity_value > 0 and o.equity_vesting_years >= 4:
        return "scenario_d_equity_vesting"
    if percentile < 75 and o.signing_bonus > 0:
        return "scenario_b_competing_offer"
    return "scenario_e_walkaway"


async def generate_scenario_script(
    scenario_key: str,
    offer: dict | OfferInput,
    *,
    market_data: dict | None = None,
    language: str = "zh",
    llm_provider: LLMProvider | None = None,
) -> NegotiationScript:
    """用指定 5 场景之一 + LLM 增强,产出最终谈判脚本。

    Args:
        scenario_key: 5 个场景 key 之一
        offer: 输入 offer
        market_data: 可选市场分位数据
        language: zh / en
        llm_provider: 可选 LLM 注入
    """
    scenario = NEGOTIATION_SCENARIOS.get(scenario_key)
    if not scenario:
        raise ValueError(f"unknown scenario: {scenario_key}")

    # 先生成基础脚本
    base = await generate_negotiation_script(offer, market_data=market_data, llm_provider=llm_provider, language=language)

    # 在 email + talking_points 上叠加场景化话术
    if language.lower().startswith("en"):
        subject = scenario.get("email_subject_en", "")
        tps = scenario["talking_points_en"]
    else:
        subject = scenario.get("email_subject_cn", "")
        tps = scenario["talking_points_cn"]

    # email 模板前置 subject
    email_with_subject = f"Subject: {subject}\n\n{base.email_template}"
    base.email_template = email_with_subject
    # 把场景的 talking points 放在前,然后继续 base 的 5 个
    base.talking_points = tps + [tp for tp in base.talking_points if tp not in tps][:3]

    # 加 scenario 标记 next_steps
    base.next_steps = [f"采用「{scenario['label']}」场景策略"] + base.next_steps
    return base
