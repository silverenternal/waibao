"""通知模板模块 (T104).

提供 4 类核心业务场景的 jinja2 模板:
- emotion_high_risk: 情绪高风险 (心理预警)
- ticket_created: 工单/任务创建
- match_success: 候选人匹配成功
- system_alert: 系统告警 (运维/容量)

每类模板输出 ``NotificationTemplate`` 封装,内含:
- subject: 简短标题 (用于 IM/邮件主题)
- body: 纯文本正文 (兜底所有通道)
- html: 可选富文本 (邮件/Markdown 通道使用)
- meta: 透传给 provider 的 metadata (例如 atMobiles)

模板字符串内联在此模块中 (避免静态资源加载复杂度);通过 jinja2.Environment
完成变量替换;对未提供变量做静默渲染 (jinja2 default)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

logger = logging.getLogger("recruittech.services.notify.templates")


class NotificationType(str, Enum):
    """业务通知类型枚举."""

    EMOTION_HIGH_RISK = "emotion_high_risk"
    TICKET_CREATED = "ticket_created"
    MATCH_SUCCESS = "match_success"
    SYSTEM_ALERT = "system_alert"


# ---------------------------------------------------------------------------
# 模板字典 (按 NotificationType 索引)
# ---------------------------------------------------------------------------

_TEMPLATE_SPECS: dict[NotificationType, dict[str, str]] = {
    NotificationType.EMOTION_HIGH_RISK: {
        "subject": "[情绪预警] 候选人 {{ candidate_name }} 出现高风险信号",
        "body": (
            "时间: {{ occurred_at | default('未知') }}\n"
            "候选人: {{ candidate_name | default('匿名') }}\n"
            "风险等级: {{ risk_level | default('HIGH') }}\n"
            "触发信号: {{ trigger | default('未提供') }}\n\n"
            "建议操作:\n"
            "1. 优先安排 1v1 沟通\n"
            "2. 评估是否暂停面试/推进流程\n"
            "3. 必要时对接 EAP (员工帮助计划)\n\n"
            "跟踪链接: {{ link | default('#') }}"
        ),
        "html": (
            "## 情绪高风险告警\n\n"
            "- **候选人**: {{ candidate_name | default('匿名') }}\n"
            "- **风险等级**: <span style=\"color:#d4380d\">{{ risk_level | default('HIGH') }}</span>\n"
            "- **触发信号**: {{ trigger | default('未提供') }}\n"
            "- **时间**: {{ occurred_at | default('未知') }}\n\n"
            "[查看详情]({{ link | default('#') }})\n"
        ),
    },
    NotificationType.TICKET_CREATED: {
        "subject": "[新工单] {{ title }}",
        "body": (
            "工单编号: {{ ticket_id | default('(待生成)') }}\n"
            "类型: {{ ticket_type | default('通用') }}\n"
            "优先级: {{ priority | default('P2') }}\n"
            "创建人: {{ created_by | default('system') }}\n"
            "创建时间: {{ created_at | default('') }}\n\n"
            "描述:\n{{ description | default('(无)') }}"
        ),
        "html": (
            "## 新工单创建\n\n"
            "- **编号**: {{ ticket_id | default('(待生成)') }}\n"
            "- **类型**: {{ ticket_type | default('通用') }}\n"
            "- **优先级**: `{{ priority | default('P2') }}`\n"
            "- **创建人**: {{ created_by | default('system') }}\n\n"
            "### 描述\n{{ description | default('(无)') }}\n"
        ),
    },
    NotificationType.MATCH_SUCCESS: {
        "subject": "[匹配成功] {{ candidate_name }} ↔ {{ role_title }}",
        "body": (
            "候选人: {{ candidate_name | default('未知') }}\n"
            "职位: {{ role_title | default('未命名') }}\n"
            "综合得分: {{ score | default('--') }}\n"
            "技能匹配: {{ skill_score | default('--') }}\n"
            "语义相似度: {{ semantic_score | default('--') }}\n\n"
            "推荐下一步:\n"
            "- 发起 handoff\n"
            "- 安排 talent partner 初筛\n"
            "- 准备面试包\n\n"
            "查看详情: {{ link | default('#') }}"
        ),
        "html": (
            "## 候选人匹配成功\n\n"
            "| 字段 | 值 |\n| --- | --- |\n"
            "| 候选人 | {{ candidate_name | default('未知') }} |\n"
            "| 职位 | {{ role_title | default('未命名') }} |\n"
            "| 综合得分 | **{{ score | default('--') }}** |\n"
            "| 技能匹配 | {{ skill_score | default('--') }} |\n"
            "| 语义相似度 | {{ semantic_score | default('--') }} |\n\n"
            "[打开候选人详情]({{ link | default('#') }})\n"
        ),
    },
    NotificationType.SYSTEM_ALERT: {
        "subject": "[系统告警][{{ severity | default('WARN') }}] {{ alert_name }}",
        "body": (
            "告警名称: {{ alert_name | default('未知') }}\n"
            "等级: {{ severity | default('WARN') }}\n"
            "来源: {{ source | default('platform') }}\n"
            "发生时间: {{ occurred_at | default('') }}\n\n"
            "描述: {{ description | default('(无)') }}\n\n"
            "处置建议: {{ action | default('请相关 SRE 介入') }}"
        ),
        "html": (
            "## 系统告警\n\n"
            "- **告警**: {{ alert_name | default('未知') }}\n"
            "- **等级**: <span style=\"color:#d4380d\">{{ severity | default('WARN') }}</span>\n"
            "- **来源**: {{ source | default('platform') }}\n"
            "- **时间**: {{ occurred_at | default('') }}\n\n"
            "### 描述\n{{ description | default('(无)') }}\n\n"
            "### 建议\n{{ action | default('请相关 SRE 介入') }}\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# 渲染结果封装
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NotificationTemplate:
    """模板渲染结果."""

    type: NotificationType
    subject: str
    body: str
    html: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_message_payload(self, recipients: list[str]) -> dict[str, Any]:
        """转换为 dispatcher 内部使用的载荷."""
        return {
            "subject": self.subject,
            "body": self.body,
            "html": self.html,
            "to": list(recipients),
            "metadata": dict(self.meta),
            "type": self.type.value,
        }


# ---------------------------------------------------------------------------
# jinja2 环境 (单例)
# ---------------------------------------------------------------------------

_env: Environment | None = None


def _get_env() -> Environment:
    """获取 jinja2 Environment (懒加载单例).

    使用 StrictUndefined 之外回退到 default filter:
    业务字段常缺失 (例如 trigger/link 等),
    用 | default('...') 兜底,避免 StrictUndefined 渲染失败.
    """
    global _env
    if _env is None:
        _env = Environment(
            autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _env


def _render(spec: str, context: dict[str, Any]) -> str:
    env = _get_env()
    try:
        return env.from_string(spec).render(**context)
    except Exception as exc:  # pragma: no cover — defensive log only
        logger.exception("template render failed: %s", exc)
        # 兜底:返回原始模板字符串 (便于排查)
        return spec


def render_template(
    ntype: NotificationType | str,
    context: dict[str, Any] | None = None,
    *,
    recipients: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> NotificationTemplate:
    """根据通知类型 + 上下文渲染模板.

    Args:
        ntype: ``NotificationType`` 或其 value (兼容字符串).
        context: 模板变量字典;允许缺失 (会用 ``| default`` 兜底).
        recipients: 默认收件人 (可选,用于 dispatcher 透传).
        meta: 透传 metadata (例如 ``atMobiles``/``priority``).

    Returns:
        ``NotificationTemplate`` 实例,业务方可直接送 dispatcher.
    """
    if isinstance(ntype, str):
        try:
            ntype = NotificationType(ntype)
        except ValueError as exc:
            raise ValueError(f"unknown notification type: {ntype}") from exc

    spec = _TEMPLATE_SPECS.get(ntype)
    if spec is None:
        raise ValueError(f"no template registered for type={ntype}")

    ctx = dict(context or {})

    subject = _render(spec["subject"], ctx)
    body = _render(spec["body"], ctx)
    html = _render(spec["html"], ctx)

    payload_meta: dict[str, Any] = dict(meta or {})
    # 透传 NotificationType + recipients 便于 dispatcher 调试
    payload_meta.setdefault("notification_type", ntype.value)
    if recipients:
        payload_meta.setdefault("default_recipients", list(recipients))

    return NotificationTemplate(
        type=ntype,
        subject=subject,
        body=body,
        html=html,
        meta=payload_meta,
    )


def available_types() -> list[str]:
    """列出所有可用的通知类型 (调试/UI 下拉用)."""
    return [t.value for t in NotificationType]


__all__ = [
    "NotificationTemplate",
    "NotificationType",
    "render_template",
    "available_types",
]