"""HR 工单 REST API (T207).

Endpoints:
    POST   /api/tickets               - 员工创建工单
    GET    /api/tickets               - HR 看所有工单
    GET    /api/tickets/me            - 员工看自己的工单
    PATCH  /api/tickets/{id}/status   - HR/员工推进状态
    POST   /api/tickets/{id}/comments - 添加评论
    GET    /api/tickets/{id}/timeline - 看时间线
    GET    /api/tickets/{id}          - 单条详情 (额外)
    GET    /api/tickets/overdue       - HR 看逾期工单 (额外)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.ticket_service import (
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    TicketError,
    add_comment,
    create_ticket,
    get_ticket,
    get_timeline,
    list_my_tickets,
    list_overdue_tickets,
    list_tickets,
    transition_status,
    update_ticket_meta,
)

logger = logging.getLogger("recruittech.api.tickets")
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    priority: str = Field(default="normal")
    category: str = Field(default="hr")
    assignee_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class TicketStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None
    assignee_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class TicketCommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)
    is_internal: bool = False
    attachments: list = Field(default_factory=list)


class TicketMetaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    assignee_id: Optional[str] = None
    tags: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_author_type(user: CurrentUser) -> str:
    """根据 user.role 决定评论 author_type."""
    if user.role == UserRole.admin:
        return "hr"
    if user.role == UserRole.talent_partner:
        return "hr"
    return "employee"


def _ensure_ticket_or_404(supabase, ticket_id: str) -> dict:
    """取工单或抛 404."""
    t = get_ticket(supabase, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")
    return t.to_dict()


# ---------------------------------------------------------------------------
# POST /api/tickets  - 员工创建工单
# ---------------------------------------------------------------------------
@router.post("")
async def create_ticket_endpoint(
    body: TicketCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """员工创建工单 (任何已登录用户).

    注: HR/管理员也可创建 — 但通常通过此端点的是员工本人。
    """
    supabase = get_supabase_admin()
    try:
        ticket = create_ticket(
            supabase,
            user_id=str(user.id),
            title=body.title,
            description=body.description,
            priority=body.priority,
            category=body.category,
            assignee_id=body.assignee_id,
            tags=body.tags,
            metadata=body.metadata,
        )
    except TicketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ticket": ticket.to_dict(), "success": True}


# ---------------------------------------------------------------------------
# GET /api/tickets  - HR/admin 看所有
# ---------------------------------------------------------------------------
@router.get("")
async def list_tickets_endpoint(
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    assignee_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.admin)),
):
    """列出工单 (HR/管理员视角)."""
    supabase = get_supabase_admin()
    items = list_tickets(
        supabase,
        user_id=user_id,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /api/tickets/me  - 员工看自己的
# ---------------------------------------------------------------------------
@router.get("/me")
async def list_my_tickets_endpoint(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    """员工查自己的工单."""
    supabase = get_supabase_admin()
    items = list_my_tickets(
        supabase,
        str(user.id),
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /api/tickets/overdue  - 逾期工单 (HR 仪表盘)
# ---------------------------------------------------------------------------
@router.get("/overdue")
async def list_overdue_endpoint(
    limit: int = Query(default=50, le=200),
    user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.admin)),
):
    """逾期工单列表 (SLA 已过且未解决/关闭)."""
    supabase = get_supabase_admin()
    items = list_overdue_tickets(supabase, limit=limit)
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# GET /api/tickets/{id}  - 单条详情
# ---------------------------------------------------------------------------
@router.get("/{ticket_id}")
async def get_ticket_endpoint(
    ticket_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取单条工单详情 (创建者本人 / HR / admin 可见)."""
    supabase = get_supabase_admin()
    t = get_ticket(supabase, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")
    # 权限校验: 创建者 / HR / admin
    is_hr_or_admin = user.role in (UserRole.talent_partner, UserRole.admin)
    if not is_hr_or_admin and t.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="无权查看该工单")
    return t.to_dict()


