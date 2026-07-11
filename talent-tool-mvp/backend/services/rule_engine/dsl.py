"""规则引擎 DSL (T804).

JSON 格式:
{
    "id": "rule_hr_low_autoresolve",
    "name": "HR service 自动解决率低告警",
    "description": "...",
    "enabled": true,
    "trigger": "HR_SERVICE_AUTORESOLVE_RATE_LOW",  // 内置触发器或自定义事件名
    "condition": {
        "op": "AND",
        "children": [
            {"op": "<", "field": "rate", "value": 0.6},
            {"op": "in", "field": "window", "value": ["7d", "30d"]}
        ]
    },
    "actions": [
        {"type": "notify", "channel": "wecom", "to": ["hrbp@x.com"],
         "template": "hr_low_autoresolve"},
        {"type": "create_ticket", "department": "HRBP",
         "priority": "P1", "title": "HR service 自动解决率告警"}
    ],
    "cooldown_seconds": 3600,
    "tags": ["hr", "alert"]
}

支持的 operator:
    == != < <= > >= in not_in contains starts_with
复合条件用 ConditionGroup + AND / OR.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any


class ComparisonOp(str, enum.Enum):
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    EXISTS = "exists"


class LogicalOp(str, enum.Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


@dataclass(slots=True)
class Condition:
    """原子条件.

    Attributes:
        op: 比较操作.
        field: 事件上下文中的字段路径,用 . 分层 (e.g. "data.rate").
        value: 比较值.
    """

    op: ComparisonOp
    field: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op.value, "field": self.field, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Condition":
        return cls(
            op=ComparisonOp(d["op"]),
            field=d["field"],
            value=d.get("value"),
        )


@dataclass(slots=True)
class ConditionGroup:
    """复合条件 (AND / OR).

    Attributes:
        op: 逻辑操作.
        children: Condition 或 ConditionGroup 列表.
    """

    op: LogicalOp
    children: list["Condition | ConditionGroup"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op.value,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConditionGroup":
        children: list[Condition | ConditionGroup] = []
        for child in d.get("children", []):
            if "children" in child:
                children.append(ConditionGroup.from_dict(child))
            else:
                children.append(Condition.from_dict(child))
        return cls(op=LogicalOp(d.get("op", "AND")), children=children)


@dataclass(slots=True)
class Action:
    """执行动作.

    常见 type:
        - notify     { channel, to, template }
        - create_ticket { department, priority, title }
        - webhook    { url, secret? }
        - emit_event { event, data }
    """

    type: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.params}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Action":
        d = dict(d)
        type_ = d.pop("type")
        return cls(type=type_, params=d)


@dataclass(slots=True)
class Rule:
    """一条规则.

    Attributes:
        id / name / description / enabled / trigger
        condition: 触发后是否真正执行 (None 表示无条件执行)
        actions: 动作列表
        cooldown_seconds: 同一事件 ID 在该秒数内只触发一次
        tags: 分类标签
    """

    id: str
    name: str
    description: str
    enabled: bool
    trigger: str
    condition: ConditionGroup | Condition | None
    actions: list[Action]
    cooldown_seconds: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "trigger": self.trigger,
            "condition": self.condition.to_dict() if self.condition else None,
            "actions": [a.to_dict() for a in self.actions],
            "cooldown_seconds": self.cooldown_seconds,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        cond_raw = d.get("condition")
        cond_obj: ConditionGroup | Condition | None
        if not cond_raw:
            cond_obj = None
        elif isinstance(cond_raw, dict) and "children" in cond_raw:
            cond_obj = ConditionGroup.from_dict(cond_raw)
        else:
            cond_obj = Condition.from_dict(cond_raw)
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            enabled=bool(d.get("enabled", True)),
            trigger=d["trigger"],
            condition=cond_obj,
            actions=[Action.from_dict(a) for a in d.get("actions", [])],
            cooldown_seconds=int(d.get("cooldown_seconds", 0)),
            tags=list(d.get("tags", [])),
        )

    @classmethod
    def new(
        cls,
        name: str,
        trigger: str,
        actions: list[Action],
        *,
        condition: ConditionGroup | Condition | None = None,
        description: str = "",
        enabled: bool = True,
        cooldown_seconds: int = 0,
        tags: list[str] | None = None,
    ) -> "Rule":
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            enabled=enabled,
            trigger=trigger,
            condition=condition,
            actions=actions,
            cooldown_seconds=cooldown_seconds,
            tags=tags or [],
        )


def parse_rule(d: dict[str, Any] | str) -> Rule:
    """从 dict 或 JSON 字符串解析规则."""
    import json

    if isinstance(d, str):
        d = json.loads(d)
    if not isinstance(d, dict):
        raise TypeError("rule 必须是 dict 或 JSON 字符串")
    return Rule.from_dict(d)