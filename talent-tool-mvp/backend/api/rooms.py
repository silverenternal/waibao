"""Collaboration Room REST API (T608).

11 个 endpoints (列表/房间/成员/消息/反应/已读):
    GET    /api/rooms                        - 我参与的房间列表
    POST   /api/rooms                        - 创建房间
    GET    /api/rooms/{id}                   - 房间详情 (含成员)
    PATCH  /api/rooms/{id}                   - 修改/归档房间
    POST   /api/rooms/{id}/members           - 邀请成员
    DELETE /api/rooms/{id}/members/{user_id} - 移除成员 (主动/踢人)
    GET    /api/rooms/{id}/messages          - 主对话流分页
    POST   /api/rooms/{id}/messages          - 发消息 (支持 thread parent)
    PATCH  /api/rooms/{id}/messages/{msg_id} - 编辑
    DELETE /api/rooms/{id}/messages/{msg_id} - 删除 (软删)
    POST   /api/rooms/{id}/messages/{msg_id}/reactions - 切换 emoji
    POST   /api/rooms/{id}/read              - 标记已读
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.collaboration_room import (
    MAX_MESSAGE_LEN,
    MESSAGE_TYPES,
    MessageNotFoundError,
    NotMemberError,
    PermissionDeniedError,
    RoomError,
    add_reaction,
    archive_room,
    create_room,
    delete_message,
    edit_message,
    get_room,
    get_room_with_members,
    get_total_unread_count,
    get_unread_count,
    invite_member,
    leave_room,
    list_messages,
    list_my_mentions,
    list_my_rooms,
    list_pins,
    list_thread_replies,
    mark_mention_read,
    mark_read,
    pin_message,
    post_message,
    search_messages,
    unpin_message,
    update_room,
)

logger = logging.getLogger("recruittech.api.rooms")
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="group")
    organisation_id: Optional[str] = None
    members: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    metadata: Optional[dict] = None
    archived: Optional[bool] = None


class MemberInvite(BaseModel):
    user_id: str
    role: str = Field(default="member")


class ReactionAdd(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LEN)
    message_type: str = Field(default="text")
    parent_id: Optional[str] = None
    mentions: list[str] = Field(default_factory=list)
    mention_offsets: list[dict] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)


class MessageEdit(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LEN)


class ReadMark(BaseModel):
    at: Optional[str] = None


class PinAction(BaseModel):
    message_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_types(type_: str) -> None:
    from services.collaboration_room import ROOM_TYPES
    if type_ not in ROOM_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid room type: {type_}")


def _check_message_type(t: str) -> None:
    if t not in MESSAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid message_type: {t}")


def _handle_room_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotMemberError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, MessageNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RoomError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="internal error")


def get_sb():
    return get_supabase_admin()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_my_rooms_endpoint(
    archived: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
):
    """GET /api/rooms — 我参与的房间列表 (含 last_message + 未读)."""
    sb = get_sb()
    rooms = list_my_rooms(sb, user_id=str(user.id), include_archived=archived)
    return {
        "rooms": rooms,
        "total_unread": get_total_unread_count(sb, user_id=str(user.id)),
    }


@router.post("", status_code=201)
async def create_room_endpoint(
    body: RoomCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """POST /api/rooms — 创建房间."""
    _check_types(body.type)
    sb = get_sb()
    try:
        room = create_room(
            sb,
            organisation_id=body.organisation_id,
            name=body.name,
            type_=body.type,
            created_by=str(user.id),
            members=body.members,
            metadata=body.metadata,
        )
    except RoomError as exc:
        raise _handle_room_error(exc)
    return get_room_with_members(sb, room.id)


@router.get("/{room_id}")
async def get_room_endpoint(
    room_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """GET /api/rooms/{id} — 房间详情 + 成员."""
    sb = get_sb()
    try:
        from services.collaboration_room import _check_member
        _check_member(sb, room_id, str(user.id))
        room = get_room_with_members(sb, room_id)
        room["unread_count"] = get_unread_count(sb, room_id, user_id=str(user.id))
        # 顺手返回置顶消息
        room["pins"] = list_pins(sb, room_id, user_id=str(user.id))
        return room
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)


@router.patch("/{room_id}")
async def patch_room_endpoint(
    room_id: str,
    body: RoomUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """PATCH /api/rooms/{id} — 修改名称/元数据/归档."""
    sb = get_sb()
    try:
        room = update_room(
            sb,
            room_id,
            user_id=str(user.id),
            name=body.name,
            metadata=body.metadata,
            archived=body.archived,
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return room.to_dict()


@router.post("/{room_id}/members", status_code=201)
async def invite_member_endpoint(
    room_id: str,
    body: MemberInvite,
    user: CurrentUser = Depends(get_current_user),
):
    """POST /api/rooms/{id}/members — 邀请成员."""
    sb = get_sb()
    try:
        member = invite_member(
            sb,
            room_id,
            inviter_id=str(user.id),
            invitee_id=body.user_id,
            role=body.role,
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return member.to_dict()


@router.delete("/{room_id}/members/{target_user_id}", status_code=204)
async def remove_member_endpoint(
    room_id: str,
    target_user_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """DELETE /api/rooms/{id}/members/{user_id} — 主动离开或踢人."""
    sb = get_sb()
    try:
        from services.collaboration_room import remove_member
        remove_member(
            sb,
            room_id,
            actor_id=str(user.id),
            target_id=target_user_id,
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return None


@router.get("/{room_id}/messages")
async def list_messages_endpoint(
    room_id: str,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    thread_root_id: Optional[str] = Query(default=None),
    include_thread: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
):
    """GET /api/rooms/{id}/messages?cursor=...&limit=50 — 主对话流分页."""
    sb = get_sb()
    try:
        msgs, next_cursor = list_messages(
            sb,
            room_id,
            user_id=str(user.id),
            cursor=cursor,
            limit=limit,
            thread_root_id=thread_root_id,
            include_thread=include_thread,
        )
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)

    payload = [m.to_dict() for m in msgs]
    return {"messages": payload, "next_cursor": next_cursor}


@router.post("/{room_id}/messages", status_code=201)
async def post_message_endpoint(
    room_id: str,
    body: MessageCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """POST /api/rooms/{id}/messages — 发送消息."""
    _check_message_type(body.message_type)
    sb = get_sb()
    try:
        msg = post_message(
            sb,
            room_id,
            sender_id=str(user.id),
            content=body.content,
            message_type=body.message_type,
            parent_id=body.parent_id,
            mentions=body.mentions,
            mention_offsets=body.mention_offsets,
            attachments=body.attachments,
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return msg.to_dict()


@router.patch("/{room_id}/messages/{message_id}")
async def edit_message_endpoint(
    room_id: str,
    message_id: str,
    body: MessageEdit,
    user: CurrentUser = Depends(get_current_user),
):
    """PATCH /api/rooms/{id}/messages/{msg_id} — 编辑消息."""
    sb = get_sb()
    try:
        msg = edit_message(
            sb,
            room_id,
            message_id,
            editor_id=str(user.id),
            content=body.content,
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return msg.to_dict()


@router.delete("/{room_id}/messages/{message_id}", status_code=204)
async def delete_message_endpoint(
    room_id: str,
    message_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """DELETE /api/rooms/{id}/messages/{msg_id} — 软删消息."""
    sb = get_sb()
    try:
        delete_message(
            sb,
            room_id,
            message_id,
            actor_id=str(user.id),
        )
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)
    return None


@router.post("/{room_id}/messages/{message_id}/reactions", status_code=201)
async def react_message_endpoint(
    room_id: str,
    message_id: str,
    body: ReactionAdd,
    user: CurrentUser = Depends(get_current_user),
):
    """POST /api/rooms/{id}/messages/{msg_id}/reactions — 切换 emoji."""
    sb = get_sb()
    try:
        reaction = add_reaction(
            sb,
            room_id,
            message_id,
            user_id=str(user.id),
            emoji=body.emoji,
        )
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)
    return {
        "message_id": reaction.message_id,
        "user_id": reaction.user_id,
        "emoji": reaction.emoji,
        "active": bool(reaction.created_at),
    }


@router.post("/{room_id}/read", status_code=204)
async def mark_read_endpoint(
    room_id: str,
    body: ReadMark | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """POST /api/rooms/{id}/read — 标记已读."""
    sb = get_sb()
    at = body.at if body else None
    try:
        mark_read(sb, room_id, user_id=str(user.id), at=at)
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)
    return None


# ---------------------------------------------------------------------------
# 扩展: pin / unpin / thread / search / mentions (辅助端点, 仍属 REST)
# ---------------------------------------------------------------------------

@router.post("/{room_id}/pin")
async def pin_endpoint(
    room_id: str,
    body: PinAction,
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    try:
        return pin_message(sb, room_id, body.message_id, user_id=str(user.id))
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)


@router.post("/{room_id}/unpin")
async def unpin_endpoint(
    room_id: str,
    body: PinAction,
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    try:
        return unpin_message(sb, room_id, body.message_id, user_id=str(user.id))
    except (RoomError, NotMemberError, PermissionDeniedError) as exc:
        raise _handle_room_error(exc)


@router.get("/{room_id}/threads/{parent_id}")
async def thread_replies_endpoint(
    room_id: str,
    parent_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    try:
        msgs = list_thread_replies(sb, room_id, parent_id, user_id=str(user.id))
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)
    return {"messages": [m.to_dict() for m in msgs]}


@router.get("/{room_id}/search")
async def search_endpoint(
    room_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    try:
        msgs = search_messages(sb, room_id, user_id=str(user.id), query=q, limit=limit)
    except (RoomError, NotMemberError) as exc:
        raise _handle_room_error(exc)
    return {"messages": [m.to_dict() for m in msgs]}


@router.get("/me/mentions")
async def list_my_mentions_endpoint(
    unread_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    rows = list_my_mentions(sb, user_id=str(user.id), unread_only=unread_only, limit=limit)
    return {"mentions": rows}


@router.post("/me/mentions/{mention_id}/read", status_code=204)
async def mark_mention_read_endpoint(
    mention_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    sb = get_sb()
    mark_mention_read(sb, mention_id, user_id=str(user.id))
    return None
