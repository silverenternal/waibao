"""T3705 JD 营销化: marketing_mode + SEO + A/B + 4 维评分."""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.jd_marketing")


@dataclass
class SEOPlan:
    title: str
    description: str
    keywords: List[str]


@dataclass
class JDScores:
    completeness: int
    attractiveness: int
    fairness: int
    marketing: int
    total: int

    def to_dict(self):
        return asdict(self)


@dataclass
class JDMeta:
    base: Dict[str, Any]
    seo: SEOPlan
    story_mode: str
    culture_blurb: str
    team_vibe: str
    scores: JDScores
    ab_variants: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["seo"] = asdict(self.seo)
        d["scores"] = self.scores.to_dict()
        return d


def _slug(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip())
    return re.sub(r"[^\w一-龥-]+", "", s)[:80] or "role"


def generate_seo(title: str, role_desc: str, location: str = "") -> SEOPlan:
    keyword_pool = re.findall(r"[\w一-龥]+", f"{title} {role_desc}")[:10]
    return SEOPlan(
        title=f"{title} | 加入我们,一起",
        description=(role_desc or "")[:140],
        keywords=list(dict.fromkeys(keyword_pool))[:8],
    )


def story_mode(role_title: str, vision: str, candidate_impact: str) -> str:
    """返回「故事化」模板."""
    return (
        f"我们正在构建 {vision or '下一代产品'},"
        f"为客户带来 {candidate_impact or '真正的改变'}。"
        f"现在,我们正在寻找一位 {role_title},"
        f"和我们一起定义这个行业的新标准。"
    )


def culture_blurb(culture_keywords: List[str]) -> str:
    if not culture_keywords:
        return "我们倡导开放透明、扁平协作的工作方式"
    return "我们崇尚 " + "、".join(culture_keywords[:5]) + " 的工作方式"


def team_vibe(team_size: int, vibe_keywords: List[str]) -> str:
    kw = "、".join(vibe_keywords[:3]) if vibe_keywords else "脑暴、午餐、出海"
    return f"团队 {team_size} 人, 风格:{kw}"


def score_jd(payload: Dict[str, Any]) -> JDScores:
    """4 维度评分."""
    completeness = 0
    fields = ["title", "description", "requirements", "responsibilities",
              "salary_range", "location", "team_size"]
    for f in fields:
        if payload.get(f):
            completeness += 100 // len(fields)
    completeness = min(100, completeness + (10 if payload.get("benefits") else 0))
    completeness = min(100, completeness)

    desc = (payload.get("description") or "").strip()
    attractiveness = 0
    if len(desc) > 50:
        attractiveness += 40
    if any(k in desc for k in ["改变", "我们正在", "一起", "成长", "影响力"]):
        attractiveness += 30
    if payload.get("salary_range"):
        attractiveness += 20
    if payload.get("team_photo_url") or payload.get("culture_keywords"):
        attractiveness += 10
    attractiveness = min(100, attractiveness)

    fairness = 100
    bias_words = ["35岁以下", "男生", "未婚", "形象好"]
    for w in bias_words:
        if w in desc:
            fairness -= 25
    fairness = max(0, fairness)

    marketing_score = 0
    if "故事" in desc or "我们正在" in desc:
        marketing_score += 40
    if payload.get("culture_keywords"):
        marketing_score += 30
    if "impact" in desc.lower() or "改变" in desc:
        marketing_score += 20
    if payload.get("hero_image_url"):
        marketing_score += 10
    marketing_score = min(100, marketing_score)

    total = (completeness + attractiveness + fairness + marketing_score) // 4
    return JDScores(completeness, attractiveness, fairness, marketing_score, total)


def ab_variant_title(role_title: str) -> List[Dict[str, str]]:
    """生成 2 个标题变体."""
    base = role_title.strip() or "工程师"
    return [
        {"variant": "A", "title": f"【{base}】- 高速成长的初创团队"},
        {"variant": "B", "title": f"{base} - 我们正在改变行业,你呢"},
    ]


def marketing_package(payload: Dict[str, Any]) -> JDMeta:
    role = payload.get("title", "")
    desc = payload.get("description", "")
    vision = payload.get("vision", "")
    impact = payload.get("candidate_impact", "")
    culture_kw = payload.get("culture_keywords", [])
    team_size = int(payload.get("team_size", 0) or 0)
    location = payload.get("location", "")

    seo = generate_seo(role, desc, location)
    story = story_mode(role, vision, impact)
    culture = culture_blurb(culture_kw)
    vibe = team_vibe(team_size, payload.get("vibe_keywords", []))
    scores = score_jd(payload)
    variants = ab_variant_title(role)

    return JDMeta(
        base=payload,
        seo=seo,
        story_mode=story,
        culture_blurb=culture,
        team_vibe=vibe,
        scores=scores,
        ab_variants=variants,
    )
