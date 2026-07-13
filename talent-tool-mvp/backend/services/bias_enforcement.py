"""T3704 - 偏见强制纠正. 词表 + 后报告 + 替代话术."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("recruittech.services.bias_enforcement")

# 偏见词典:每类含词 + 推荐替代
BIAS_LEXICON: Dict[str, Dict[str, Any]] = {
    "age": {
        "label": "年龄偏见",
        "words": ["35岁以下", "30岁以下", "年轻", "应届", "不超", "有活力"],
        "replacement": "建议改为「有 X 年以上实战经验」+ 技能导向",
    },
    "gender": {
        "label": "性别偏见",
        "words": ["男生优先", "只招", "男/女"],
        "replacement": "建议隐去性别,使用「候选人」",
    },
    "appearance": {
        "label": "外貌/婚育偏见",
        "words": ["形象好", "颜值", "已婚已育", "未婚", "无怀孕"],
        "replacement": "建议删除,聚焦能力描述",
    },
    "region": {
        "label": "地域偏见",
        "words": ["985", "211", "本地人", "本市户籍"],
        "replacement": "建议改为「同等学力」/ 能力描述",
    },
    "health": {
        "label": "健康/病史偏见",
        "words": ["无重大疾病", "无精神病史", "体检合格即可"],
        "replacement": "建议删除(入职体检合规即可)",
    },
}


@dataclass
class BiasHit:
    category: str
    label: str
    matched_phrase: str
    position: int
    severity: int  # 0-100


@dataclass
class BiasReport:
    hits: List[BiasHit] = field(default_factory=list)
    score: int = 0   # 100 - 减分
    recommendations: List[str] = field(default_factory=list)
    can_submit: bool = True  # 是否必须替换

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hits"] = [asdict(h) for h in self.hits]
        return d


def scan_bias(text: str) -> BiasReport:
    if not text:
        return BiasReport()
    hits: List[BiasHit] = []
    for cat, info in BIAS_LEXICON.items():
        for w in info["words"]:
            i = text.find(w)
            if i >= 0:
                severity = {"age": 70, "gender": 90, "appearance": 80,
                            "region": 60, "health": 85}.get(cat, 50)
                hits.append(BiasHit(
                    category=cat,
                    label=info["label"],
                    matched_phrase=w,
                    position=i,
                    severity=severity,
                ))
    score = max(0, 100 - sum(h.severity for h in hits))
    recommendations = list({info["replacement"] for _, info in BIAS_LEXICON.items()
                            for h in hits if h.category == _})
    can_submit = not any(h.severity >= 70 for h in hits)  # 高严重度强制替换
    return BiasReport(hits=hits, score=score, recommendations=recommendations, can_submit=can_submit)


def substitute(text: str, replacements: Optional[Dict[str, str]] = None) -> str:
    if not text:
        return text
    out = text
    for cat, info in BIAS_LEXICON.items():
        for w in info["words"]:
            if w in out:
                rep = (replacements or {}).get(cat, info["replacement"])
                out = out.replace(w, f"[已替换:{rep[:30]}…]")
    return out


# ------ 影响报告 ------

def build_impact_report(
    historic_jds: List[Dict[str, Any]],
    months: int = 3,
) -> Dict[str, Any]:
    """historic_jds: [{department, quarter, bias_report: BiasReport.dict, applied}]"""
    affected = []
    dept_counts: Dict[str, int] = defaultdict(int)
    quarter_counts: Dict[str, int] = defaultdict(int)
    for jd in historic_jds:
        br = jd.get("bias_report", {}) or {}
        if br.get("hits"):
            affected.append(jd)
            dept_counts[jd.get("department", "unknown")] += 1
            quarter_counts[jd.get("quarter", "unknown")] += 1
    total = len(historic_jds)
    rate = round(len(affected) / total * 100, 1) if total else 0.0
    if total > 0:
        impact_text = (
            f"近 {months} 个月里 {len(affected)} 个 JD 命中偏见词,占 {rate}%。"
            "研究显示偏见 JD 会让投递量下降 30~50%。"
            "建议采用系统推荐的替代话术重写全部受影响 JD,预计能恢复 30~40% 招聘效果。"
        )
    else:
        impact_text = "暂无足够历史数据评估偏见影响,建议先积累 3 个月 JD 数据。"
    return {
        "total_jds": total,
        "affected_jds": len(affected),
        "affected_rate_pct": rate,
        "department_breakdown": dict(dept_counts),
        "quarter_breakdown": dict(quarter_counts),
        "narrative": impact_text,
        "recommendations": [
            "为部门负责人提供「无偏见 JD 模板」",
            "在 JD 发布前自动加 1 道偏见扫描门",
            "按季度跟踪偏见下降率",
        ],
    }
