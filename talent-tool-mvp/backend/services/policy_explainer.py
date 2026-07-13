"""T3706 - 制度 AI 解释:把法律语言 → 通俗化 + FAQ."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.policy_explainer")

# 内置「法律→通俗」词映射
LEGAL_TO_PLAIN = [
    (r"用人单位应当", "公司必须"),
    (r"劳动者", "员工"),
    (r"不得", "不可以"),
    (r"工资不得低于当地最低工资标准", "工资不能低于当地最低工资"),
    (r"试用期", "入职试用阶段"),
    (r"竞业限制", "离职后一段时间内不能去竞争对手公司"),
    (r"经济补偿", "辞退补偿金"),
    (r"社会保险", "社保"),
    (r"依法", "按法律"),
    (r"协商一致", "双方都同意"),
    (r"解除劳动合同", "解除合同"),
    (r"违反规章制度", "违反公司规则"),
    (r"严重失职", "工作出现重大失误"),
    (r"营私舞弊", "为了私利做假"),
    (r"立即解除", "当天走人"),
]


@dataclass
class FAQItem:
    q: str
    a: str


@dataclass
class PolicyExplainer:
    plain_version: str
    key_points: List[str] = field(default_factory=list)
    faqs: List[FAQItem] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["faqs"] = [asdict(f) for f in self.faqs]
        return d


def _to_plain(text: str) -> str:
    out = text
    for pat, rep in LEGAL_TO_PLAIN:
        out = re.sub(pat, rep, out)
    # 句尾简化: 长句拆短
    out = re.sub(r"[,，；;]{2,}", "，", out)
    return out


def _extract_key_points(text: str) -> List[str]:
    """粗略抽取「应当/不得/可以/需」开头的句子作为要点."""
    sentences = re.split(r"[。\n!?]", text)
    pts = []
    for s in sentences:
        s = s.strip()
        if any(s.startswith(k) for k in ["应当", "必须", "不得", "可以", "需", "如果", "经"]):
            if 8 <= len(s) <= 60:
                pts.append(s + "。")
    return pts[:5]


def _auto_faq(text: str) -> List[FAQItem]:
    seed = [
        ("这个制度适用于我吗?", _to_plain("按法律和公司制度规定,适用范围以员工签署的合同为准。")),
        ("如果公司不执行怎么办?", _to_plain("员工有权向劳动监察部门投诉,或申请劳动仲裁维护合法权益。")),
        ("试用期最长多久?", _to_plain("按《劳动合同法》: 3 个月以上不满 1 年的,试用期不超过 1 个月;"
                              "1 年以上不满 3 年的,不超过 2 个月;3 年以上或无固定期限,不超过 6 个月。")),
    ]
    return [FAQItem(q=q, a=a) for q, a in seed]


def _risk_flags(text: str) -> List[str]:
    flags = []
    if "罚款" in text:
        flags.append("涉及罚款条款,需 HRBP + 法务复核")
    if "立即解除" in text or "开除" in text:
        flags.append("含即时解除条款,确保程序合规 (通知工会)")
    if "担保" in text:
        flags.append("含担保条款,可能违反《劳动合同法》")
    return flags


def explain_policy(title: str, content: str) -> PolicyExplainer:
    plain = _to_plain(content)
    points = _extract_key_points(plain or content)
    faqs = _auto_faq(plain or content)
    risks = _risk_flags(content)
    return PolicyExplainer(
        plain_version=plain,
        key_points=points,
        faqs=faqs,
        risk_flags=risks,
        citations=[f"#{title} v1.0"],
    )
