"""Collaboration Room 服务 (T608).

职责链路:
    create_room()         -> 创建房间 + 自动添加 owner
    invite_member()       -> 直接添加成员 / 生成邀请
    leave_room()          -> 标记 left_at
    archive_room()        -> 软删
    post_message()        -> 写消息 + 解析 mentions + 触发 mention 通知
    edit_message()        -> 修改, 写 edited_at
    delete_message()      -> 软删, 写 deleted_at
    add_reaction()        -> 表情回应 (toggle)
    pin_message()         -> 置顶消息
    unpin_message()
    mark_read()           -> 更新 last_read_at
    get_unread_count()    -> 计算 last_read_at 之后的消息数
    search_messages()     -> 全文搜索 + scope (room/all)
    list_thread_replies() -> 列出线程回复
    get_room_with_members() -> join 房间详情

设计:
- 所有函数接受 supabase client (默认 admin) 作为第一参数, 方便单测注入 fake client
- mentions 解析使用正则 `@<UUID>` 在服务端做 (UUID-only 简单方案)
- @mention offsets 由前端写过来保证渲染精度; 服务端只校验 mentions[] 包含的 UUID
- 错误: RoomError / NotMemberError / MessageNotFoundError
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from services.platform.errors import swallow  # T5002: typed collapse of best-effort errors

logger = logging.getLogger("recruittech.services.collaboration_room")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROOM_TYPES = ("direct", "group", "topic", "project")
ROOM_MEMBER_ROLES = ("owner", "admin", "member", "guest")
MESSAGE_TYPES = ("text", "markdown", "file", "system")

# 内容长度限制
MAX_MESSAGE_LEN = 20_000
MAX_NAME_LEN = 200
MAX_REACTIONS_PER_MESSAGE = 32

# mention 正则 — UUID 形式
_MENTION_RE = re.compile(r"@([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


# ---------------------------------------------------------------------------
# 错误
# ---------------------------------------------------------------------------

class RoomError(Exception):
    """房间相关错误的基类."""


class NotMemberError(RoomError):
    """用户不是房间成员."""


class MessageNotFoundError(RoomError):
    """消息不存在."""


class PermissionDeniedError(RoomError):
    """权限不足."""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Room:
    id: str
    organisation_id: str | None
    name: str
    type: str
    created_by: str | None
    created_at: str
    last_message_at: str | None
    archived: bool
    metadata: dict
    member_count: int

    @classmethod
    def from_row(cls, row: dict) -> "Room":
        return cls(
            id=row["id"],
            organisation_id=row.get("organisation_id"),
            name=row.get("name", ""),
            type=row.get("type", "group"),
            created_by=row.get("created_by"),
            created_at=row.get("created_at", ""),
            last_message_at=row.get("last_message_at"),
            archived=bool(row.get("archived", False)),
            metadata=row.get("metadata") or {},
            member_count=row.get("member_count", 0) or 0,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organisation_id": self.organisation_id,
            "name": self.name,
            "type": self.type,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "last_message_at": self.last_message_at,
            "archived": self.archived,
            "metadata": self.metadata,
            "member_count": self.member_count,
        }


@dataclass(slots=True)
class RoomMember:
    room_id: str
    user_id: str
    role: str
    joined_at: str
    left_at: str | None
    last_read_at: str | None
    muted: bool

    @classmethod
    def from_row(cls, row: dict) -> "RoomMember":
        return cls(
            room_id=row["room_id"],
            user_id=row["user_id"],
            role=row.get("role", "member"),
            joined_at=row.get("joined_at", ""),
            left_at=row.get("left_at"),
            last_read_at=row.get("last_read_at"),
            muted=bool(row.get("muted", False)),
        )

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at,
            "left_at": self.left_at,
            "last_read_at": self.last_read_at,
            "muted": self.muted,
        }


@dataclass(slots=True)
class RoomMessage:
    id: str
    room_id: str
    sender_id: str
    content: str
    message_type: str
    parent_id: str | None
    mentions: list[str]
    mention_offsets: list[dict]
    attachments: list[dict]
    edited_at: str | None
    deleted_at: str | None
    created_at: str
    thread_root_id: str | None

    @classmethod
    def from_row(cls, row: dict) -> "RoomMessage":
        return cls(
            id=row["id"],
            room_id=row["room_id"],
            sender_id=row["sender_id"],
            content=row.get("content", ""),
            message_type=row.get("message_type", "text"),
            parent_id=row.get("parent_id"),
            mentions=row.get("mentions") or [],
            mention_offsets=row.get("mention_offsets") or [],
            attachments=row.get("attachments") or [],
            edited_at=row.get("edited_at"),
            deleted_at=row.get("deleted_at"),
            created_at=row.get("created_at", ""),
            thread_root_id=row.get("thread_root_id"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "message_type": self.message_type,
            "parent_id": self.parent_id,
            "mentions": self.mentions,
            "mention_offsets": self.mention_offsets,
            "attachments": self.attachments,
            "edited_at": self.edited_at,
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "thread_root_id": self.thread_root_id,
        }

    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(slots=True)
class RoomReaction:
    message_id: str
    user_id: str
    emoji: str
    created_at: str

    @classmethod
    def from_row(cls, row: dict) -> "RoomReaction":
        return cls(
            message_id=row["message_id"],
            user_id=row["user_id"],
            emoji=row["emoji"],
            created_at=row.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# 工具 — members 守护
# ---------------------------------------------------------------------------

def _check_member(supabase, room_id: str, user_id: str, *, require_active: bool = True) -> None:
    """检查用户是不是房间成员, 否则 raise NotMemberError."""
    q = supabase.table("room_members").select("left_at").eq("room_id", room_id).eq("user_id", user_id)
    res = q.execute()
    rows = (res.data or [])
    if not rows:
        raise NotMemberError(f"user {user_id} not in room {room_id}")
    if require_active and rows[0].get("left_at"):
        raise NotMemberError(f"user {user_id} left room {room_id}")


def _check_admin(supabase, room_id: str, user_id: str) -> None:
    """检查用户是不是房间 admin/owner."""
    res = (
        supabase.table("room_members")
        .select("role, left_at")
        .eq("room_id", room_id)
        .eq("user_id", user_id)
        .execute()
    )
    rows = (res.data or [])
    if not rows or rows[0].get("left_at"):
        raise NotMemberError(f"user {user_id} not in room {room_id}")
    role = rows[0].get("role")
    if role not in ("owner", "admin"):
        raise PermissionDeniedError(f"user {user_id} is not admin/owner of room {room_id}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_mentions(content: str) -> tuple[list[str], list[dict]]:
    """从消息文本里解析 @mention (UUID 形式).

    返回 (mentions: [uuid], offsets: [{user_id, start, end}])
    """
    mentions: list[str] = []
    offsets: list[dict] = []
    seen: set[str] = set()
    for m in _MENTION_RE.finditer(content):
        uid = m.group(1)
        if uid in seen:
            continue
        seen.add(uid)
        mentions.append(uid)
        offsets.append({"user_id": uid, "start": m.start(), "end": m.end()})
    return mentions, offsets


# ---------------------------------------------------------------------------
# Room CRUD
# ---------------------------------------------------------------------------

def create_room(
    supabase,
    *,
    organisation_id: Optional[str] = None,
    name: str,
    type_: str = "group",
    created_by: str,
    members: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> Room:
    """创建房间并把 created_by 作为 owner; members 列表 (默认只 owner)."""
    if type_ not in ROOM_TYPES:
        raise RoomError(f"invalid room type: {type_}")
    if not name or len(name) > MAX_NAME_LEN:
        raise RoomError(f"name length must be 1..{MAX_NAME_LEN}")

    # 1) insert room
    room_res = supabase.table("rooms").insert({
        "organisation_id": organisation_id,
        "name": name,
        "type": type_,
        "created_by": created_by,
        "archived": False,
        "metadata": metadata or {},
    }).execute()
    if not room_res.data:
        raise RoomError("failed to insert room")
    room_id = room_res.data[0]["id"]

    # 2) 加 owner (created_by)
    member_rows: list[dict] = [
        {
            "room_id": room_id,
            "user_id": created_by,
            "role": "owner",
            "joined_at": _now_iso(),
        }
    ]

    # 3) 加其他成员
    if members:
        seen = {created_by}
        for uid in members:
            if uid in seen:
                continue
            seen.add(uid)
            member_rows.append({
                "room_id": room_id,
                "user_id": uid,
                "role": "member",
                "joined_at": _now_iso(),
                "invited_by": created_by,
            })

    supabase.table("room_members").insert(member_rows).execute()

    # T1808: 指标采集
    try:
        from services.observability.collab_metrics import get_collab_metrics
        m = get_collab_metrics()
        m.room_created(room_id, organisation_id, type_)
        for _ in member_rows[1:]:
            m.member_added(room_id)
    except Exception:  # noqa: BLE001
        pass

    return get_room(supabase, room_id)


def get_room(supabase, room_id: str) -> Room:
    res = supabase.table("rooms").select("*").eq("id", room_id).execute()
    if not res.data:
        raise RoomError(f"room {room_id} not found")
    return Room.from_row(res.data[0])


def get_room_with_members(supabase, room_id: str) -> dict:
    """返回 room + member 列表 + 当前用户 last_read_at."""
    room = get_room(supabase, room_id).to_dict()
    mem_res = (
        supabase.table("room_members")
        .select("user_id, role, joined_at, left_at, last_read_at, muted, invitation_pending")
        .eq("room_id", room_id)
        .is_("left_at", "null")
        .order("joined_at")
        .execute()
    )
    room["members"] = mem_res.data or []
    return room


def list_my_rooms(
    supabase,
    *,
    user_id: str,
    organisation_id: Optional[str] = None,
    include_archived: bool = False,
    batch_unread: bool = True,
) -> list[dict]:
    """列出用户参与的房间 (含 last_message + 未读).

    T1808 性能优化:
      - 默认 batch_unread=True: 单次 in-list query 拿所有 room 未读 (避免 N+1).
      - 批量路径下 DB 查询次数从 N 降到 1.
      - 老 API 行为完全保留 (batch_unread=False 时回退到逐个 query).
    """
    # 1) 拿用户全部 active room_ids
    q = (
        supabase.table("room_members")
        .select("room_id, last_read_at")
        .eq("user_id", user_id)
        .is_("left_at", "null")
    )
    res = q.execute()
    rows = res.data or []
    room_ids = [r["room_id"] for r in rows]
    read_map = {r["room_id"]: r.get("last_read_at") for r in rows}
    if not room_ids:
        return []

    # 2) 拿 rooms
    q2 = supabase.table("rooms").select("*").in_("id", room_ids)
    if not include_archived:
        q2 = q2.eq("archived", False)
    if organisation_id is not None:
        q2 = q2.eq("organisation_id", organisation_id)
    rooms_res = q2.order("last_message_at", desc=True, nullsfirst=False).execute()
    rooms_data = rooms_res.data or []

    # 3) 批量查 unread (T1808) 或逐个查 (fallback)
    if batch_unread and rooms_data:
        try:
            room_ids_kept = [r["id"] for r in rooms_data]
            unread_map = _count_unread_batch(
                supabase, room_ids=room_ids_kept,
                last_read_at_map=read_map, user_id=user_id,
            )
        except Exception:  # noqa: BLE001 - 退化到逐个 query
            unread_map = {}
    else:
        unread_map = {}

    out: list[dict] = []
    for r in rooms_data:
        d = Room.from_row(r).to_dict()
        d["last_read_at"] = read_map.get(d["id"])
        if d["id"] in unread_map:
            d["unread_count"] = unread_map[d["id"]]
        else:
            # 退化: 单 room query
            d["unread_count"] = _count_unread_for_room(
                supabase, room_id=d["id"], last_read_at=d["last_read_at"],
                user_id=user_id,
            )
        out.append(d)
    return out


def _count_unread_for_room(
    supabase,
    room_id: str,
    last_read_at: Optional[str],
    user_id: Optional[str] = None,
) -> int:
    """计算 room 中 last_read_at 之后的消息数 (主对话流, 排除 user 自身).

    user_id 提供时, 用 neq 排除自己发的消息, 避免自己私聊自己显示未读.
    """
    q = supabase.table("room_messages").select("id", count="exact").eq("room_id", room_id).is_("deleted_at", "null").is_("parent_id", "null")
    if last_read_at:
        q = q.gt("created_at", last_read_at)
    if user_id:
        q = q.neq("sender_id", user_id)
    res = q.execute()
    return int(res.count or 0)


def _count_unread_batch(
    supabase,
    room_ids: list[str],
    last_read_at_map: dict[str, Optional[str]],
    user_id: str,
) -> dict[str, int]:
    """T1808 性能优化: 批量查询多个 room 的未读数.

    原 list_my_rooms 每个 room 一次 query, N+1 问题.
    此处用单次 RPC 或 in-list query 替代:
      1) 先取所有 room 中 last_read_at 之后的主对话流消息 (按 room_id group)
      2) 排除 user 自己发的
    返回 {room_id: unread_count}.

    实现: 一次 in-list query, 取必要字段, 在内存中 group by room_id.
    """
    if not room_ids:
        return {}
    # 性能关键: 选择最晚的 last_read_at 作为基线 (即"想看全部没读"=空, 全部想读=最早)
    # 但每个 room 的 last_read_at 不同, 需要 in-memory 过滤.
    res = (
        supabase.table("room_messages")
        .select("room_id, created_at, sender_id")
        .in_("room_id", room_ids)
        .is_("deleted_at", "null")
        .is_("parent_id", "null")
        .neq("sender_id", user_id)
        .execute()
    )
    rows = res.data or []
    counts: dict[str, int] = {rid: 0 for rid in room_ids}
    for r in rows:
        rid = r["room_id"]
        last_read = last_read_at_map.get(rid)
        if last_read and r["created_at"] <= last_read:
            continue
        counts[rid] = counts.get(rid, 0) + 1
    return counts


def update_room(
    supabase,
    room_id: str,
    *,
    user_id: str,
    name: Optional[str] = None,
    metadata: Optional[dict] = None,
    archived: Optional[bool] = None,
) -> Room:
    _check_admin(supabase, room_id, user_id)
    payload: dict[str, Any] = {}
    if name is not None:
        if not name or len(name) > MAX_NAME_LEN:
            raise RoomError(f"name length must be 1..{MAX_NAME_LEN}")
        payload["name"] = name
    if metadata is not None:
        payload["metadata"] = metadata
    if archived is not None:
        payload["archived"] = bool(archived)
        payload["archived_at"] = _now_iso() if archived else None
    if not payload:
        return get_room(supabase, room_id)
    supabase.table("rooms").update(payload).eq("id", room_id).execute()
    return get_room(supabase, room_id)


def archive_room(supabase, room_id: str, *, user_id: str) -> Room:
    return update_room(supabase, room_id, user_id=user_id, archived=True)


# ---------------------------------------------------------------------------
# 成员
# ---------------------------------------------------------------------------

def invite_member(
    supabase,
    room_id: str,
    *,
    inviter_id: str,
    invitee_id: str,
    role: str = "member",
) -> RoomMember:
    """邀请/添加成员. 重复邀请时返回现有记录, 不重复插入."""
    if role not in ROOM_MEMBER_ROLES:
        raise RoomError(f"invalid role: {role}")

    # inviter 权限: admin/owner 才能邀请他人 (邀请自己直接接受)
    if inviter_id != invitee_id:
        _check_admin(supabase, room_id, inviter_id)
    else:
        _check_member(supabase, room_id, inviter_id, require_active=False)

    # 已有记录?
    existing = (
        supabase.table("room_members")
        .select("*")
        .eq("room_id", room_id)
        .eq("user_id", invitee_id)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        if row.get("left_at"):
            # 重新加入
            upd = supabase.table("room_members").update({
                "left_at": None,
                "role": role,
                "invited_by": inviter_id,
                "invitation_pending": False,
            }).eq("room_id", room_id).eq("user_id", invitee_id).execute()
            return RoomMember.from_row(upd.data[0])
        return RoomMember.from_row(row)

    ins = supabase.table("room_members").insert({
        "room_id": room_id,
        "user_id": invitee_id,
        "role": role,
        "joined_at": _now_iso(),
        "invited_by": inviter_id,
    }).execute()
    if not ins.data:
        raise RoomError("failed to insert member")
    # T1808: metrics
    try:
        from services.observability.collab_metrics import get_collab_metrics
        get_collab_metrics().member_added(room_id)
    except Exception:  # noqa: BLE001
        pass
    return RoomMember.from_row(ins.data[0])


def remove_member(supabase, room_id: str, *, actor_id: str, target_id: str) -> None:
    """Actor 主动离开/踢人.

    - 主动离开: target_id == actor_id
    - 踢人: actor 必须是 admin/owner
    - owner 不能离开 (除非 transfer ownership)
    """
    if target_id != actor_id:
        _check_admin(supabase, room_id, actor_id)

    mem = (
        supabase.table("room_members")
        .select("role, left_at")
        .eq("room_id", room_id)
        .eq("user_id", target_id)
        .execute()
    )
    rows = (mem.data or [])
    if not rows:
        raise NotMemberError(f"user {target_id} not in room {room_id}")
    if rows[0].get("left_at"):
        return  # 已经离开, 幂等

    if rows[0].get("role") == "owner" and target_id == actor_id:
        raise PermissionDeniedError("owner cannot leave without transfer")

    supabase.table("room_members").update({
        "left_at": _now_iso(),
    }).eq("room_id", room_id).eq("user_id", target_id).execute()


def leave_room(supabase, room_id: str, *, user_id: str) -> None:
    remove_member(supabase, room_id, actor_id=user_id, target_id=user_id)


def list_members(supabase, room_id: str) -> list[RoomMember]:
    res = (
        supabase.table("room_members")
        .select("*")
        .eq("room_id", room_id)
        .is_("left_at", "null")
        .order("joined_at")
        .execute()
    )
    return [RoomMember.from_row(r) for r in (res.data or [])]


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------

def post_message(
    supabase,
    room_id: str,
    *,
    sender_id: str,
    content: str,
    message_type: str = "text",
    parent_id: Optional[str] = None,
    mentions: Optional[list[str]] = None,
    mention_offsets: Optional[list[dict]] = None,
    attachments: Optional[list[dict]] = None,
) -> RoomMessage:
    """发送消息, 自动解析 mentions 并写入 room_mentions."""
    # T1808: metrics 集成
    from services.observability.collab_metrics import track_post_message

    if message_type not in MESSAGE_TYPES:
        raise RoomError(f"invalid message_type: {message_type}")
    if message_type == "text" and (not content or len(content) > MAX_MESSAGE_LEN):
        raise RoomError(f"text length must be 1..{MAX_MESSAGE_LEN}")

    _check_member(supabase, room_id, sender_id)

    # parent_id 必须也是同 room 的消息
    if parent_id:
        parent_res = (
            supabase.table("room_messages")
            .select("id, room_id")
            .eq("id", parent_id)
            .execute()
        )
        if not parent_res.data or parent_res.data[0].get("room_id") != room_id:
            raise RoomError("parent message not in room")
        # 只允许两层 (thread: parent 必须本身没有 parent)
        if parent_res.data[0].get("id") and _message_has_parent(supabase, parent_id):
            raise RoomError("thread depth exceeded (max 2)")

    # 解析 mentions
    parsed_mentions, parsed_offsets = _parse_mentions(content)
    final_mentions = list(set((mentions or []) + parsed_mentions))
    final_offsets = list(mention_offsets or []) + parsed_offsets

    insert_payload: dict[str, Any] = {
        "room_id": room_id,
        "sender_id": sender_id,
        "content": content,
        "message_type": message_type,
        "parent_id": parent_id,
        "mentions": final_mentions,
        "mention_offsets": final_offsets,
        "attachments": attachments or [],
    }

    with track_post_message(mentions=len(final_mentions)):
        res = supabase.table("room_messages").insert(insert_payload).execute()
        if not res.data:
            raise RoomError("failed to insert message")
        msg = RoomMessage.from_row(res.data[0])

        # 写 room_mentions 通知
        if msg.mentions:
            # 校验 mentions 都是 active 成员
            members = list_members(supabase, room_id)
            active_ids = {m.user_id for m in members}
            valid = [uid for uid in msg.mentions if uid in active_ids]
            if valid:
                mention_rows = [
                    {"user_id": uid, "room_id": room_id, "message_id": msg.id}
                    for uid in valid
                ]
                # T5002: best-effort mention fan-out — never let a notification
                # write failure abort the message insert.
                from services.platform.errors import safe_call
                safe_call(
                    lambda: supabase.table("room_mentions").insert(mention_rows).execute(),
                    log=logger, message="failed to write room_mentions",
                )

        return msg


def _message_has_parent(supabase, message_id: str) -> bool:
    res = (
        supabase.table("room_messages")
        .select("parent_id")
        .eq("id", message_id)
        .execute()
    )
    if not res.data:
        return False
    return res.data[0].get("parent_id") is not None


def edit_message(
    supabase,
    room_id: str,
    message_id: str,
    *,
    editor_id: str,
    content: str,
) -> RoomMessage:
    res = (
        supabase.table("room_messages")
        .select("*")
        .eq("id", message_id)
        .eq("room_id", room_id)
        .execute()
    )
    if not res.data:
        raise MessageNotFoundError(f"message {message_id} not in room {room_id}")
    msg = RoomMessage.from_row(res.data[0])
    if msg.sender_id != editor_id:
        raise PermissionDeniedError("only sender can edit message")
    if msg.is_deleted():
        raise PermissionDeniedError("message deleted")
    if not content or len(content) > MAX_MESSAGE_LEN:
        raise RoomError(f"text length must be 1..{MAX_MESSAGE_LEN}")

    new_mentions, new_offsets = _parse_mentions(content)
    supabase.table("room_messages").update({
        "content": content,
        "mentions": new_mentions,
        "mention_offsets": new_offsets,
        "edited_at": _now_iso(),
    }).eq("id", message_id).execute()

    return RoomMessage.from_row(
        supabase.table("room_messages")
        .select("*").eq("id", message_id).execute().data[0]
    )


def delete_message(
    supabase,
    room_id: str,
    message_id: str,
    *,
    actor_id: str,
) -> None:
    res = (
        supabase.table("room_messages")
        .select("sender_id, room_id")
        .eq("id", message_id)
        .execute()
    )
    if not res.data or res.data[0].get("room_id") != room_id:
        raise MessageNotFoundError(f"message {message_id} not in room {room_id}")
    sender = res.data[0].get("sender_id")
    if sender != actor_id:
        _check_admin(supabase, room_id, actor_id)
    supabase.table("room_messages").update({
        "deleted_at": _now_iso(),
        "deleted_by": actor_id,
    }).eq("id", message_id).execute()


def list_messages(
    supabase,
    room_id: str,
    *,
    user_id: str,
    cursor: Optional[str] = None,
    limit: int = 50,
    thread_root_id: Optional[str] = None,
    include_thread: bool = False,
) -> tuple[list[RoomMessage], Optional[str]]:
    """分页主对话流消息 (parent_id IS NULL 当 thread_root_id 缺省; 含线程根).

    返回 (messages, next_cursor)
    """
    from services.observability.collab_metrics import track_list_messages
    _check_member(supabase, room_id, user_id)

    with track_list_messages():
        q = (
            supabase.table("room_messages")
            .select("*")
            .eq("room_id", room_id)
        )

        if thread_root_id:
            q = q.eq("thread_root_id", thread_root_id)
        elif not include_thread:
            # 主对话流: 仅 parent IS NULL
            q = q.is_("parent_id", "null")

        if cursor:
            q = q.lt("created_at", cursor)

        q = q.order("created_at", desc=True).limit(limit)
        res = q.execute()

        msgs = [RoomMessage.from_row(r) for r in (res.data or [])]
        next_cursor = msgs[-1].created_at if len(msgs) == limit else None
        msgs.reverse()  # 前端期望时间正序
        return msgs, next_cursor


def list_thread_replies(
    supabase,
    room_id: str,
    parent_message_id: str,
    *,
    user_id: str,
) -> list[RoomMessage]:
    _check_member(supabase, room_id, user_id)
    res = (
        supabase.table("room_messages")
        .select("*")
        .eq("room_id", room_id)
        .eq("parent_id", parent_message_id)
        .is_("deleted_at", "null")
        .order("created_at")
        .execute()
    )
    return [RoomMessage.from_row(r) for r in (res.data or [])]


def search_messages(
    supabase,
    room_id: str,
    *,
    user_id: str,
    query: str,
    limit: int = 50,
) -> list[RoomMessage]:
    """全文搜索房间内消息 (to_tsvector)."""
    from services.observability.collab_metrics import track_search_messages
    _check_member(supabase, room_id, user_id)
    with track_search_messages():
        res = (
            supabase.table("room_messages")
            .select("*")
            .eq("room_id", room_id)
            .is_("deleted_at", "null")
            .text_search("content", query, config="simple")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [RoomMessage.from_row(r) for r in (res.data or [])]


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

def add_reaction(
    supabase,
    room_id: str,
    message_id: str,
    *,
    user_id: str,
    emoji: str,
) -> RoomReaction:
    """Toggle reaction — 已存在则删除, 反之插入."""
    from services.observability.collab_metrics import get_collab_metrics
    _check_member(supabase, room_id, user_id)
    if not emoji or len(emoji) > 16:
        raise RoomError("invalid emoji")

    # 校验 message 存在
    msg_res = (
        supabase.table("room_messages")
        .select("id, room_id")
        .eq("id", message_id)
        .execute()
    )
    if not msg_res.data or msg_res.data[0].get("room_id") != room_id:
        raise MessageNotFoundError(f"message {message_id} not in room {room_id}")

    # 检查是否已存在
    existing = (
        supabase.table("room_reactions")
        .select("message_id")
        .eq("message_id", message_id)
        .eq("user_id", user_id)
        .eq("emoji", emoji)
        .execute()
    )
    if existing.data:
        supabase.table("room_reactions").delete() \
            .eq("message_id", message_id) \
            .eq("user_id", user_id) \
            .eq("emoji", emoji).execute()
        # 返回"已删除"标记
        return RoomReaction(message_id=message_id, user_id=user_id, emoji=emoji, created_at="")

    supabase.table("room_reactions").insert({
        "message_id": message_id,
        "user_id": user_id,
        "emoji": emoji,
    }).execute()
    # T1808: reaction metric
    get_collab_metrics().reaction_added()
    return RoomReaction(message_id=message_id, user_id=user_id, emoji=emoji, created_at=_now_iso())


def list_reactions(
    supabase,
    message_id: str,
) -> list[RoomReaction]:
    res = supabase.table("room_reactions").select("*").eq("message_id", message_id).execute()
    return [RoomReaction.from_row(r) for r in (res.data or [])]


# ---------------------------------------------------------------------------
# Pin / Unpin
# ---------------------------------------------------------------------------

def pin_message(supabase, room_id: str, message_id: str, *, user_id: str) -> dict:
    _check_admin(supabase, room_id, user_id)
    msg_res = (
        supabase.table("room_messages")
        .select("id, room_id")
        .eq("id", message_id)
        .execute()
    )
    if not msg_res.data or msg_res.data[0].get("room_id") != room_id:
        raise MessageNotFoundError(f"message {message_id} not in room {room_id}")
    # 简化为: 如果已存在则忽略 (幂等), 否则插入
    existing = (
        supabase.table("room_pins")
        .select("room_id")
        .eq("room_id", room_id)
        .eq("message_id", message_id)
        .execute()
    )
    if not existing.data:
        supabase.table("room_pins").insert({
            "room_id": room_id,
            "message_id": message_id,
            "pinned_by": user_id,
        }).execute()
    return {"room_id": room_id, "message_id": message_id, "pinned": True}


def unpin_message(supabase, room_id: str, message_id: str, *, user_id: str) -> dict:
    _check_admin(supabase, room_id, user_id)
    supabase.table("room_pins").delete() \
        .eq("room_id", room_id).eq("message_id", message_id).execute()
    return {"room_id": room_id, "message_id": message_id, "pinned": False}


def list_pins(supabase, room_id: str, *, user_id: str) -> list[dict]:
    _check_member(supabase, room_id, user_id)
    pin_res = (
        supabase.table("room_pins")
        .select("message_id, pinned_by, pinned_at")
        .eq("room_id", room_id)
        .order("pinned_at", desc=True)
        .execute()
    )
    if not pin_res.data:
        return []
    msg_ids = [p["message_id"] for p in pin_res.data]
    msgs = (
        supabase.table("room_messages")
        .select("*")
        .in_("id", msg_ids)
        .execute()
    )
    by_id = {m["id"]: RoomMessage.from_row(m).to_dict() for m in (msgs.data or [])}
    out: list[dict] = []
    for p in pin_res.data:
        msg = by_id.get(p["message_id"])
        if msg:
            out.append({
                "message": msg,
                "pinned_by": p.get("pinned_by"),
                "pinned_at": p.get("pinned_at"),
            })
    return out


# ---------------------------------------------------------------------------
# Read / Unread
# ---------------------------------------------------------------------------

def mark_read(supabase, room_id: str, *, user_id: str, at: Optional[str] = None) -> None:
    """更新 last_read_at. at 默认 now()."""
    from services.observability.collab_metrics import get_collab_metrics, track_mark_read
    _check_member(supabase, room_id, user_id)
    at_iso = at or _now_iso()
    # T1808: 记录 mark_read 时未读数 (用于未读分布统计)
    metrics = get_collab_metrics()
    pre_unread = _count_unread_for_room(supabase, room_id, _get_last_read_at(supabase, room_id, user_id), user_id)
    with track_mark_read(unread_count=pre_unread):
        supabase.table("room_members").update({"last_read_at": at_iso}) \
            .eq("room_id", room_id).eq("user_id", user_id).execute()


def _get_last_read_at(supabase, room_id: str, user_id: str) -> Optional[str]:
    """读取 member 的 last_read_at (供 metrics 用)."""
    def _read() -> Optional[str]:
        res = (
            supabase.table("room_members")
            .select("last_read_at")
            .eq("room_id", room_id)
            .eq("user_id", user_id)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows[0].get("last_read_at")
        return None

    # T5002: typed collapse — best-effort read, default None on failure.
    from services.platform.errors import safe_call
    return safe_call(_read, default=None, log=logger, message="read last_read_at failed")


def get_unread_count(supabase, room_id: str, *, user_id: str) -> int:
    """返回当前未读数 (主对话流, 排除自己发的)."""
    _check_member(supabase, room_id, user_id)
    mem_res = (
        supabase.table("room_members")
        .select("last_read_at")
        .eq("room_id", room_id)
        .eq("user_id", user_id)
        .execute()
    )
    last_read_at = (mem_res.data or [{}])[0].get("last_read_at")
    return _count_unread_for_room(supabase, room_id, last_read_at, user_id=user_id)


def get_total_unread_count(supabase, *, user_id: str) -> int:
    """用户在所有房间的未读总和."""
    rooms = list_my_rooms(supabase, user_id=user_id)
    return sum(r.get("unread_count", 0) for r in rooms)


# ---------------------------------------------------------------------------
# Mention 通知
# ---------------------------------------------------------------------------

def list_my_mentions(
    supabase,
    *,
    user_id: str,
    unread_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    q = (
        supabase.table("room_mentions")
        .select("id, room_id, message_id, read_at, created_at, room_messages:sender_id, room_messages:content")
        .eq("user_id", user_id)
    )
    if unread_only:
        q = q.is_("read_at", "null")
    res = q.order("created_at", desc=True).limit(limit).execute()
    return res.data or []


def mark_mention_read(supabase, mention_id: str, *, user_id: str) -> None:
    supabase.table("room_mentions").update({"read_at": _now_iso()}) \
        .eq("id", mention_id).eq("user_id", user_id).execute()


# T1808: __all__ 让 v5.0 shim 能 re-export 私有辅助函数
__all__ = [
    "ROOM_TYPES", "ROOM_MEMBER_ROLES", "MESSAGE_TYPES",
    "MAX_MESSAGE_LEN", "MAX_NAME_LEN", "MAX_REACTIONS_PER_MESSAGE",
    "RoomError", "NotMemberError", "MessageNotFoundError", "PermissionDeniedError",
    "Room", "RoomMember", "RoomMessage", "RoomReaction",
    "create_room", "get_room", "get_room_with_members", "list_my_rooms",
    "update_room", "archive_room",
    "invite_member", "remove_member", "leave_room", "list_members",
    "post_message", "edit_message", "delete_message",
    "list_messages", "list_thread_replies", "search_messages",
    "add_reaction", "list_reactions",
    "pin_message", "unpin_message", "list_pins",
    "mark_read", "get_unread_count", "get_total_unread_count",
    "list_my_mentions", "mark_mention_read",
    "_check_admin", "_check_member", "_count_unread_for_room", "_count_unread_batch",
    "_parse_mentions", "_now_iso", "_get_last_read_at",
]
