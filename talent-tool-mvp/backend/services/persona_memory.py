"""Persona Memory — 老板 / HR 偏好长期记忆 (T703).

存储键:
    - communication_style  : "formal" | "direct" | "gentle"
    - preferred_terms      : ["快", "迭代", "数据驱动", ...]
    - decision_patterns    : ["先看成本再谈质量", "data-driven", ...]
    - time_zone            : "Asia/Shanghai"
    - favorite_meeting_time: {"weekday": "周三", "hour": "10:00"}

操作:
    - set_pref(supabase, user_id, organisation_id, key, value, source, confidence)
    - get_prefs(supabase, user_id, organisation_id) -> dict
    - infer_prefs_from_text(supabase, user_id, organisation_id, text, llm)
        - LLM 提取偏好,confidence < 0.5 不写入

DB:
    - persona_prefs 表 (supabase/migrations/012_persona_preferences.sql)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("recruittech.services.persona_memory")


# 已知偏好键 + 期望的 schema (供 LLM 提示 + 校验)
PREF_KEYS = {
    "communication_style": "formal | direct | gentle",
    "preferred_terms": "list[str] 关键词/术语",
    "decision_patterns": "list[str] 决策习惯",
    "time_zone": "IANA 时区 e.g. Asia/Shanghai",
    "favorite_meeting_time": "{weekday, hour} 例如 周三 10:00",
}

# 阈值: confidence 低于这个不写
MIN_CONFIDENCE = 0.5

# 来源
SOURCE_EXPLICIT = "explicit"
SOURCE_INFERRED = "inferred"
SOURCE_ADMIN = "admin"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def set_pref(
    supabase: Any,
    user_id: str,
    organisation_id: Optional[str],
    pref_key: str,
    pref_value: Any,
    *,
    source: str = SOURCE_EXPLICIT,
    confidence: float = 0.9,
) -> dict | None:
    """写入一条偏好。

    Returns:
        写入的 row dict, 或者 None (confidence < 阈值 / 失败)
    """
    if confidence < MIN_CONFIDENCE:
        logger.debug(f"persona_memory.set_pref skipped (confidence={confidence} < {MIN_CONFIDENCE})")
        return None
    if pref_key not in PREF_KEYS and not pref_key.startswith("custom."):
        logger.warning(f"persona_memory.set_pref unknown pref_key={pref_key}; allow anyway")
    record = {
        "user_id": user_id,
        "organisation_id": organisation_id,
        "pref_key": pref_key,
        "pref_value": pref_value if isinstance(pref_value, (dict, list, str, int, float, bool)) else {"value": str(pref_value)},
        "source": source,
        "confidence": float(confidence),
    }
    try:
        r = supabase.table("persona_prefs").upsert(
            record, on_conflict="user_id,organisation_id,pref_key"
        ).execute()
        rows = r.data or []
        return rows[0] if rows else record
    except Exception as e:  # noqa: BLE001
        logger.warning(f"persona_memory.set_pref failed: {e}")
        return None


async def get_prefs(
    supabase: Any,
    user_id: str,
    organisation_id: Optional[str] = None,
) -> dict[str, Any]:
    """读取一个用户的所有偏好 (以 pref_key 为键)。"""
    try:
        q = supabase.table("persona_prefs").select("*").eq("user_id", user_id)
        if organisation_id is not None:
            q = q.eq("organisation_id", organisation_id)
        r = q.execute()
        rows = r.data or []
        return {row["pref_key"]: row for row in rows}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"persona_memory.get_prefs failed: {e}")
        return {}


async def get_pref(
    supabase: Any,
    user_id: str,
    pref_key: str,
    organisation_id: Optional[str] = None,
) -> dict | None:
    prefs = await get_prefs(supabase, user_id, organisation_id)
    return prefs.get(pref_key)


async def delete_pref(
    supabase: Any,
    user_id: str,
    pref_key: str,
    organisation_id: Optional[str] = None,
) -> bool:
    try:
        q = supabase.table("persona_prefs").delete().eq("user_id", user_id).eq("pref_key", pref_key)
        if organisation_id is not None:
            q = q.eq("organisation_id", organisation_id)
        q.execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"persona_memory.delete_pref failed: {e}")
        return False


# ---------------------------------------------------------------------------
# 自动学习 (LLM 提取)
# ---------------------------------------------------------------------------
EXTRACT_PROMPT = """你是一个偏好分析助手。从用户最近的发言中提取偏好,仅在表达明显时输出。

