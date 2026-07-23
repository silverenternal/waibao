"""Canonical LLM extraction schemas — the single source of truth.

v11.6 R2 — every place that asks the LLM for a structured JSON payload MUST
reference a constant defined here instead of inlining its own triple-quoted
``schema`` string.  Before this module the same extraction
schemas were copy-pasted across:

  * ``agents/llm_extractor.py``    (5 inline blocks)
  * ``agents/employer/talent_brief_agent.py``
  * ``agents/jobseeker/clarifier_agent.py``
  * ``services/jobseeker/resume_parser.py`` (``_RESUME_SCHEMA_HINT``)

…which drifted.  The most damaging drift (caught in v11.5) was the resume
``basic.name`` field: the ``extract_resume`` schema told the LLM to emit
``{"name": {"value": ..., "reasoning": ...}}`` while every consumer
(``resume_parser._post_process``, ``identity/verification``,
``test_resume_parser``) treats ``basic.name`` as a **flat string**.  The
canonical schema here declares it flat, matching the real validated
contract, so the prompt and the code now agree.

Design notes
------------
* These are **natural-language JSON templates** handed to the LLM in the
  system/user prompt, NOT formal JSON Schema (``$schema``).  Local LLMs
  (qwen2.5 / glm via Ollama) follow the example-shape far more reliably
  than a strict JSON Schema, so the existing string templates are
  preserved verbatim — this change only consolidates *where* they live,
  it does not alter extraction semantics.
* Field-naming conventions (global):
    - ``basic.{name,email,phone,location}``  → **flat strings** (PII fields,
      downstream-validated as strings; never ``{value,reasoning}``).
    - ``skills``                              → **list[dict]** with a
      ``name`` string key (consistent across resume + clarifier).
    - scalar quality scores                   → ``0.0~1.0`` float literals.
* Each constant is consumed by exactly one extractor / agent; renaming a
  key here is the one place that must be kept in sync with consumers and
  (for the frontend-facing ones) with R3 / ``contracts/``.
"""
from __future__ import annotations

# ============================================================
# 1. resume extraction — agents/llm_extractor.extract_resume
# ============================================================
# NOTE: ``basic`` fields are FLAT STRINGS. This is the real downstream
# contract — resume_parser._post_process, identity/verification and
# test_resume_parser all read ``basic.name`` as a string (and PII-encrypt
# it). Declaring ``{value,reasoning}`` here (as the old inline schema did)
# was the v11.5 drift that this module fixes. _post_process still
# defensively flattens any stray dict, so the extraction stays robust.
RESUME_SCHEMA = """{
  "basic": {
    "name": "姓名",
    "email": "邮箱",
    "phone": "电话",
    "location": "所在地"
  },
  "education": [
    {"school": "学校", "degree": "学历", "major": "专业", "year": "年份", "reasoning": "..."}
  ],
  "experience": [
    {
      "company": "公司", "title": "职位", "duration_months": 月数,
      "responsibilities": ["职责"], "achievements": ["成果"], "reasoning": "..."
    }
  ],
  "skills": [
    {"name": "技能", "category": "技术/管理/语言/...", "years": 年限, "level": "初/中/高", "evidence": "简历中如何体现", "reasoning": "..."}
  ],
  "highlights": [
    {"fact": "亮点(如:开源贡献、专利)", "significance": "为什么重要"}
  ],
  "red_flags": [
    {"issue": "潜在问题(如:频繁跳槽)", "severity": "低/中/高", "evidence": "依据"}
  ],
  "overall_impression": "一句话总结"
}"""


# ============================================================
# 2. emotion detection — agents/llm_extractor.detect_emotion
# ============================================================
EMOTION_SCHEMA = """{
  "emotions": [
    {"name": "情绪名(joy/sadness/anger/anxiety/confusion/hope/neutral等)", "intensity": 0.0~1.0, "evidence": "原文依据"}
  ],
  "primary_emotion": "主导情绪",
  "complexity": "simple/mixed/contradictory",   // 简单/混合/矛盾
  "underlying_need": "用户真正想表达但没说出的需求",
  "risk_level": "none/mild/moderate/severe",     // 是否有心理风险
  "recommended_response_tone": "warm/encouraging/listening/firm",  // 建议回应语气
  "response": "对用户的回应(2-3 句,先共情再引导)"
}"""


