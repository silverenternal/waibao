"""内置触发器定义 (T804).

每个触发器:
    - name        : 唯一标识
    - description : 用途说明
    - schema      : 期望的 context schema (供 UI 编辑器校验)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BuiltinTrigger:
    name: str
    description: str
    schema: dict[str, Any] = field(default_factory=dict)
    example_context: dict[str, Any] = field(default_factory=dict)


BUILTIN_TRIGGERS: dict[str, BuiltinTrigger] = {
    "HR_SERVICE_AUTORESOLVE_RATE_LOW": BuiltinTrigger(
        name="HR_SERVICE_AUTORESOLVE_RATE_LOW",
        description=(
            "HR 智能体在某窗口内的自动解决率低于阈值。"
            "常用于告警 HRBP / 创建工单。"
        ),
        schema={
            "type": "object",
            "required": ["rate", "window", "sample_size"],
            "properties": {
                "rate": {"type": "number", "minimum": 0, "maximum": 1},
                "window": {"type": "string", "enum": ["1d", "7d", "30d"]},
                "sample_size": {"type": "integer", "minimum": 1},
                "tenant_id": {"type": "string"},
            },
        },
        example_context={
            "rate": 0.52,
            "window": "7d",
            "sample_size": 380,
            "tenant_id": "tenant-001",
        },
    ),
    "MATCH_FUNNEL_DROP": BuiltinTrigger(
        name="MATCH_FUNNEL_DROP",
        description=(
            "匹配漏斗中(浏览→收藏→投递→面试)某一步转化率显著下降。"
        ),
        schema={
            "type": "object",
            "required": ["step", "previous_rate", "current_rate"],
            "properties": {
                "step": {"type": "string", "enum": ["view", "save", "apply", "interview"]},
                "previous_rate": {"type": "number"},
                "current_rate": {"type": "number"},
                "tenant_id": {"type": "string"},
            },
        },
        example_context={
            "step": "apply",
            "previous_rate": 0.21,
            "current_rate": 0.09,
            "tenant_id": "tenant-001",
        },
    ),
    "EMOTION_RISK_SPIKE": BuiltinTrigger(
        name="EMOTION_RISK_SPIKE",
        description="求职者情绪风险评分在窗口内出现尖峰。",
        schema={
            "type": "object",
            "required": ["user_id", "score", "delta"],
            "properties": {
                "user_id": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "delta": {"type": "number"},
            },
        },
        example_context={
            "user_id": "user-001",
            "score": 0.82,
            "delta": 0.27,
        },
    ),
    "TICKET_SLA_BREACH_RISK": BuiltinTrigger(
        name="TICKET_SLA_BREACH_RISK",
        description="工单剩余 SLA 时间不足阈值,可能超时。",
        schema={
            "type": "object",
            "required": ["ticket_id", "remaining_minutes"],
            "properties": {
                "ticket_id": {"type": "string"},
                "remaining_minutes": {"type": "integer"},
                "priority": {"type": "string"},
            },
        },
        example_context={
            "ticket_id": "ticket-001",
            "remaining_minutes": 12,
            "priority": "P1",
        },
    ),
    "BIAS_DETECTED": BuiltinTrigger(
        name="BIAS_DETECTED",
        description="TalentBrief / JD 检测出潜在偏见 (高严重度)。",
        schema={
            "type": "object",
            "required": ["doc_id", "severity", "category"],
            "properties": {
                "doc_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                "category": {"type": "string"},
            },
        },
        example_context={
            "doc_id": "jd-007",
            "severity": "high",
            "category": "gender",
        },
    ),
    "POLICY_LEGAL_RISK_UPLOADED": BuiltinTrigger(
        name="POLICY_LEGAL_RISK_UPLOADED",
        description="上传的制度被检测出高法律风险。",
        schema={
            "type": "object",
            "required": ["policy_id", "risk_level"],
            "properties": {
                "policy_id": {"type": "string"},
                "risk_level": {"type": "string", "enum": ["high", "medium", "low"]},
            },
        },
        example_context={"policy_id": "policy-002", "risk_level": "high"},
    ),
}


def get_builtin_trigger(name: str) -> BuiltinTrigger | None:
    """按名字取内置触发器,找不到返回 None."""
    return BUILTIN_TRIGGERS.get(name)