候选偏好键:
- communication_style: 沟通风格 (formal/direct/gentle)
- preferred_terms: 偏好术语或关键词 (list)
- decision_patterns: 决策模式/习惯 (list)
- time_zone: 时区 (如 Asia/Shanghai)
- favorite_meeting_time: 最喜欢的开会时间 (weekday/hour)

输入文本: "{text}"

输出 JSON:
{{
  "prefs": [
    {{"key": "communication_style", "value": "direct", "confidence": 0.0~1.0}},
    {{"key": "preferred_terms", "value": ["迭代", "数据驱动"], "confidence": 0.8}},
    ...
  ],
  "notes": "可选说明"
}}

约束:
- 如果没有任何偏好信号,返回 {{"prefs": [], "notes": "no signal"}}
- confidence 必须反映证据强度;含糊的不要给 (>0.5)
"""


async def infer_prefs_from_text(
    supabase: Any,
    user_id: str,
    organisation_id: Optional[str],
    text: str,
    *,
    llm: Any = None,
    source: str = SOURCE_INFERRED,
) -> list[dict]:
    """从一段对话里提取偏好,自动 upsert 到 persona_prefs。

    Returns:
        写入成功的 rows (不含 confidence < 0.5 的)。
    """
    if not text or not text.strip():
        return []

    from agents.runtime import LLMClient

    client = llm or LLMClient()
    prompt = EXTRACT_PROMPT.format(text=text[:2000])

    try:
        import json as _json

        # 调 LLM
        raw = await client.call(
            [{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        # client.call 返回 (text, in_tok, out_tok) tuple in this repo
        if isinstance(raw, tuple):
            text_resp = raw[0]
        else:
            text_resp = getattr(raw, "text", None) or str(raw)
        result = _json.loads(text_resp)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"persona_memory.infer LLM failed: {e}")
        # fallback: 关键词兜底
        result = _keyword_fallback(text)

    rows: list[dict] = []
    for p in result.get("prefs", []) or []:
        key = p.get("key")
        value = p.get("value")
        conf = float(p.get("confidence", 0.0))
        if not key or value is None:
            continue
        row = await set_pref(
            supabase,
            user_id,
            organisation_id,
            key,
            value,
            source=source,
            confidence=conf,
        )
        if row is not None:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 关键词兜底 (无 LLM 时)
# ---------------------------------------------------------------------------
def _keyword_fallback(text: str) -> dict[str, Any]:
    """规则: 高频词 + 风格关键词"""
    text_lower = text.lower()

    # communication_style
    style = None
    if any(w in text for w in ["麻烦", "请", "感谢", "辛苦了"]):
        style = "gentle"
    elif any(w in text for w in ["马上", "立刻", "直接", "不要绕"]):
        style = "direct"
    elif any(w in text for w in ["以下为", "根据", "依据"]):
        style = "formal"

    # preferred_terms: 抽取 2-grams 高频词
    words = re.findall(r"[一-龥A-Za-z]{2,}", text)
    stopwords = {"这个", "那个", "可以", "需要", "我们", "你们", "他们", "没有", "什么"}
    freq: dict[str, int] = {}
    for w in words:
        if w in stopwords:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda x: -x[1])[:5]
    top_terms = [w for w, _ in top if _ >= 2]

    prefs = []
    if style:
        prefs.append({"key": "communication_style", "value": style, "confidence": 0.7})
    if top_terms:
        prefs.append({"key": "preferred_terms", "value": top_terms, "confidence": 0.6})

    return {"prefs": prefs, "notes": "keyword_fallback"}


# ---------------------------------------------------------------------------
# 渲染偏好到 system prompt
# ---------------------------------------------------------------------------
def render_prefs_for_prompt(prefs: dict[str, Any]) -> str:
    """把 prefs dict 渲染成一段系统提示。"""
    if not prefs:
        return ""
    lines = ["已知老板偏好:"]
    for key, row in prefs.items():
        if not isinstance(row, dict):
            continue
        value = row.get("pref_value", {})
        if isinstance(value, dict):
            v_str = value.get("value", "")
            if not v_str and "values" in value:
                v_str = ", ".join(value["values"])
            if not v_str:
                v_str = str(value)
        elif isinstance(value, list):
            v_str = ", ".join(str(x) for x in value)
        else:
            v_str = str(value)
        conf = row.get("confidence", 0.5)
        src = row.get("source", "explicit")
        lines.append(f"- {key} = {v_str}  (source={src}, confidence={conf:.2f})")
    return "\n".join(lines)