# ============================================================
# 3. bias detection — agents/llm_extractor.detect_biases
#    (also reused by employer/talent_brief_agent via detect_biases)
# ============================================================
BIAS_SCHEMA = """{
  "demographic_bias": [
    {"type": "年龄/性别/学历/地域/婚育/...", "evidence": "原文依据", "severity": "low/medium/high", "concern": "为什么这是问题", "suggestion": "改进措辞"}
  ],
  "cognitive_bias": [
    {"type": "光环效应/锚定/确认偏误/...", "evidence": "...", "concern": "..."}
  ],
  "logical_gaps": [
    {"gap": "逻辑空白", "question_to_clarify": "应该问老板什么问题"}
  ],
  "implicit_requirements": [
    {"req": "老板没说但可能想要的需求", "inferred_from": "推断依据"}
  ],
  "fairness_score": 0.0~1.0,
  "overall_assessment": "总结"
}"""


# ============================================================
# 4. intent understanding — agents/llm_extractor.understand_intent
# ============================================================
# The available-agents catalog is interpolated at call time, so this is a
# format template (the f-string lives in understand_intent).
INTENT_SCHEMA_TEMPLATE = """{{
  "primary_intent": "用户主要想做什么",
  "secondary_intents": ["次要意图"],
  "emotional_state": "用户当前情绪",
  "urgency": "low/medium/high",
  "best_agent": "最合适的 agent",
  "confidence": 0.0~1.0,
  "reasoning": "为什么选这个 agent",
  "needs_disambiguation": true/false,
  "clarification_question": "如果 needs_disambiguation=true,该问什么"
}}

可选 agents:
{agents_desc}
"""


# ============================================================
# 5. profile synthesis — agents/llm_extractor.synthesize_profile
# ============================================================
PROFILE_SYNTHESIS_SCHEMA = """{
  "summary": "一句话画像总结",
  "explicit_profile": {
    "skills": [...], "experience": [...], "education": [...]
  },
  "implicit_profile": {
    "personality_traits": ["从语言风格推断的性格特征"],
    "values": ["价值观"],
    "motivations": ["驱动因素"]
  },
  "needs": {
    "explicit": ["用户明确说过的"],
    "implicit": ["从行为/语气推断的"],
    "conflicting": ["自相矛盾的"]
  },
  "contradictions": [
    {"source_a": "来源1说的", "source_b": "来源2说的", "possible_resolution": "可能的解释"}
  ],
  "completeness": {"field": "completeness 0~1"},
  "confidence": 0.0~1.0,
  "follow_up_questions": ["按重要性排序的追问"]
}"""


# ============================================================
# 6. talent brief — employer/talent_brief_agent._handle (画像草稿)
# ============================================================
TALENT_BRIEF_SCHEMA = """{
  "hard_constraints": [
    {"category": "行业/职级/技能/...", "value": "...", "importance": "must/should", "rationale": "老板为什么提这个"}
  ],
  "soft_preferences": [
    {"preference": "软偏好", "rationale": "为什么老板隐含希望"}
  ],
  "implicit_requirements": [
    {"req": "隐性需求", "inferred_from": "推断依据", "confidence": 0~1}
  ],
  "talent_image_draft": {
    "summary": "一句话人才画像",
    "background": "背景倾向",
    "potential_direction": "潜力方向",
    "values": ["价值观关键词"],
    "red_flags_to_avoid": ["老板没说但可能不喜欢的"]
  },
  "smart_questions_for_boss": [
    {"question": "应该问老板的问题", "purpose": "为什么问"}
  ]
}"""


# ============================================================
# 7. clarifier synthesis — jobseeker/clarifier_agent._llm_synthesize
# ============================================================
CLARIFIER_SYNTHESIS_SCHEMA = """{
  "profile_synthesis": {
    "summary": {"value": "一句话", "reasoning": "..."},
    "explicit_skills": [{"value": "技能", "reasoning": "..."}],
    "implicit_traits": [{"value": "特质", "reasoning": "..."}],
    "value_orientation": [{"value": "价值观", "reasoning": "..."}],
    "career_interests": [{"value": "方向", "reasoning": "..."}]
  },
  "real_needs": {
    "explicit": [...],
    "implicit": [...],
    "must_haves": [...],
    "nice_to_haves": [...],
    "deal_breakers": [...]
  },
  "contradictions": [
    {"source_a": "...", "source_b": "...", "explanation": "..."}
  ],
  "follow_up_questions": [
    {"question": "...", "priority": "high/medium/low", "purpose": "为什么问"}
  ],
  "info_completeness": {"value": 0.0~1.0, "reasoning": "..."},
  "overall_confidence": 0.0~1.0
}"""


__all__ = [
    "RESUME_SCHEMA",
    "EMOTION_SCHEMA",
    "BIAS_SCHEMA",
    "INTENT_SCHEMA_TEMPLATE",
    "PROFILE_SYNTHESIS_SCHEMA",
    "TALENT_BRIEF_SCHEMA",
    "CLARIFIER_SYNTHESIS_SCHEMA",
]