# ---------------------------------------------------------------------------
# PATCH /api/tickets/{id}/status  - 状态推进
# ---------------------------------------------------------------------------
@router.patch("/{ticket_id}/status")
async def update_status_endpoint(
    ticket_id: str,
    body: TicketStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """更新工单状态.

    权限:
    - HR / admin: 可以推进到任意合法状态
    - 员工 (创建者): 只能 resolved → 等待用户回复 / closed 之类的有限转移
    """
    if body.status not in TICKET_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"非法 status: {body.status}; 允许: {list(TICKET_STATUSES)}",
        )

    supabase = get_supabase_admin()
    current = get_ticket(supabase, ticket_id)
    if not current:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")

    is_hr_or_admin = user.role in (UserRole.talent_partner, UserRole.admin)
    is_owner = current.user_id == str(user.id)

    if not is_hr_or_admin and not is_owner:
        raise HTTPException(status_code=403, detail="无权修改该工单")

    try:
        ticket = transition_status(
            supabase,
            ticket_id,
            to_status=body.status,
            changed_by=str(user.id),
            reason=body.reason,
            assignee_id=body.assignee_id,
            metadata=body.metadata,
        )
    except TicketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ticket": ticket.to_dict(), "success": True}


# ---------------------------------------------------------------------------
# PATCH /api/tickets/{id}  - 修改元数据 (title/description/priority/...)
# ---------------------------------------------------------------------------
@router.patch("/{ticket_id}")
async def update_meta_endpoint(
    ticket_id: str,
    body: TicketMetaUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """更新工单元数据 (非状态字段).

    权限: HR/admin 全权; 创建者本人仅可改 title/description/priority/category。
    """
    supabase = get_supabase_admin()
    current = get_ticket(supabase, ticket_id)
    if not current:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")

    is_hr_or_admin = user.role in (UserRole.talent_partner, UserRole.admin)
    is_owner = current.user_id == str(user.id)
    if not is_hr_or_admin and not is_owner:
        raise HTTPException(status_code=403, detail="无权修改该工单")

    # 员工不能改 assignee_id / tags (HR 字段)
    if not is_hr_or_admin:
        if body.assignee_id is not None or body.tags is not None:
            raise HTTPException(
                status_code=403,
                detail="无权修改 assignee_id / tags (需 HR/管理员)",
            )

    if body.priority is not None and body.priority not in TICKET_PRIORITIES:
        raise HTTPException(
            status_code=400,
            detail=f"非法 priority: {body.priority}",
        )

    try:
        ticket = update_ticket_meta(
            supabase,
            ticket_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            category=body.category,
            assignee_id=body.assignee_id,
            tags=body.tags,
        )
    except TicketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ticket": ticket.to_dict(), "success": True}


# ---------------------------------------------------------------------------
# POST /api/tickets/{id}/comments  - 添加评论
# ---------------------------------------------------------------------------
@router.post("/{ticket_id}/comments")
async def add_comment_endpoint(
    ticket_id: str,
    body: TicketCommentCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """添加评论.

    权限:
    - 创建者本人 / HR / admin: 可以评论
    - 评论 author_type 自动按角色判定 (employee / hr)
    """
    supabase = get_supabase_admin()
    current = get_ticket(supabase, ticket_id)
    if not current:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")

    is_hr_or_admin = user.role in (UserRole.talent_partner, UserRole.admin)
    is_owner = current.user_id == str(user.id)
    if not is_hr_or_admin and not is_owner:
        raise HTTPException(status_code=403, detail="无权评论该工单")

    # 内部标记 (is_internal=True) 仅 HR/管理员可见
    is_internal = body.is_internal and is_hr_or_admin

    author_type = _resolve_author_type(user)
    try:
        comment = add_comment(
            supabase,
            ticket_id,
            author_id=str(user.id),
            body=body.body,
            author_type=author_type,
            is_internal=is_internal,
            attachments=body.attachments,
        )
    except TicketError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"comment": comment, "success": True}


# ---------------------------------------------------------------------------
# GET /api/tickets/{id}/timeline  - 时间线
# ---------------------------------------------------------------------------
@router.get("/{ticket_id}/timeline")
async def get_timeline_endpoint(
    ticket_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取工单时间线 (状态流转 + 评论合并)."""
    supabase = get_supabase_admin()
    current = get_ticket(supabase, ticket_id)
    if not current:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")

    is_hr_or_admin = user.role in (UserRole.talent_partner, UserRole.admin)
    is_owner = current.user_id == str(user.id)
    if not is_hr_or_admin and not is_owner:
        raise HTTPException(status_code=403, detail="无权查看该工单")

    timeline = get_timeline(supabase, ticket_id)
    # 员工只看非 internal 评论
    if not is_hr_or_admin:
        timeline = [
            t for t in timeline
            if not (
                t.get("kind") == "comment"
                and t.get("payload", {}).get("is_internal")
            )
        ]
    return {
        "ticket_id": ticket_id,
        "events": timeline,
        "count": len(timeline),
    }


__all__ = ["router"]