"""LLM-Native Extractors — 用 LLM 做所有结构化抽取,删除所有正则/词典.

设计哲学:
- ❌ 正则匹配邮箱/手机 (脆弱,只认英文)
- ❌ 关键词词典判断情绪 (丢失细微差别)
- ❌ 硬编码偏见词表 (永远滞后于新偏见形式)
- ✅ 让 LLM 一次性抽取 + 给出推理依据
- ✅ LLM 发现自己不确定时,主动请求更多信息
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import re

from agents.runtime import LLMClient
from agents.toolkit import llm_call
# v11.6 R2 — canonical extraction schemas (single source of truth).
# Each extractor below references these constants instead of inlining its
# own ``schema = """..."""`` block; see agents/schemas.py.
from agents.schemas import (
    BIAS_SCHEMA,
    EMOTION_SCHEMA,
    INTENT_SCHEMA_TEMPLATE,
    PROFILE_SYNTHESIS_SCHEMA,
    RESUME_SCHEMA,
)

logger = logging.getLogger("recruittech.agents.llm_extractor")

# v11.5 R1 — error marker key returned by every extractor on failure.
# Callers MUST treat a dict containing this key as "extraction failed /
# degraded" rather than a real, empty result. This is the single contract
# that turns a silent {} into an observable failure.
EXTRACTION_ERROR_KEY = "_error"


# ============================================================
# 通用抽取工具: LLM-based structured extraction
# ============================================================
_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n", re.MULTILINE)
_TRAILING_FENCE_RE = re.compile(r"\n\s*```\s*$")


def _extract_json_block(raw: str) -> str:
    """Robustly isolate the JSON payload from an LLM completion.

    Local LLMs (qwen2.5 via Ollama, llama, glm) routinely wrap JSON in a
    ```` ```json ```` fence and/or emit leading/trailing chatter despite
    ``json_mode``.  Before giving up on ``json.loads`` we:

      1. strip a single markdown code fence (```json ... ```);
      2. if the whole thing still is not valid JSON, grab the first
         balanced ``{ ... }`` substring (the actual object) and try that.

    Returns the candidate substring; the caller runs ``json.loads`` and
    decides whether it actually parses.
    """
    if raw is None:
        return ""
    text = raw.strip()
    # 1. strip one surrounding fence (start ```json / ``` ... end ```)
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text, count=1)
        text = _TRAILING_FENCE_RE.sub("", text)
        text = text.strip()
    # quick win: already valid-looking
    if text.startswith("{") or text.startswith("["):
        return text
    # 2. fall back to the first balanced { ... } block
    start = text.find("{")
    if start == -1:
        # maybe a JSON array instead
        start = text.find("[")
        if start == -1:
            return text  # let json.loads raise with the original
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text  # unbalanced — let json.loads fail loudly


def parse_llm_json(raw: str) -> dict:
    """Parse an LLM JSON completion robustly; raise on real failure.

    Unlike the previous ``json.loads(raw)`` this survives markdown fences
    and surrounding prose.  Raises ``ValueError`` (with the offending
    snippet) when no valid JSON object can be recovered, so callers can
    convert the failure into a clearly-marked ``_error`` result instead of
    silently treating the output as an empty dict.
    """
    candidate = _extract_json_block(raw or "")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        # last resort: try the literal raw (some models emit valid JSON
        # that our balancer mishandled, e.g. nested stringified JSON)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM did not return valid JSON: {exc.msg}; head={raw[:120]!r}"
            ) from exc
    if not isinstance(parsed, dict):
        # A bare scalar / list is not a valid structured extraction here.
        raise ValueError(
            f"LLM JSON parsed to {type(parsed).__name__}, expected object"
        )
    return parsed

async def extract_json_with_reasoning(
    llm: LLMClient,
    content: str,
    schema_description: str,
    few_shot: Optional[list[dict]] = None,
    max_cost: int = 10,
) -> dict:
    """让 LLM 按 schema 抽取结构化数据,带 reasoning 字段.

    Args:
        content: 要抽取的原始文本
        schema_description: 自然语言描述期望的字段(LLM 比 JSON Schema 更灵活)
        few_shot: 可选的 few-shot 示例
        max_cost: 最大 cost cents
    """
    examples = ""
    if few_shot:
        examples = "\n示例:\n" + "\n".join(
            f"输入: {ex['input']}\n输出: {json.dumps(ex['output'], ensure_ascii=False)}"
            for ex in few_shot[:2]
        )

    system = f"""你是专业的信息抽取助手。

任务: 从给定文本中抽取结构化信息。

抽取 schema:
{schema_description}

每个字段都要带 reasoning (推理依据: 你从哪里看出这个结论)。

如果信息不存在,填 null,reasoning 写"未提及"。

输出 JSON,所有字段都包含 value + reasoning 两个子字段。
{examples}
"""

    try:
        raw = await llm_call(
            llm,
            content,
            system=system,
            json_mode=True,
        )
        result = parse_llm_json(raw)
        # detect empty / no-op results so callers don't mistake them for
        # a genuine "nothing found" — if the model returned an object but
        # every field was dropped, surface that too.
        if not result:
            logger.warning("LLM extraction returned empty object")
            return {EXTRACTION_ERROR_KEY: "empty extraction result", "degraded": True}
        return result
    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}")
        return {EXTRACTION_ERROR_KEY: str(e), "degraded": True}


