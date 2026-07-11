"""Rule CRUD + test API (T804).

Endpoints:
  GET    /api/rules                   列表
  POST   /api/rules                   创建
  GET    /api/rules/{id}              详情
  PATCH  /api/rules/{id}              更新
  DELETE /api/rules/{id}              删除
  POST   /api/rules/{id}/test         回放测试
  GET    /api/rules/{id}/runs         运行历史
  GET    /api/rules/triggers          内置触发器清单
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.rule_engine.builtins import BUILTIN_TRIGGERS
from services.rule_engine.dsl import (
    Action,
    Condition,
    ConditionGroup,
    LogicalOp,
    Rule,
    parse_rule,
)
from services.rule_engine.evaluator import validate_condition_depth
from services.rule_engine.tester import replay_rule
from services.rule_engine.evaluator import RuleEvaluator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rules", tags=["rules"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActionIn(BaseModel):
    type: str = Field(..., min_length=1, max_length=64)
    # 其他字段通过 model_config 透传;pydantic v2 允许 extra
    params: dict[str, Any] = Field(default_factory=dict)


class ConditionIn(BaseModel):
    """ConditionGroup 或 Condition 通用描述.

    形态:
      原子条件: {"field": "rate", "op": "<", "value": 0.6}
      复合:     {"op": "AND", "children": [...]}
      NOT:      {"op": "NOT", "children": [<one-child>]}
    """

    op: str = Field(..., min_length=1, max_length=16)
    field: str | None = None
    value: Any = None
    children: list["ConditionIn"] | None = None

    def to_dsl(self) -> Any:
        """转换为 DSL 节点 (Condition 或 ConditionGroup)."""
        from services.rule_engine.dsl import ComparisonOp, Condition, LogicalOp

        if self.children is not None:
            # 复合 (AND/OR/NOT)
            try:
                op = LogicalOp(self.op.upper())
            except ValueError as exc:
                raise ValueError(f"未知 logical op '{self.op}'") from exc
            children: list[Any] = [c.to_dsl() for c in self.children]
            return ConditionGroup(op=op, children=children)
        # 原子
        try:
            op = ComparisonOp(self.op)
        except ValueError as exc:
            raise ValueError(f"未知 comparison op '{self.op}'") from exc
        return Condition(op=op, field=self.field or "", value=self.value)


# 解决 forward ref
ConditionIn.model_rebuild()


class RuleCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    trigger: str = Field(..., min_length=1, max_length=128)
    condition: ConditionIn | None = None
    actions: list[ActionIn] = Field(default_factory=list)
    enabled: bool = True
    cooldown_seconds: int = Field(default=0, ge=0, le=86_400)
    tags: list[str] = Field(default_factory=list)

    @field_validator("actions")
    @classmethod
    def _check_actions(cls, v: list[ActionIn]) -> list[ActionIn]:
        for a in v:
            if a.type not in {"notify", "create_ticket", "webhook", "emit_event"}:
                raise ValueError(f"未知 action type '{a.type}'")
        return v


class RuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    trigger: str | None = Field(default=None, min_length=1, max_length=128)
    condition: ConditionIn | None = None
    actions: list[ActionIn] | None = None
    enabled: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)
    tags: list[str] | None = None


class RuleOut(BaseModel):
    id: str
    organisation_id: str
    name: str
    description: str
    trigger: str
    condition: dict[str, Any] | None
    actions: list[dict[str, Any]]
    enabled: bool
    cooldown_seconds: int
    tags: list[str]
    last_triggered_at: str | None
    trigger_count: int
    created_at: str | None


class TestIn(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class TestOut(BaseModel):
    matched: bool
    condition_trace: list[dict[str, Any]]
    actions_executed: list[dict[str, Any]]
    duration_ms: int
    error: str | None = None


class RunOut(BaseModel):
    id: str
    rule_id: str
    trigger: str
    matched: bool
    context_snapshot: dict[str, Any]
    actions_executed: list[dict[str, Any]]
    duration_ms: int
    error: str | None
    occurred_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_id_for(user: CurrentUser) -> str:
    direct = getattr(user, "organisation_id", None)
    if direct:
        return str(direct)
    supabase = get_supabase_admin()
    res = (
        supabase.table("users")
        .select("organisation_id")
        .eq("id", str(user.id))
        .single()
        .execute()
    )
    org = res.data.get("organisation_id") if res.data else None
    if not org:
        org = str(uuid.uuid4())
        supabase.table("users").update({"organisation_id": org}).eq(
            "id", str(user.id)
        ).execute()
    return str(org)


def _to_out(row: dict[str, Any]) -> RuleOut:
    return RuleOut(
        id=row["id"],
        organisation_id=row.get("organisation_id") or "",
        name=row.get("name") or "",
        description=row.get("description") or "",
        trigger=row.get("trigger") or "",
        condition=row.get("condition"),
        actions=row.get("actions") or [],
        enabled=row.get("enabled", True),
        cooldown_seconds=int(row.get("cooldown_seconds") or 0),
        tags=row.get("tags") or [],
        last_triggered_at=row.get("last_triggered_at"),
        trigger_count=int(row.get("trigger_count") or 0),
        created_at=row.get("created_at"),
    )


def _build_rule_dsl(row: dict[str, Any]) -> Rule:
    payload = {
        "id": row["id"],
        "name": row.get("name") or "",
        "description": row.get("description") or "",
        "enabled": row.get("enabled", True),
        "trigger": row["trigger"],
        "condition": row.get("condition"),
        "actions": row.get("actions") or [],
        "cooldown_seconds": row.get("cooldown_seconds", 0),
        "tags": row.get("tags") or [],
    }
    return parse_rule(payload)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RuleOut])
async def list_rules(
    enabled: bool | None = None,
    trigger: str | None = None,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    q = get_supabase_admin().table("rules").select("*").eq("organisation_id", org)
    if enabled is not None:
        q = q.eq("enabled", enabled)
    if trigger:
        q = q.eq("trigger", trigger)
    res = q.order("created_at", desc=True).execute()
    return [_to_out(r) for r in (res.data or [])]


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleCreateIn,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    cond_node = body.condition.to_dsl() if body.condition else None
    if cond_node is not None:
        try:
            validate_condition_depth(cond_node)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    cond_storage = _condition_to_storage(cond_node)
    actions_payload = [
        {"type": a.type, **a.params} for a in body.actions
    ]
    record = {
        "id": str(uuid.uuid4()),
        "organisation_id": org,
        "name": body.name,
        "description": body.description,
        "trigger": body.trigger,
        "condition": cond_storage,
        "actions": actions_payload,
        "enabled": body.enabled,
        "cooldown_seconds": body.cooldown_seconds,
        "tags": body.tags,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    res = get_supabase_admin().table("rules").insert(record).execute()
    if not res.data:
        raise HTTPException(500, "create_failed")
    return _to_out(res.data[0])


def _condition_to_storage(node: Any) -> dict[str, Any] | None:
    """DB 里统一存 ConditionGroup (即使顶层是原子,也包成单元素 group 便于 _eval_group)."""
    from services.rule_engine.dsl import Condition, ConditionGroup

    if node is None:
        return None
    if isinstance(node, ConditionGroup):
        return node.to_dict()
    if isinstance(node, Condition):
        return ConditionGroup(
            op=LogicalOp.AND,  # type: ignore[arg-type]
            children=[node],
        ).to_dict()
    return None


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: str,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("rules")
        .select("*")
        .eq("id", rule_id)
        .eq("organisation_id", org)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    return _to_out(res.data)


@router.patch("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: str,
    body: RuleUpdateIn,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(400, "no_fields_to_update")
    if "condition" in patch and patch["condition"] is not None:
        cond_dsl = body.condition.to_dsl() if body.condition else None
        if cond_dsl is not None:
            try:
                validate_condition_depth(cond_dsl)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            patch["condition"] = _condition_to_storage(cond_dsl)
    if "actions" in patch and patch["actions"]:
        patch["actions"] = [
            {"type": a.get("type"), **(a.get("params") or {})}
            for a in patch["actions"]
            if isinstance(a, dict)
        ]
    res = (
        get_supabase_admin()
        .table("rules")
        .update(patch)
        .eq("id", rule_id)
        .eq("organisation_id", org)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    return _to_out(res.data[0])


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("rules")
        .delete()
        .eq("id", rule_id)
        .eq("organisation_id", org)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    return None


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@router.post("/{rule_id}/test", response_model=TestOut)
async def test_rule(
    rule_id: str,
    body: TestIn,
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    res = (
        get_supabase_admin()
        .table("rules")
        .select("*")
        .eq("id", rule_id)
        .eq("organisation_id", org)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "not_found")
    rule = _build_rule_dsl(res.data)
    ev = RuleEvaluator()
    result = await replay_rule(ev, rule, body.context, dry_run=body.dry_run)
    return TestOut(**result.to_dict())


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/runs", response_model=list[RunOut])
async def list_runs(
    rule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(
        require_role(UserRole.admin, UserRole.talent_partner)
    ),
):
    org = _org_id_for(user)
    sb = get_supabase_admin()
    own = (
        sb.table("rules")
        .select("id")
        .eq("id", rule_id)
        .eq("organisation_id", org)
        .execute()
    )
    if not own.data:
        raise HTTPException(404, "not_found")
    res = (
        sb.table("rule_runs")
        .select("*")
        .eq("rule_id", rule_id)
        .order("occurred_at", desc=True)
        .limit(limit)
        .execute()
    )
    out: list[RunOut] = []
    for r in res.data or []:
        out.append(
            RunOut(
                id=r["id"],
                rule_id=r["rule_id"],
                trigger=r.get("trigger") or "",
                matched=bool(r.get("matched")),
                context_snapshot=r.get("context_snapshot") or {},
                actions_executed=r.get("actions_executed") or [],
                duration_ms=int(r.get("duration_ms") or 0),
                error=r.get("error"),
                occurred_at=r.get("occurred_at")
                or datetime.now(tz=timezone.utc).isoformat(),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Triggers catalogue
# ---------------------------------------------------------------------------


@router.get("/triggers/catalogue")
async def list_triggers():
    """内置触发器清单."""
    return {
        "triggers": [
            {
                "name": name,
                "description": t.description,
                "schema": t.schema,
                "example_context": t.example_context,
                "kind": "metric" if name.endswith(("_LOW", "_DROP")) or name.startswith("MATCH_") else "event",
            }
            for name, t in BUILTIN_TRIGGERS.items()
        ]
    }
