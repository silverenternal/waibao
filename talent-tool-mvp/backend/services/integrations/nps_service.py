"""T1702 — NPS 反馈分析服务.

提供两个核心能力:

- ``calculate_nps(scores)``          : 从原始 0-10 分数计算 NPS (复用 pilot_service.compute_nps)
- ``categorize_feedback(comment)``   : 用 LLM 把开放文本反馈分到主题桶

LLM 类别定义 (与 ``pilot_feedback.category`` 对齐):
  - bug                 缺陷
  - feature_request     新功能
  - praise              表扬
  - complaint           抱怨
  - docs                文档 / 易用性
  - performance         性能
  - pricing             价格 / 套餐
  - other               其他

LLM 不可用时回退到启发式关键词匹配,确保服务始终返回结果.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable, Optional

from services.integrations.pilot_service import (
    NPS_TARGET,
    PASSIVE_THRESHOLD,
    PROMOTER_THRESHOLD,
    compute_nps as _compute_nps_pilot,
)

logger = logging.getLogger("recruittech.services.nps_service")


# ---------------------------------------------------------------------------
# 类别常量
# ---------------------------------------------------------------------------

CATEGORY_BUG = "bug"
CATEGORY_FEATURE = "feature_request"
CATEGORY_PRAISE = "praise"
CATEGORY_COMPLAINT = "complaint"
CATEGORY_DOCS = "docs"
CATEGORY_PERFORMANCE = "performance"
CATEGORY_PRICING = "pricing"
CATEGORY_OTHER = "other"

SUPPORTED_CATEGORIES = (
    CATEGORY_BUG,
    CATEGORY_FEATURE,
    CATEGORY_PRAISE,
    CATEGORY_COMPLAINT,
    CATEGORY_DOCS,
    CATEGORY_PERFORMANCE,
    CATEGORY_PRICING,
    CATEGORY_OTHER,
)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NPSResult:
    """NPS 计算结果 (扩展 pilot_service.compute_nps + 趋势)."""

    nps: Optional[float]
    promoters: int
    passives: int
    detractors: int
    responses: int
    target: int = NPS_TARGET
    meets_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CategorizedFeedback:
    """单条反馈分类结果."""

    category: str
    confidence: float
    sentiment: str       # 'positive' | 'neutral' | 'negative'
    tags: list[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# NPS 计算 (对外公开,语义化命名)
# ---------------------------------------------------------------------------


def calculate_nps(
    scores: Iterable[int | None],
    *,
    target: int = NPS_TARGET,
) -> NPSResult:
    """从 NPS 分数列表计算 NPS + 是否达标.

    Args:
        scores: NPS 0-10 分数,None 视为未作答.
        target: 目标 NPS (默认 40).

    Returns:
        :class:`NPSResult`
    """
    raw = _compute_nps_pilot(scores)
    meets = raw["nps"] is not None and raw["nps"] >= target
    return NPSResult(
        nps=raw["nps"],
        promoters=raw["promoters"],
        passives=raw["passives"],
        detractors=raw["detractors"],
        responses=raw["responses"],
        target=target,
        meets_target=meets,
    )


# ---------------------------------------------------------------------------
# 启发式分类 (无 LLM 时的回退)
# ---------------------------------------------------------------------------


_HEURISTIC_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    # (category, regex, sentiment, tag)
    (CATEGORY_BUG, re.compile(r"(崩溃|卡死|闪退|报错|exception|error|crash|bug|404|500|白屏|失败)", re.I), "negative", "defect"),
    (CATEGORY_FEATURE, re.compile(r"(希望|能不能|建议|如果能|feature|缺少|想要|期待)", re.I), "neutral", "wishlist"),
    (CATEGORY_PRAISE, re.compile(r"(太好了|超棒|喜欢|感谢|amazing|love|awesome|great|不错|好用)", re.I), "positive", "praise"),
    (CATEGORY_COMPLAINT, re.compile(r"(难用|卡|慢|不行|失望|frustrated|annoying|bad|hate)", re.I), "negative", "complaint"),
    (CATEGORY_DOCS, re.compile(r"(文档|说明|教程|帮助|docs|documentation|guide)", re.I), "neutral", "docs"),
    (CATEGORY_PERFORMANCE, re.compile(r"(性能|速度|卡顿|加载|慢|slow|lag|latency|performance)", re.I), "negative", "perf"),
    (CATEGORY_PRICING, re.compile(r"(价格|费用|贵|套餐|定价|price|pricing|cost|expensive)", re.I), "negative", "pricing"),
]


def _heuristic_categorize(text: str) -> CategorizedFeedback:
    """基于正则的轻量分类."""
    matches: list[tuple[str, str, str, int]] = []
    for cat, regex, sentiment, tag in _HEURISTIC_RULES:
        if regex.search(text):
            matches.append((cat, sentiment, tag, len(regex.findall(text))))
    if not matches:
        return CategorizedFeedback(
            category=CATEGORY_OTHER,
            confidence=0.3,
            sentiment="neutral",
            tags=[],
            rationale="heuristic: no keyword matched",
        )
    # 取匹配次数最多的
    matches.sort(key=lambda x: x[3], reverse=True)
    cat, sentiment, tag, _ = matches[0]
    tags = list({m[2] for m in matches})
    return CategorizedFeedback(
        category=cat,
        confidence=min(0.6 + 0.1 * len(matches), 0.9),
        sentiment=sentiment,
        tags=tags,
        rationale=f"heuristic: matched {len(matches)} patterns",
    )


# ---------------------------------------------------------------------------
# LLM 分类 (可选,失败/未配置则回退启发式)
# ---------------------------------------------------------------------------


_CATEGORIZE_PROMPT = """你是产品反馈分类助手。请把用户反馈分到下列类别之一,并给出 1-2 个简短标签与 1 句理由。

