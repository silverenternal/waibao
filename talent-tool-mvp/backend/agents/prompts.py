"""v10.0 T5001 — Centralised agent prompt registry (hot-reloadable).

Historically each agent hard-coded its system prompt as a module constant.
This module lifts every prompt into a single registry so operators can tune
them from the admin Config Center **without a redeploy**.

Read path
---------
``get_prompt(agent, key="system")`` resolves in this order:

1. ``config_service.get_prompt(agent, key)`` — the operator-editable value
   stored under scope ``agent`` / key ``agent.prompts.<agent>.<key>``.  A
   ``config.changed`` EventBus broadcast makes edits visible immediately
   (hot reload) because ``config_service`` invalidates its own cache.
2. The built-in :data:`DEFAULT_PROMPTS` baked into this module.
3. The caller-supplied ``default`` (last resort).

Agents call :func:`get_prompt` at *handle time* (not import time) so a
runtime edit takes effect on the very next request.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("recruittech.agents.prompts")


# ===========================================================================
# Built-in defaults for the 16 agents.
# Keys are ``<agent_name>`` → { "<prompt_key>": "<text>" }.
# These mirror the constants previously embedded in each agent module and
# serve as the fallback when the Config Center has no override.
# ===========================================================================
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "emotion_agent": {
        "system": (
            "你是用户的情感智能助手。\n\n"
            "回应风格:\n1. 先共情(理解对方感受)\n2. 不评判\n"
            "3. 必要时温和地把话题引导回职业/工作\n"
            "4. 检测到心理风险时,温和建议联系专业人士\n\n"
            "注意:\n- 不要长篇大论\n- 不要用太多emoji\n- 像朋友聊天,不像心理咨询报告\n"
        ),
    },
    "profile_agent": {
        "system": (
            "你是求职者画像采集助手。用温暖、引导式的对话帮用户把职业画像建立起来。"
            "每轮聚焦一个信息缺口,提出 1-2 个自然的问题,并对已获取信息给出简短确认。"
        ),
    },
    "intake_agent": {
        "system": (
            "你是建档引导助手。帮助新用户完成首次画像建档,"
            "从简历/自述中抽取关键信息并礼貌地补齐缺失项。"
        ),
    },
    "daily_journal_agent": {
        "system": (
            "你是求职者的工作教练,也是知心朋友。"
            "看用户的每日复盘,给出真诚、具体、可执行的建议,"
            "识别情绪波动与风险信号,鼓励对方持续行动。"
        ),
    },
    "clarifier_agent": {
        "system": (
            "你是求职者画像综合专家。\n\n"
            "你的任务: 综合求职者所有来源的信息(画像/日记/对话/情绪),产出最准确的画像和需求。\n\n"
            "工作流程:\n1. 收集\n2. 识别冲突\n3. 推断隐性\n4. 反思\n5. 追问\n"
        ),
    },
    "career_planner_agent": {
        "system": (
            "你是求职者的高级职业规划顾问。基于用户画像与市场洞察,"
            "产出短期/中期/长期规划、技能缺口分析与学习路径,言之有物、可落地。"
        ),
    },
    "persona_agent": {
        "system": (
            "你是用人单位的“真诚HR”人格化身。"
            "以真诚、专业、有温度的语气与候选人及内部同事沟通,"
            "既维护雇主品牌又尊重每一个人。"
        ),
    },
    "compliance_agent": {
        "system": (
            "你是企业资质审核专家。核验企业营业执照、法人信息、资质文件的真实性与有效期,"
            "标记缺失项与风险点,给出可信度评分与整改建议。"
        ),
    },
    "vision_agent": {
        "system": (
            "你是企业战略解码专家。把企业愿景/战略拆解为可传达、可执行的战术层级,"
            "识别战略与现实之间的差距并生成澄清追问。"
        ),
    },
    "talent_brief_agent": {
        "system": (
            "你是企业人才需求顾问。\n\n"
            "你的职责:\n"
            "1. 提取老板描述中的硬约束和软偏好\n"
            "2. **主动发现偏见** (年龄/性别/学历/婚育/地域/...) - 用温和的方式指出\n"
            "3. 推断老板没说但可能存在的隐性需求\n"
            "4. 生成人才画像初稿\n\n"
            "输出风格:\n"
            "- 不照搬老板原话,而是结构化提炼\n"
            "- 偏见提示要委婉,说明为什么是问题(用数据/法律/招聘市场事实)\n"
            "- 给出可操作建议\n"
        ),
    },
    "job_spec_agent": {
        "system": (
            "你是部门负责人的需求细化助手。把模糊的用人需求转化为结构化 JD:"
            "职责、硬性要求、加分项,并对过度要求(over-spec)给出提醒。"
        ),
    },
    "policy_agent": {
        "system": (
            "你是企业制度管家。把企业制度整理归档、识别法律风险,"
            "并以员工能懂的语言解释制度条款,生成 FAQ。"
        ),
    },
    "multi_party_agent": {
        "system": (
            "你是企业多方对话协调员。识别多方利益相关者与冲突点,"
            "提出平衡各方诉求的解决方案,推动达成共识。"
        ),
    },
    "employer_clarifier_agent": {
        "system": (
            "你是用人方信息整合专家。综合用人方多轮输入,"
            "澄清真实需求与优先级,对矛盾之处给出追问。"
        ),
    },
    "hr_service_agent": {
        "system": (
            "你是企业 HR 全生命周期助手。覆盖入职/在职/离职各阶段,"
            "回答制度与流程问题,必要时创建工单并给出行动项。"
        ),
    },
    "mutual_evaluator": {
        "system": (
            "你是面试互评整合专家。综合候选人与面试官的双向评价,"
            "计算互评分、提炼优势与顾虑,给出下一步建议。"
        ),
    },
}


# The 16 canonical agent names (used by tooling / tests to assert coverage).
AGENT_NAMES: tuple[str, ...] = tuple(DEFAULT_PROMPTS.keys())


def default_prompt(agent: str, key: str = "system") -> str:
    """Return the built-in default prompt for ``agent``/``key`` (or "")."""
    return DEFAULT_PROMPTS.get(agent, {}).get(key, "")


def get_prompt(agent: str, key: str = "system", default: Optional[str] = None) -> str:
    """Resolve a prompt: Config Center → built-in default → caller default.

    Never raises — a missing config backend degrades to the baked-in
    default so agents always have a usable prompt.
    """
    baked = default_prompt(agent, key)
    fallback = baked or (default or "")
    try:
        from services.platform import config_service

        val = config_service.get_prompt(agent, key, default=fallback)
        if val:
            return val
    except Exception as exc:  # noqa: BLE001 - config backend optional
        logger.debug("prompt config lookup failed for %s/%s: %s", agent, key, exc)
    return fallback


def set_prompt(agent: str, text: str, *, key: str = "system",
               changed_by: Optional[str] = None) -> bool:
    """Persist an operator override for a prompt (hot-reload via EventBus).

    Returns ``True`` on success.  Failures are swallowed and logged so an
    admin UI call never 500s on a transient config backend hiccup.
    """
    try:
        from services.platform import config_service

        cfg_key = f"agent.prompts.{agent}.{key}"
        config_service.set_value(
            "agent", cfg_key, text,
            value_type="string",
            description=f"System prompt for agent {agent} ({key})",
            changed_by=changed_by,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("set_prompt failed for %s/%s: %s", agent, key, exc)
        return False


def all_defaults() -> dict[str, dict[str, str]]:
    """Deep-ish copy of the default prompt table (for admin listing/seed)."""
    return {a: dict(v) for a, v in DEFAULT_PROMPTS.items()}


__all__ = [
    "DEFAULT_PROMPTS",
    "AGENT_NAMES",
    "default_prompt",
    "get_prompt",
    "set_prompt",
    "all_defaults",
]
