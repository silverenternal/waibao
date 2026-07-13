"""T3703 - 战略影响分析. 输入策略内容 → 招聘影响 + 自动通知."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.strategy_impact")

# 招聘动作信号
HIRE_KEYWORDS = {
    "招聘": "新设岗位",
    "扩招": "扩编",
    "招": "招聘",
    "校招": "校招启动",
    "补": "补员",
}
CLOSE_KEYWORDS = {
    "关停": "业务关停",
    "裁撤": "裁员",
    "裁": "裁员",
    "退出": "退出市场",
    "停止": "暂停",
}
LANGUAGE_KEYWORDS = {
    "英语": "英语",
    "日语": "日语",
    "西班牙语": "西语",
    "海外": "海外",
    "国际化": "海外",
}
SKILL_KEYWORDS = {
    "AI": "AI/算法",
    "前端": "前端工程师",
    "后端": "后端工程师",
    "运营": "运营",
    "销售": "销售",
    "市场": "市场",
    "产品": "产品",
    "财务": "财务",
}


@dataclass
class ImpactItem:
    type: str  # hire / close / pivot / transform
    title: str
    affected_skills: List[str] = field(default_factory=list)
    estimated_count: Optional[int] = None
    detail: str = ""
    priority: str = "medium"  # low / medium / high


@dataclass
class ImpactReport:
    strategy_excerpt: str
    items: List[ImpactItem] = field(default_factory=list)
    summary: str = ""
    auto_notify_targets: List[str] = field(default_factory=list)
    raw_signals: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["items"] = [asdict(i) for i in self.items]
        return d


def _scan(text: str, mapping: Dict[str, str]) -> List[str]:
    found = []
    for kw, label in mapping.items():
        if kw in text:
            found.append(label)
    return list(dict.fromkeys(found))  # 去重


def _extract_numbers(text: str) -> List[int]:
    nums = re.findall(r"\d+\s*(?:个|人|名|位|岗|/)", text)
    out = []
    for s in nums:
        try:
            n = int(re.search(r"\d+", s).group())
            out.append(n)
        except Exception:
            pass
    return out


def analyze_strategy(content: str) -> ImpactReport:
    content = content or ""
    signals = {
        "hire": _scan(content, HIRE_KEYWORDS),
        "close": _scan(content, CLOSE_KEYWORDS),
        "language": _scan(content, LANGUAGE_KEYWORDS),
        "skill": _scan(content, SKILL_KEYWORDS),
    }

    nums = _extract_numbers(content)

    items: List[ImpactItem] = []

    # 招聘方向
    for skill in signals["skill"]:
        for hire_label in signals["hire"]:
            count = nums[0] if nums else 3
            items.append(ImpactItem(
                type="hire",
                title=f"需要招聘 {count} 个 {skill} 人才",
                affected_skills=[skill],
                estimated_count=count,
                detail=f"由战略中的[{hire_label}]信号触发,核心能力 {skill}",
                priority="high" if count >= 5 else "medium",
            ))

    # 语言需求
    for lang in signals["language"]:
        items.append(ImpactItem(
            type="hire",
            title=f"增加 {lang} 岗位预算",
            affected_skills=["语言", lang],
            estimated_count=2,
            detail=f"国际化扩展需要 {lang} 沟通能力",
            priority="medium",
        ))

    # 关停/裁撤
    for close_label in signals["close"]:
        items.append(ImpactItem(
            type="close",
            title=f"{close_label}",
            affected_skills=[],
            estimated_count=None,
            detail="请同步 HRBP 评估现有员工转岗方案",
            priority="high",
        ))

    # 优先级去重
    seen = set()
    uniq = []
    for i in items:
        if i.title not in seen:
            uniq.append(i)
            seen.add(i.title)

    notify_targets: List[str] = []
    if any(i.type == "hire" for i in uniq):
        notify_targets.append("hr_team")
    if any(i.type == "close" for i in uniq):
        notify_targets.append("hrbp_and_legal")
        notify_targets.append("affected_candidates")

    summary = f"识别 {len(uniq)} 项招聘/业务影响."
    if not uniq:
        summary = "未识别明显战略动作,建议补充更具体的招聘/业务关键词."

    return ImpactReport(
        strategy_excerpt=content[:200],
        items=uniq,
        summary=summary,
        auto_notify_targets=notify_targets,
        raw_signals=signals,
    )


def fire_strategy_updated_event(content: str, version: str = "1.0") -> Dict[str, Any]:
    """触发 strategy.updated 事件总线."""
    try:
        from eventbus import emit  # type: ignore
    except Exception:
        emit = None

    report = analyze_strategy(content)
    payload = report.to_dict()
    payload["version"] = version

    if emit is not None:
        try:
            emit("strategy.updated", payload)
        except Exception as e:
            logger.warning("emit strategy.updated failed: %s", e)

    return payload