类别:
- bug                 缺陷 / 报错 / 程序异常
- feature_request     新功能建议 / 想要但缺失
- praise              表扬 / 喜爱
- complaint           不满 / 抱怨 / 失望
- docs                文档 / 教程 / 易用性
- performance         性能 / 速度 / 卡顿
- pricing             价格 / 套餐 / 收费
- other               其他

要求:
- 仅输出严格 JSON,不要任何解释或 markdown:
{{"category":"...","confidence":0.0-1.0,"sentiment":"positive|neutral|negative","tags":["..."],"rationale":"..."}}

用户反馈:
\"\"\"{text}\"\"\"
"""


async def _llm_categorize(text: str) -> Optional[CategorizedFeedback]:
    """通过 LLM 分类,失败返回 None (调用方决定回退)."""
    try:
        # 延迟导入: 避免强制依赖 LLM 客户端
        import json

        from services.llm_cache import generate_text_cached  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.debug("nps_service: LLM not available (%s)", exc)
        return None

    prompt = _CATEGORIZE_PROMPT.format(text=text.strip()[:2000])
    try:
        # generate_text_cached 返回纯文本, 我们尝试解析 JSON
        raw: Any = await generate_text_cached(
            prompt=prompt,
            model=os.getenv("PILOT_CATEGORY_MODEL", "haiku"),
            temperature=0.0,
            max_tokens=300,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("nps_service: LLM call failed (%s)", exc)
        return None

    if isinstance(raw, dict):
        payload = raw
    else:
        # 从文本中抠 JSON
        m = re.search(r"\{.*\}", str(raw), re.S)
        if not m:
            return None
        try:
            payload = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    cat = str(payload.get("category", CATEGORY_OTHER)).strip().lower()
    if cat not in SUPPORTED_CATEGORIES:
        cat = CATEGORY_OTHER
    sentiment = str(payload.get("sentiment", "neutral")).lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    tags = payload.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    tags = [str(t)[:30] for t in tags][:5]
    rationale = str(payload.get("rationale", ""))[:200]

    return CategorizedFeedback(
        category=cat,
        confidence=round(min(max(confidence, 0.0), 1.0), 2),
        sentiment=sentiment,
        tags=tags,
        rationale=rationale,
    )


async def categorize_feedback(
    text: str,
    *,
    use_llm: bool = True,
) -> CategorizedFeedback:
    """对一条开放反馈做分类.

    优先尝试 LLM (若 ``use_llm=True`` 且环境已配置),失败/超时回退到启发式.
    """
    text = (text or "").strip()
    if not text:
        return CategorizedFeedback(
            category=CATEGORY_OTHER,
            confidence=0.0,
            sentiment="neutral",
            rationale="empty input",
        )

    if use_llm:
        llm_result = await _llm_categorize(text)
        if llm_result is not None:
            return llm_result
    return _heuristic_categorize(text)


async def categorize_many(
    texts: list[str],
    *,
    use_llm: bool = True,
) -> list[CategorizedFeedback]:
    """批量分类."""
    return [await categorize_feedback(t, use_llm=use_llm) for t in texts]


__all__ = [
    "CATEGORY_BUG",
    "CATEGORY_COMPLAINT",
    "CATEGORY_DOCS",
    "CATEGORY_FEATURE",
    "CATEGORY_OTHER",
    "CATEGORY_PERFORMANCE",
    "CATEGORY_PRAISE",
    "CATEGORY_PRICING",
    "CategorizedFeedback",
    "NPSResult",
    "SUPPORTED_CATEGORIES",
    "calculate_nps",
    "categorize_feedback",
    "categorize_many",
]