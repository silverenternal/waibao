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
from services.offer_calculator import (
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
