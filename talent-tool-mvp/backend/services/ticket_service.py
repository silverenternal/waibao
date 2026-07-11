"""HR 工单业务服务 (T207).

职责链路:
    create_ticket() -> 计算 SLA due_at + 写状态历史
    transition_status() -> 状态机校验 + 写状态历史 + 更新首响应/解决时间
    add_comment() -> 评论
    get_timeline() -> 合并 status_history + comments 按时序返回

设计:
- 状态机: open → in_progress → (awaiting_user ↔ in_progress) → resolved → closed
- SLA: 按 priority 查 ticket_sla_rules 表; 若规则缺失,降级默认 72h。
- 全部函数接受 supabase client 参数,默认从 api.deps.get_supabase_admin() 取。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger("recruittech.services.ticket")

# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------
TICKET_STATUSES = ("open", "in_progress", "awaiting_user", "resolved", "closed")
TICKET_PRIORITIES = ("low", "normal", "high", "urgent")

# 合法转移: from → set of allowed to
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open":          {"in_progress", "resolved", "closed"},
    "in_progress":   {"awaiting_user", "resolved", "closed"},
    "awaiting_user": {"in_progress", "resolved", "closed"},
    "resolved":      {"closed", "in_progress"},   # 可重开
    "closed":        set(),                        # 终态
}

# 兜底 SLA (查不到规则表时使用)
DEFAULT_SLA_HOURS = {
    "urgent": (1, 8),
    "high":   (2, 24),
    "normal": (8, 72),
    "low":    (24, 168),
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Ticket:
    id: str
    user_id: str
    organisation_id: str | None
    title: str
    description: str
    status: str
    priority: str
    category: str
    assignee_id: str | None
    sla_due_at: str | None
    first_responded_at: str | None
    resolved_at: str | None
    closed_at: str | None
    metadata: dict
    tags: list
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: dict) -> "Ticket":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            organisation_id=row.get("organisation_id"),
            title=row.get("title", ""),
            description=row.get("description", ""),
            status=row.get("status", "open"),
            priority=row.get("priority", "normal"),
            category=row.get("category", "hr"),
            assignee_id=row.get("assignee_id"),
            sla_due_at=row.get("sla_due_at"),
            first_responded_at=row.get("first_responded_at"),
            resolved_at=row.get("resolved_at"),
            closed_at=row.get("closed_at"),
            metadata=row.get("metadata") or {},
            tags=row.get("tags") or [],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organisation_id": self.organisation_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "category": self.category,
            "assignee_id": self.assignee_id,
            "sla_due_at": self.sla_due_at,
            "first_responded_at": self.first_responded_at,
            "resolved_at": self.resolved_at,
            "closed_at": self.closed_at,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TicketError(Exception):
    """工单业务异常."""


class InvalidTransitionError(TicketError):
    """非法状态转移."""


# ---------------------------------------------------------------------------
# SLA 计算
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def compute_sla_due_at(priority: str, *, base: datetime | None = None) -> datetime:
    """根据 priority 计算 SLA 截止时间.

    优先读 ticket_sla_rules; 缺失则降级到默认映射。
    返回 datetime (UTC)。
    """
    p = (priority or "normal").lower()
    if p not in DEFAULT_SLA_HOURS:
        p = "normal"
    # resolution_hrs 是 SLA 截止时间 (一般最看重解决 SLA)
    _, resolution_hrs = DEFAULT_SLA_HOURS[p]
    return (base or _now_dt()) + timedelta(hours=resolution_hrs)


def compute_sla_due_from_rules(
    supabase: Any,
    priority: str,
    *,
    base: datetime | None = None,
) -> datetime:
    """从 ticket_sla_rules 表读取 resolution_hrs 计算 SLA (如果表可读)."""
    p = (priority or "normal").lower()
    if p not in DEFAULT_SLA_HOURS:
        p = "normal"
    try:
        result = (
            supabase.table("ticket_sla_rules")
            .select("resolution_hrs")
            .eq("priority", p)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        if result and result.data and result.data.get("resolution_hrs"):
            hrs = int(result.data["resolution_hrs"])
            return (base or _now_dt()) + timedelta(hours=hrs)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"ticket_sla_rules query failed, fallback: {exc}")
    return compute_sla_due_at(p, base=base)


# ---------------------------------------------------------------------------
# 状态机校验
# ---------------------------------------------------------------------------
def is_valid_transition(from_status: str, to_status: str) -> bool:
    """检查状态转移是否合法."""
    if from_status == to_status:
        return True  # no-op
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def assert_valid_transition(from_status: str, to_status: str) -> None:
    if not is_valid_transition(from_status, to_status):
        raise InvalidTransitionError(
            f"非法状态转移: {from_status} → {to_status} "
            f"(允许: {sorted(ALLOWED_TRANSITIONS.get(from_status, set()))})"
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_ticket(
    supabase: Any,
    *,
    user_id: str,
    title: str,
    description: str = "",
    priority: str = "normal",
    category: str = "hr",
    organisation_id: str | None = None,
    assignee_id: str | None = None,
    metadata: dict | None = None,
    tags: list | None = None,
    auto_create: bool = False,
) -> Ticket:
    """创建工单. 返回 Ticket 对象.

    auto_create=True 时,会在 metadata 中标注 source=auto (智能体创建).
    """
    if not title or not title.strip():
        raise TicketError("title 不能为空")
    if priority not in TICKET_PRIORITIES:
        priority = "normal"
    if category not in (
        "hr", "onboarding", "offboarding", "policy", "payroll",
        "benefits", "training", "complaint", "it", "other",
    ):
        category = "hr"

    md = dict(metadata or {})
    if auto_create:
        md.setdefault("source", "auto")

    # 1. 计算 SLA 截止时间
    sla_dt = compute_sla_due_from_rules(supabase, priority)
    sla_due_at = sla_dt.isoformat()

    record = {
        "user_id": user_id,
        "organisation_id": organisation_id,
        "title": title.strip(),
        "description": description,
        "status": "open",
        "priority": priority,
        "category": category,
        "assignee_id": assignee_id,
        "metadata": md,
        "tags": tags or [],
        "sla_due_at": sla_due_at,
    }

    result = supabase.table("tickets").insert(record).execute()
    if not result.data:
        raise TicketError("插入工单失败: 返回为空")
    row = result.data[0] if isinstance(result.data, list) else result.data

    # 2. 写入初始状态历史
    try:
        supabase.table("ticket_status_history").insert({
            "ticket_id": row["id"],
            "from_status": None,
            "to_status": "open",
            "changed_by": user_id,
            "reason": "auto_create" if auto_create else "user_create",
            "metadata": md,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"写入初始状态历史失败: {exc}")

    return Ticket.from_row(row)


def get_ticket(supabase: Any, ticket_id: str) -> Ticket | None:
    """按 ID 取工单."""
    result = (
        supabase.table("tickets")
        .select("*")
        .eq("id", ticket_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    return Ticket.from_row(result.data)


def list_tickets(
    supabase: Any,
    *,
    user_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """列出工单 (HR/管理员用)."""
    q = (
        supabase.table("tickets")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + max(limit - 1, 0))
    )
    if user_id:
        q = q.eq("user_id", user_id)
    if status:
        q = q.eq("status", status)
    if priority:
        q = q.eq("priority", priority)
    if assignee_id:
        q = q.eq("assignee_id", assignee_id)
    result = q.execute()
    return list(result.data or [])


def list_my_tickets(
    supabase: Any,
    user_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """员工查自己的工单."""
    q = (
        supabase.table("tickets")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + max(limit - 1, 0))
    )
    if status:
        q = q.eq("status", status)
    result = q.execute()
    return list(result.data or [])


def update_ticket_meta(
    supabase: Any,
    ticket_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    assignee_id: str | None = None,
    tags: list | None = None,
) -> Ticket:
    """更新工单元数据 (非状态字段)."""
    patch: dict[str, Any] = {}
    if title is not None:
        if not title.strip():
            raise TicketError("title 不能为空")
        patch["title"] = title.strip()
    if description is not None:
        patch["description"] = description
    if priority is not None:
        if priority not in TICKET_PRIORITIES:
            raise TicketError(f"非法 priority: {priority}")
        patch["priority"] = priority
    if category is not None:
        patch["category"] = category
    if assignee_id is not None:
        patch["assignee_id"] = assignee_id
    if tags is not None:
        patch["tags"] = tags
    if not patch:
        # 无修改,直接返回当前
        existing = get_ticket(supabase, ticket_id)
        if not existing:
            raise TicketError(f"工单不存在: {ticket_id}")
        return existing

    result = (
        supabase.table("tickets")
        .update(patch)
        .eq("id", ticket_id)
        .execute()
    )
    if not result.data:
        raise TicketError(f"工单不存在: {ticket_id}")
    return Ticket.from_row(result.data[0])


# ---------------------------------------------------------------------------
# 状态转移
# ---------------------------------------------------------------------------
def transition_status(
    supabase: Any,
    ticket_id: str,
    *,
    to_status: str,
    changed_by: str,
    reason: str | None = None,
    assignee_id: str | None = None,
    metadata: dict | None = None,
) -> Ticket:
    """状态机核心: 校验转移合法性 → 更新 tickets → 写 status_history.

    自动维护:
    - first_responded_at: open → in_progress/awaiting_user 时记录
    - resolved_at:  → resolved 时记录
    - closed_at: → closed 时记录
    """
    if to_status not in TICKET_STATUSES:
        raise TicketError(f"非法状态: {to_status}")

    current = get_ticket(supabase, ticket_id)
    if not current:
        raise TicketError(f"工单不存在: {ticket_id}")
    from_status = current.status

    if from_status == to_status:
        return current

    assert_valid_transition(from_status, to_status)

    now = _now_iso()
    patch: dict[str, Any] = {"status": to_status, "updated_at": now}
    if to_status in ("in_progress", "awaiting_user") and not current.first_responded_at:
        patch["first_responded_at"] = now
    if to_status == "resolved":
        patch["resolved_at"] = now
    if to_status == "closed":
        patch["closed_at"] = now
    if assignee_id is not None:
        patch["assignee_id"] = assignee_id

    result = (
        supabase.table("tickets")
        .update(patch)
        .eq("id", ticket_id)
        .execute()
    )
    if not result.data:
        raise TicketError(f"工单更新失败: {ticket_id}")
    new_row = result.data[0]

    # 写状态历史
    try:
        supabase.table("ticket_status_history").insert({
            "ticket_id": ticket_id,
            "from_status": from_status,
            "to_status": to_status,
            "changed_by": changed_by,
            "reason": reason,
            "metadata": metadata or {},
        }).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"写入状态历史失败: {exc}")

    return Ticket.from_row(new_row)


# ---------------------------------------------------------------------------
# 评论
# ---------------------------------------------------------------------------
def add_comment(
    supabase: Any,
    ticket_id: str,
    *,
    author_id: str,
    body: str,
    author_type: str = "employee",
    is_internal: bool = False,
    attachments: list | None = None,
) -> dict:
    """添加评论. 返回评论 dict."""
    if not body or not body.strip():
        raise TicketError("评论内容不能为空")
    if author_type not in ("employee", "hr", "system"):
        author_type = "employee"

    record = {
        "ticket_id": ticket_id,
        "author_id": author_id,
        "author_type": author_type,
        "body": body.strip(),
        "is_internal": is_internal,
        "attachments": attachments or [],
    }
    result = supabase.table("ticket_comments").insert(record).execute()
    if not result.data:
        raise TicketError("评论插入失败")
    return result.data[0] if isinstance(result.data, list) else result.data


def list_comments(supabase: Any, ticket_id: str) -> list[dict]:
    """列出工单评论 (按时间升序)."""
    result = (
        supabase.table("ticket_comments")
        .select("*")
        .eq("ticket_id", ticket_id)
        .order("created_at", desc=False)
        .execute()
    )
    return list(result.data or [])


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
def get_timeline(supabase: Any, ticket_id: str) -> list[dict]:
    """合并 status_history + comments 按时序返回.

    每条元素包含: kind ('status' | 'comment'), at, actor, payload。
    """
    # 1. status history
    hist_result = (
        supabase.table("ticket_status_history")
        .select("*")
        .eq("ticket_id", ticket_id)
        .order("changed_at", desc=False)
        .execute()
    )
    history = list(hist_result.data or [])

    # 2. comments
    comments = list_comments(supabase, ticket_id)

    merged: list[dict] = []
    for h in history:
        merged.append({
            "kind": "status",
            "at": h.get("changed_at"),
            "actor": h.get("changed_by"),
            "payload": {
                "from_status": h.get("from_status"),
                "to_status": h.get("to_status"),
                "reason": h.get("reason"),
                "metadata": h.get("metadata") or {},
            },
        })
    for c in comments:
        merged.append({
            "kind": "comment",
            "at": c.get("created_at"),
            "actor": c.get("author_id"),
            "payload": {
                "body": c.get("body"),
                "author_type": c.get("author_type"),
                "is_internal": c.get("is_internal", False),
            },
        })

    # 按 at 升序
    merged.sort(key=lambda x: (x.get("at") or ""))
    return merged


# ---------------------------------------------------------------------------
# SLA 工具
# ---------------------------------------------------------------------------
def list_overdue_tickets(supabase: Any, limit: int = 50) -> list[dict]:
    """列出逾期未解决的工单 (HR 仪表盘)."""
    now = _now_iso()
    result = (
        supabase.table("tickets")
        .select("*")
        .lt("sla_due_at", now)
        .not_().in_("status", ["resolved", "closed"])
        .order("sla_due_at", desc=False)
        .limit(limit)
        .execute()
    )
    return list(result.data or [])


__all__ = [
    "TICKET_STATUSES",
    "TICKET_PRIORITIES",
    "ALLOWED_TRANSITIONS",
    "DEFAULT_SLA_HOURS",
    "Ticket",
    "TicketError",
    "InvalidTransitionError",
    "is_valid_transition",
    "assert_valid_transition",
    "compute_sla_due_at",
    "compute_sla_due_from_rules",
    "create_ticket",
    "get_ticket",
    "list_tickets",
    "list_my_tickets",
    "update_ticket_meta",
    "transition_status",
    "add_comment",
    "list_comments",
    "get_timeline",
    "list_overdue_tickets",
]