# ============================================================
# 1. 简历/资料抽取 — 替代 profile_extractor.py 的正则版本
# ============================================================

async def extract_resume(llm: LLMClient, cv_text: str) -> dict:
    """从简历文本中抽取结构化信息."""
    # RESUME_SCHEMA (agents/schemas.py) declares basic.{name,email,phone,
    # location} as FLAT STRINGS — matching resume_parser._post_process,
    # identity/verification and test_resume_parser. (v11.5 drift fix.)
    return await extract_json_with_reasoning(llm, cv_text, RESUME_SCHEMA, max_cost=30)


# ============================================================
# 2. 情绪识别 — 替代 emotion_agent.py 的 lexicon 兜底
# ============================================================

async def detect_emotion(llm: LLMClient, text: str, conversation_context: Optional[list] = None) -> dict:
    """细粒度情绪识别,LLM 自主判断.

    优势 vs 关键词:
    - 能理解"我很'好'啊"的讽刺
    - 能识别复合情绪(焦虑+期待)
    - 能识别隐含情绪
    """
    ctx = ""
    if conversation_context:
        ctx = "\n对话上下文:\n" + "\n".join(
            f"[{c.get('role', 'user')}]: {c.get('content', '')[:200]}" for c in conversation_context[-5:]
        )

    schema = EMOTION_SCHEMA
    # system prompt 明确告诉 LLM 这是情绪分析任务
    system = """你是情感分析专家(情感智能助手)。

请按 schema 从文本中识别用户的情绪、复杂度和风险等级。
注意:讽刺、隐含情绪、复合情绪都要识别。
"""
    content = f"{ctx}\n用户最新输入: {text}"
    try:
        raw = await llm_call(llm, content, system=system, json_mode=True)
        return parse_llm_json(raw)
    except Exception as e:
        logger.warning(f"detect_emotion failed: {e}")
        # Safe-but-marked fallback: the caller (emotion_agent) still needs
        # a usable response for the user, but the result now carries the
        # error marker + degraded flag so it is never mistaken for a real
        # LLM analysis.
        return {
            EXTRACTION_ERROR_KEY: str(e),
            "degraded": True,
            "primary_emotion": "neutral",
            "risk_level": "none",
            "response": "我在听。",
            "emotions": [],
            "complexity": "simple",
        }


# ============================================================
# 3. 偏见检测 — 替代 talent_brief_agent.py 的硬编码词表
# ============================================================

async def detect_biases(llm: LLMClient, text: str) -> dict:
    """让 LLM 自己发现描述中的偏见,而不是靠关键词."""
    return await extract_json_with_reasoning(llm, text, BIAS_SCHEMA, max_cost=15)


# ============================================================
# 4. 意图理解 — 替代 emotion_agent 关键词路由
# ============================================================

async def understand_intent(llm: LLMClient, text: str, available_agents: dict[str, str]) -> dict:
    """LLM 深度理解用户意图,不依赖关键词."""
    agents_desc = "\n".join(f"- {name}: {desc}" for name, desc in available_agents.items())

    schema = INTENT_SCHEMA_TEMPLATE.format(agents_desc=agents_desc)
    return await extract_json_with_reasoning(llm, text, schema, max_cost=5)


# ============================================================
# 5. 多源画像综合 — 增强版 clarifier
# ============================================================

async def synthesize_profile(
    llm: LLMClient,
    sources: dict[str, Any],  # {cv: "...", journals: [...], conversations: [...], emotions: [...]}
) -> dict:
    """多源画像综合,LLM 自己识别冲突和gap."""
    content = json.dumps(sources, ensure_ascii=False)[:8000]
    return await extract_json_with_reasoning(llm, content, PROFILE_SYNTHESIS_SCHEMA, max_cost=40)