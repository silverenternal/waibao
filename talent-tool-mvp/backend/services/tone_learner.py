"""v8.1 语气学习服务 - 学习老板/HR 的历史沟通风格.

T3701 - 2.1 个性化 HR.
"""
from __future__ import annotations

import json
import re
import logging
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.tone_learner")

TONE_FORMAL = "formal"
TONE_CASUAL = "casual"
TONE_DATA_DRIVEN = "data_driven"
TONE_RELATIONSHIP_DRIVEN = "relationship_driven"

ALL_TONES = [TONE_FORMAL, TONE_CASUAL, TONE_DATA_DRIVEN, TONE_RELATIONSHIP_DRIVEN]

# 启发式规则词典
FORMAL_MARKERS = ["您", "请", "贵", "敬", "此处", "烦请", "恭候"]
CASUAL_MARKERS = ["哈", "哈哈", "加油", "老铁", "咱们", "兄弟", "姐妹", "呀", "嘿"]
DATA_MARKERS = ["%", "增长", "下降", "环比", "同比", "数据", "指标", "达成", "转化率"]
RELATIONSHIP_MARKERS = ["辛苦了", "感谢", "谢谢", "理解", "感受", "希望", "期待", "一起"]


@dataclass
class ToneProfile:
    """一个用户(老板/HR) 的语气画像."""
    user_id: str
    primary_tone: str = TONE_FORMAL
    tone_scores: Dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    last_updated: Optional[str] = None
    manual_override: Optional[str] = None  # 老板手动指定

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_tone(text: str) -> Dict[str, float]:
    """启发式粗分类 (无 LLM 也可用)."""
    if not text:
        return {t: 0.0 for t in ALL_TONES}
    text = text.strip()
    n = max(len(text), 1)
    scores = {TONE_FORMAL: 0.0, TONE_CASUAL: 0.0, TONE_DATA_DRIVEN: 0.0, TONE_RELATIONSHIP_DRIVEN: 0.0}

    # 标点信号
    if "！" in text or "!" in text:
        scores[TONE_CASUAL] += 0.3
        scores[TONE_RELATIONSHIP_DRIVEN] += 0.1
    if text.endswith("。"):
        scores[TONE_FORMAL] += 0.1

    # 关键词匹配
    for kw in FORMAL_MARKERS:
        if kw in text:
            scores[TONE_FORMAL] += 1.0
    for kw in CASUAL_MARKERS:
        if kw in text:
            scores[TONE_CASUAL] += 1.0
    for kw in DATA_MARKERS:
        if kw in text:
            scores[TONE_DATA_DRIVEN] += 1.0
    for kw in RELATIONSHIP_MARKERS:
        if kw in text:
            scores[TONE_RELATIONSHIP_DRIVEN] += 1.0

    # 归一
    total = sum(scores.values()) or 1.0
    return {k: round(v / total, 3) for k, v in scores.items()}


def extract_few_shot_samples(
    history: List[str],
    primary_tone: str,
    max_samples: int = 3,
) -> List[str]:
    """从历史消息里挑选「最像 primary_tone」的 few-shot 样本."""
    if not history:
        return []

    scored = []
    for msg in history:
        if not msg or len(msg.strip()) < 10:
            continue
        c = classify_tone(msg)
        scored.append((c.get(primary_tone, 0.0), msg.strip()))

    scored.sort(key=lambda x: x[0], reverse=True)
    samples = [s for _, s in scored[:max_samples] if _ > 0]
    return samples if samples else [s.strip() for _, s in scored[:max_samples] if s]


def merge_tone_profiles(profiles: List[Dict[str, float]]) -> Dict[str, float]:
    """多个 profile 合并 (取平均权重)."""
    if not profiles:
        return {t: 0.25 for t in ALL_TONES}
    keys = ALL_TONES
    merged = {k: 0.0 for k in keys}
    for p in profiles:
        for k in keys:
            merged[k] += p.get(k, 0.0)
    n = len(profiles)
    return {k: round(v / n, 3) for k, v in merged.items()}


def aggregate_history(history: List[str]) -> ToneProfile:
    """聚合一个用户的所有历史消息,生成 ToneProfile."""
    if not history:
        return ToneProfile(user_id="", sample_count=0)

    per_msg = [classify_tone(m) for m in history if m]
    n = len(per_msg)
    if n == 0:
        return ToneProfile(user_id="", sample_count=0)

    keys = ALL_TONES
    avg = {k: round(sum(p.get(k, 0.0) for p in per_msg) / n, 3) for k in keys}
    primary = max(avg, key=avg.get)

    return ToneProfile(
        user_id="",
        primary_tone=primary,
        tone_scores=avg,
        sample_count=n,
    )


def render_tone_for_prompt(profile: ToneProfile) -> str:
    """渲染到 system prompt."""
    tone = profile.manual_override or profile.primary_tone
    desc = {
        TONE_FORMAL: "用词正式礼貌,称呼「您」「贵公司」,长句书面化",
        TONE_CASUAL: "亲切口语,可用「哈」「咱们」,句子简短,有感叹号",
        TONE_DATA_DRIVEN: "围绕指标/KPI,多用数字和百分比,论点支撑靠数据",
        TONE_RELATIONSHIP_DRIVEN: "重情感共鸣,表达「辛苦了」「感谢」「理解」",
    }
    return f"语气风格:{tone}\n  - {desc.get(tone, desc[TONE_FORMAL])}"


def rewrite_template(template: str, profile: ToneProfile) -> str:
    """轻量去模板化:在 template 周围加语气提示 + 老板的 few-shot 锚点."""
    tone = profile.manual_override or profile.primary_tone

    preambles = {
        TONE_FORMAL: "请您按以下正式得体的语气回复:\n",
        TONE_CASUAL: "按咱们熟悉的轻松口吻回复,加点温度:\n",
        TONE_DATA_DRIVEN: "回复请包含数据支撑,逻辑清晰:\n",
        TONE_RELATIONSHIP_DRIVEN: "回复体现同理心和关系维护:\n",
    }

    # 替换占位符 (老板自定义语料)
    body = template
    if profile.manual_override and "{{tone}}" in body:
        body = body.replace("{{tone}}", profile.manual_override)

    return f"[{tone}]\n{preambles.get(tone, preambles[TONE_FORMAL])}{body}"
