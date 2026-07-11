"""Tests for services.collaboration_room (T608).

覆盖:
    - room CRUD (create / get / update / archive)
    - member flow (invite / remove / leave / list)
    - message flow (post / edit / delete / list / search)
    - thread (post_message with parent_id)
    - mentions 解析 + room_mentions 写入
    - reactions toggle
    - pin / unpin
    - mark_read / get_unread_count
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.collaboration_room import (
    MAX_MESSAGE_LEN,
    NotMemberError,
    PermissionDeniedError,
    RoomError,
    MessageNotFoundError,
    _check_admin,
    _check_member,
    _parse_mentions,
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
    list_members,
    list_messages,
    list_my_rooms,
    list_pins,
    list_reactions,
    list_thread_replies,
    mark_read,
    pin_message,
    post_message,
    remove_member,
    search_messages,
    unpin_message,
    update_room,
)


# ---------------------------------------------------------------------------
# 极简 in-memory supabase fake — 满足本模块用到的链式 API
# ---------------------------------------------------------------------------
class _Q:
    """链式 fake query."""

    def __init__(self, store, table):
        self.s = store
        self.t = table
        self._filters: list[tuple[str, str, object]] = []
        self._not_filters: list[tuple[str, str, object]] = []
        self._order = None
        self._order_desc = False
        self._limit = None
        self._single = False
        self._maybe = False
        self._insert = None
        self._update = None
        self._delete = False
        self._text_search = None

    # -- filters --
    def eq(self, k, v):
        self._filters.append(("eq", k, v))
        return self

    def gt(self, k, v):
        self._filters.append(("gt", k, v))
        return self

    def lt(self, k, v):
        self._filters.append(("lt", k, v))
        return self

    def gte(self, k, v):
        self._filters.append(("gte", k, v))
        return self

    def lte(self, k, v):
        self._filters.append(("lte", k, v))
        return self

    def is_(self, k, v):
        # NB: postgrest .is_() 与 NULL 比较
        self._filters.append(("is", k, v))
        return self

    def neq(self, k, v):
        self._filters.append(("neq", k, v))
        return self

    def in_(self, k, vs):
        self._filters.append(("in", k, tuple(vs)))
        return self

    def ilike(self, k, v):
        self._filters.append(("ilike", k, v))
        return self

    def is_null(self, k):
        # Our Room service uses is_("left_at","null") — handle both
        self._filters.append(("isnull", k, None))
        return self

    def order(self, field, desc=False, **kw):
        self._order = field
        self._order_desc = bool(desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    def text_search(self, k, q, config=None):
        self._text_search = (k, q)
        return self

    def upsert(self, payload, on_conflict=None):
        self._upsert = payload
        return self

    def insert(self, p):
        self._insert = p
        return self

    def update(self, p):
        self._update = p
        return self

    def delete(self):
        self._delete = True
        return self

    def select(self, *_a, **_kw):
        return self

    # -- execution --
    def execute(self):
        return self.s.run(self)


class _Store:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {t: [] for t in (
            "rooms", "room_members", "room_messages", "room_threads",
            "room_reactions", "room_mentions", "room_pins",
        )}
        self._counter = 0

    def add_table(self, name):
        if name not in self.tables:
            self.tables[name] = []

    def new_id(self) -> str:
        self._counter += 1
        return f"uuid-{self._counter:04d}"

    @staticmethod
    def _match(row, ftype, k, v):
        if ftype == "eq":
            return row.get(k) == v
        if ftype == "neq":
            return row.get(k) != v
        if ftype == "is":
            # postgrest .is_("col", "null") => IS NULL
            if v == "null":
                return row.get(k) is None
            return row.get(k) == v
        if ftype == "gt":
            return (row.get(k) or "") > (v or "")
        if ftype == "lt":
            return (row.get(k) or "") < (v or "")
        if ftype == "gte":
            return (row.get(k) or "") >= (v or "")
        if ftype == "lte":
            return (row.get(k) or "") <= (v or "")
        if ftype == "in":
            return row.get(k) in v
        if ftype == "ilike":
            return str(v).strip("%") in str(row.get(k) or "")
        if ftype == "isnull":
            return row.get(k) is None
        return True

    def run(self, q: _Q):
        # INSERT
        if q._insert is not None:
            payload = q._insert
            rows = []
            if isinstance(payload, list):
                for p in payload:
                    p = dict(p)
                    p.setdefault("id", self.new_id())
                    p.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    self.tables.setdefault(q.t, []).append(p)
                    rows.append(p)
            else:
                p = dict(payload)
                p.setdefault("id", self.new_id())
                p.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                self.tables.setdefault(q.t, []).append(p)
                rows = [p]
            return SimpleNamespace(data=rows, count=len(rows))

        # UPDATE
        if q._update is not None:
            updated = []
            for r in list(self.tables.get(q.t, [])):
                if all(self._match(r, f, k, v) for (f, k, v) in q._filters):
                    r.update(q._update)
                    updated.append(dict(r))
            return SimpleNamespace(data=updated, count=len(updated))

        # DELETE
        if q._delete:
            kept = []
            removed = []
            for r in list(self.tables.get(q.t, [])):
                if all(self._match(r, f, k, v) for (f, k, v) in q._filters):
                    removed.append(r)
                else:
                    kept.append(r)
            self.tables[q.t] = kept
            return SimpleNamespace(data=removed, count=len(removed))

        # SELECT
        rows = list(self.tables.get(q.t, []))
        for f, k, v in q._filters:
            rows = [r for r in rows if self._match(r, f, k, v)]
        if q._text_search:
            k, needle = q._text_search
            rows = [r for r in rows if needle.lower() in str(r.get(k, "")).lower()]
        if q._order:
            rows.sort(
                key=lambda r: (r.get(q._order) or ""),
                reverse=q._order_desc,
            )
        if q._limit:
            rows = rows[:q._limit]
        if q._single:
            assert rows, "no row"
            return SimpleNamespace(data=rows[0], count=len(rows))
        if q._maybe:
            return SimpleNamespace(data=rows[0] if rows else None, count=len(rows))
        return SimpleNamespace(data=rows, count=len(rows))


class FakeSB:
    def __init__(self):
        self.s = _Store()
        self._current = None

    def table(self, name):
        self.s.add_table(name)
        return _Q(self.s, name)


@pytest.fixture
def sb():
    return FakeSB()


# ===========================================================================
# 1. mention parsing
# ===========================================================================
class TestMentionParsing:

    def test_parse_no_mention(self):
        m, o = _parse_mentions("hello world")
        assert m == []
        assert o == []

    def test_parse_single_mention(self):
        text = "ping @11111111-2222-3333-4444-555555555555 please"
        m, o = _parse_mentions(text)
        assert m == ["11111111-2222-3333-4444-555555555555"]
        assert len(o) == 1
        assert o[0]["start"] == 5
        assert o[0]["end"] == 5 + 37  # len of @<uuid>

    def test_parse_multi_mentions_unique(self):
        text = "hi @11111111-1111-1111-1111-111111111111 and @22222222-2222-2222-2222-222222222222 and @11111111-1111-1111-1111-111111111111"
        m, _ = _parse_mentions(text)
        assert m == [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]  # 去重

    def test_parse_invalid_uuid_ignored(self):
        m, _ = _parse_mentions("hi @not-a-uuid")
        assert m == []


# ===========================================================================
# 2. Room CRUD
# ===========================================================================
class TestRoomCRUD:

    def test_create_room_minimal(self, sb):
        r = create_room(
            sb,
            organisation_id=None,
            name="Test Room",
            type_="group",
            created_by="user-1",
        )
        assert r.name == "Test Room"
        assert r.type == "group"
        assert r.created_by == "user-1"

        # 创建者自动是 owner
        members = list_members(sb, r.id)
        assert len(members) == 1
        assert members[0].user_id == "user-1"
        assert members[0].role == "owner"

    def test_create_room_with_members(self, sb):
        r = create_room(
            sb, organisation_id=None, name="Hire chat",
            type_="project", created_by="boss",
            members=["hr", "dept", "finance", "admin"],
        )
        members = list_members(sb, r.id)
        assert len(members) == 5
        roles = {m.user_id: m.role for m in members}
        assert roles["boss"] == "owner"
        assert roles["hr"] == "member"

    def test_create_invalid_type_raises(self, sb):
        with pytest.raises(RoomError):
            create_room(sb, name="x", type_="bogus", created_by="u")

    def test_create_invalid_name_raises(self, sb):
        with pytest.raises(RoomError):
            create_room(sb, name="", created_by="u")
        with pytest.raises(RoomError):
            create_room(sb, name="x" * 500, created_by="u")

    def test_get_room(self, sb):
        r = create_room(sb, name="X", created_by="u1")
        fetched = get_room(sb, r.id)
        assert fetched.id == r.id
        assert fetched.name == "X"

    def test_get_room_not_found(self, sb):
        with pytest.raises(RoomError):
            get_room(sb, "does-not-exist")

    def test_get_room_with_members_returns_active(self, sb):
        r = create_room(sb, name="X", created_by="u1", members=["u2", "u3"])
        leave_room(sb, r.id, user_id="u2")
        out = get_room_with_members(sb, r.id)
        active = [m for m in out["members"] if m["user_id"] != "u2"]
        assert len(active) == 2  # u1 + u3

    def test_update_room_admin_only(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        invite_member(sb, r.id, inviter_id="boss", invitee_id="u2", role="admin")
        update_room(sb, r.id, user_id="u2", name="Renamed")
        assert get_room(sb, r.id).name == "Renamed"

    def test_update_room_member_denied(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        invite_member(sb, r.id, inviter_id="boss", invitee_id="u2")
        with pytest.raises(PermissionDeniedError):
            update_room(sb, r.id, user_id="u2", name="Not allowed")

    def test_archive_room(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        archived = archive_room(sb, r.id, user_id="boss")
        assert archived.archived is True


# ===========================================================================
# 3. Members
# ===========================================================================
class TestMembers:

    def test_invite_new(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        m = invite_member(sb, r.id, inviter_id="boss", invitee_id="u2")
        assert m.role == "member"

    def test_invite_self(self, sb):
        # 邀请自己加入已经存在的房间 — 应当返回原 owner 身份而不修改 role
        r = create_room(sb, name="X", created_by="boss")
        m = invite_member(sb, r.id, inviter_id="boss", invitee_id="boss", role="admin")
        assert m.role == "owner"  # 已存在则返回原角色, 不被邀请参数覆盖

    def test_invite_existing_idempotent(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        # 重复邀请已 active 成员
        m = invite_member(sb, r.id, inviter_id="boss", invitee_id="u2")
        assert m.user_id == "u2"

    def test_invite_rejoin(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        invite_member(sb, r.id, inviter_id="boss", invitee_id="u2")
        leave_room(sb, r.id, user_id="u2")
        m = invite_member(sb, r.id, inviter_id="boss", invitee_id="u2", role="admin")
        assert m.role == "admin"

    def test_invite_by_member_forbidden(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        invite_member(sb, r.id, inviter_id="boss", invitee_id="u2")
        with pytest.raises(PermissionDeniedError):
            invite_member(sb, r.id, inviter_id="u2", invitee_id="u3")

    def test_invite_invalid_role(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        with pytest.raises(RoomError):
            invite_member(sb, r.id, inviter_id="boss", invitee_id="x", role="bogus")

    def test_leave_owner_forbidden(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        with pytest.raises(PermissionDeniedError):
            leave_room(sb, r.id, user_id="boss")

    def test_leave_member_ok(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        leave_room(sb, r.id, user_id="u2")
        # 仍是 room 记录但 left_at
        members = list_members(sb, r.id)
        uids = {m.user_id for m in members}
        assert "u2" not in uids

    def test_remove_others_by_owner(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        remove_member(sb, r.id, actor_id="boss", target_id="u2")
        members = list_members(sb, r.id)
        assert "u2" not in {m.user_id for m in members}

    def test_remove_others_by_member_forbidden(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2", "u3"])
        with pytest.raises(PermissionDeniedError):
            remove_member(sb, r.id, actor_id="u2", target_id="u3")

    def test_remove_nonmember(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        with pytest.raises(NotMemberError):
            remove_member(sb, r.id, actor_id="boss", target_id="nope")


# ===========================================================================
# 4. Messages
# ===========================================================================
class TestMessages:

    def _setup(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2", "u3"])
        return r

    def test_post_message_basic(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="hello team")
        assert m.content == "hello team"
        assert m.message_type == "text"
        assert m.parent_id is None

    def test_post_message_too_long(self, sb):
        r = self._setup(sb)
        with pytest.raises(RoomError):
            post_message(sb, r.id, sender_id="boss", content="x" * (MAX_MESSAGE_LEN + 1))

    def test_post_by_nonmember_forbidden(self, sb):
        r = self._setup(sb)
        with pytest.raises(NotMemberError):
            post_message(sb, r.id, sender_id="intruder", content="hi")

    def test_edit_message_sender_only(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="orig")
        edited = edit_message(sb, r.id, m.id, editor_id="boss", content="new")
        assert edited.content == "new"
        assert edited.edited_at is not None

    def test_edit_message_other_forbidden(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="orig")
        with pytest.raises(PermissionDeniedError):
            edit_message(sb, r.id, m.id, editor_id="u2", content="hijack")

    def test_edit_deleted_forbidden(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="x")
        delete_message(sb, r.id, m.id, actor_id="boss")
        with pytest.raises(PermissionDeniedError):
            edit_message(sb, r.id, m.id, editor_id="boss", content="z")

    def test_delete_message_soft(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="x")
        delete_message(sb, r.id, m.id, actor_id="boss")
        # 仍存在但 deleted_at
        rows = [r2 for r2 in sb.s.tables["room_messages"] if r2["id"] == m.id]
        assert rows and rows[0]["deleted_at"]
        assert rows[0]["deleted_by"] == "boss"

    def test_delete_by_admin(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="u2", content="x")
        delete_message(sb, r.id, m.id, actor_id="boss")
        rows = [r2 for r2 in sb.s.tables["room_messages"] if r2["id"] == m.id]
        assert rows[0]["deleted_at"]

    def test_delete_by_stranger_forbidden(self, sb):
        r = self._setup(sb)
        m = post_message(sb, r.id, sender_id="boss", content="x")
        with pytest.raises(PermissionDeniedError):
            delete_message(sb, r.id, m.id, actor_id="u3")

    def test_list_messages_pagination(self, sb):
        r = self._setup(sb)
        for i in range(5):
            post_message(sb, r.id, sender_id="boss", content=f"msg-{i}")
        msgs, cursor = list_messages(sb, r.id, user_id="boss", limit=3)
        assert len(msgs) == 3
        assert cursor is not None
        # 取下一页
        msgs2, cursor2 = list_messages(sb, r.id, user_id="boss", limit=3, cursor=cursor)
        assert len(msgs2) == 2
        assert cursor2 is None


# ===========================================================================
# 5. Threads
# ===========================================================================
class TestThreads:

    def _setup(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        return r

    def test_post_reply_marks_parent(self, sb):
        r = self._setup(sb)
        root = post_message(sb, r.id, sender_id="boss", content="root")
        reply = post_message(sb, r.id, sender_id="u2", content="reply", parent_id=root.id)
        assert reply.parent_id == root.id

    def test_post_reply_thread_depth_enforced(self, sb):
        r = self._setup(sb)
        root = post_message(sb, r.id, sender_id="boss", content="root")
        reply = post_message(sb, r.id, sender_id="u2", content="r1", parent_id=root.id)
        with pytest.raises(RoomError):
            post_message(sb, r.id, sender_id="boss", content="r2", parent_id=reply.id)

    def test_post_reply_invalid_parent(self, sb):
        r = self._setup(sb)
        other = create_room(sb, name="Y", created_by="boss")
        msg = post_message(sb, other.id, sender_id="boss", content="?")
        with pytest.raises(RoomError):
            post_message(sb, r.id, sender_id="boss", content="r", parent_id=msg.id)

    def test_list_thread_replies(self, sb):
        r = self._setup(sb)
        root = post_message(sb, r.id, sender_id="boss", content="root")
        post_message(sb, r.id, sender_id="u2", content="r1", parent_id=root.id)
        post_message(sb, r.id, sender_id="boss", content="r2", parent_id=root.id)
        replies = list_thread_replies(sb, r.id, root.id, user_id="boss")
        assert len(replies) == 2
        assert [m.content for m in replies] == ["r1", "r2"]


# ===========================================================================
# 6. Mentions
# ===========================================================================
class TestMentions:

    def test_mention_persists(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2", "u3"])
        # 用 @UUID 形式
        text = "ping @u2 please"
        # 直接 post, parses by UUID, 但服务用正则匹配 UUID 形式
        # 这里我们手动构造一个有效 UUID
        uid = "11111111-1111-1111-1111-111111111111"
        # 先把 u2 换成 UUID 不切实际, 我们改用 explicit mentions 参数
        m = post_message(
            sb, r.id, sender_id="boss", content=f"hi", mentions=[uid]
        )
        assert uid in m.mentions
        # 应创建 mention row
        mention_rows = [r2 for r2 in sb.s.tables["room_mentions"] if r2["message_id"] == m.id]
        # 该 uid 不是 active 成员, 不写
        assert len(mention_rows) == 0

    def test_mention_writes_for_active_members(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        m = post_message(
            sb, r.id, sender_id="boss", content="hi", mentions=["u2"]
        )
        mention_rows = [r2 for r2 in sb.s.tables["room_mentions"] if r2["message_id"] == m.id]
        assert len(mention_rows) == 1
        assert mention_rows[0]["user_id"] == "u2"


# ===========================================================================
# 7. Reactions
# ===========================================================================
class TestReactions:

    def test_add_reaction_insert(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        m = post_message(sb, r.id, sender_id="boss", content="hi")
        reaction = add_reaction(sb, r.id, m.id, user_id="boss", emoji="+1")
        assert reaction.created_at != ""  # 表示 active
        reactions = list_reactions(sb, m.id)
        assert len(reactions) == 1
        assert reactions[0].emoji == "+1"

    def test_reaction_is_toggle(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        m = post_message(sb, r.id, sender_id="boss", content="hi")
        add_reaction(sb, r.id, m.id, user_id="boss", emoji="+1")
        # 再次相同 emoji 应删除
        second = add_reaction(sb, r.id, m.id, user_id="boss", emoji="+1")
        assert second.created_at == ""  # 表示已删除
        assert list_reactions(sb, m.id) == []

    def test_reaction_different_emoji_both_active(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        m = post_message(sb, r.id, sender_id="boss", content="hi")
        add_reaction(sb, r.id, m.id, user_id="boss", emoji="+1")
        add_reaction(sb, r.id, m.id, user_id="boss", emoji="heart")
        assert len(list_reactions(sb, m.id)) == 2


# ===========================================================================
# 8. Pins
# ===========================================================================
class TestPins:

    def test_pin_unpin_admin_only(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        m = post_message(sb, r.id, sender_id="boss", content="pinme")
        # member 不能 pin
        with pytest.raises(PermissionDeniedError):
            pin_message(sb, r.id, m.id, user_id="u2")
        # owner 可以
        pin_message(sb, r.id, m.id, user_id="boss")
        pins = list_pins(sb, r.id, user_id="boss")
        assert len(pins) == 1
        # unpin
        unpin_message(sb, r.id, m.id, user_id="boss")
        assert list_pins(sb, r.id, user_id="boss") == []

    def test_pin_invalid_message(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        with pytest.raises(MessageNotFoundError):
            pin_message(sb, r.id, "nope", user_id="boss")


# ===========================================================================
# 9. Read / Unread
# ===========================================================================
class TestUnread:

    def test_unread_count_increases_and_reset(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        assert get_unread_count(sb, r.id, user_id="u2") == 0
        post_message(sb, r.id, sender_id="boss", content="hi")
        post_message(sb, r.id, sender_id="boss", content="hi2")
        assert get_unread_count(sb, r.id, user_id="u2") == 2

        # 自己发的消息不计入
        post_message(sb, r.id, sender_id="u2", content="myself")
        assert get_unread_count(sb, r.id, user_id="u2") == 2

        # mark_read 后清零
        mark_read(sb, r.id, user_id="u2")
        assert get_unread_count(sb, r.id, user_id="u2") == 0

    def test_list_my_rooms_with_unread(self, sb):
        create_room(sb, name="A", created_by="boss", members=["u2"])
        rooms = list_my_rooms(sb, user_id="u2")
        assert len(rooms) == 1
        assert rooms[0]["unread_count"] == 0

        post_message(sb, rooms[0]["id"], sender_id="boss", content="ping")
        rooms = list_my_rooms(sb, user_id="u2")
        assert rooms[0]["unread_count"] == 1

    def test_total_unread(self, sb):
        r1 = create_room(sb, name="A", created_by="boss", members=["u2"])
        r2 = create_room(sb, name="B", created_by="boss", members=["u2"])
        post_message(sb, r1.id, sender_id="boss", content="1")
        post_message(sb, r2.id, sender_id="boss", content="2")
        post_message(sb, r2.id, sender_id="boss", content="3")
        assert get_total_unread_count(sb, user_id="u2") == 3


# ===========================================================================
# 10. Search
# ===========================================================================
class TestSearch:

    def test_search_basic(self, sb):
        r = create_room(sb, name="X", created_by="boss", members=["u2"])
        post_message(sb, r.id, sender_id="boss", content="buy apples")
        post_message(sb, r.id, sender_id="boss", content="sell oranges")
        msgs = search_messages(sb, r.id, user_id="boss", query="apple")
        assert len(msgs) == 1
        assert "apples" in msgs[0].content

    def test_search_excludes_deleted(self, sb):
        r = create_room(sb, name="X", created_by="boss")
        m = post_message(sb, r.id, sender_id="boss", content="buy apples")
        delete_message(sb, r.id, m.id, actor_id="boss")
        msgs = search_messages(sb, r.id, user_id="boss", query="apple")
        assert msgs == []
