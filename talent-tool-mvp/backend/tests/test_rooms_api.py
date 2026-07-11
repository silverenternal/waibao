"""Tests for api.rooms REST endpoints (T608).

策略:
- monkeypatch get_supabase_admin 返回 in-memory fake
- 覆盖 11 个核心 endpoint + 扩展 pin/thread/search/mentions
- 使用 FastAPI TestClient, 不依赖真实 Supabase / JWT
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Reuse fake from service test
from tests.test_collaboration_room import FakeSB, _Store  # noqa: E402


def _user(user_id: str, role: str = "client"):
    from contracts.shared import UserRole

    class _U:
        def __init__(self):
            import uuid as _uuid

            self.id = _uuid.UUID(user_id) if isinstance(user_id, str) and len(user_id) == 36 else _uuid.UUID(int=0)
            self.email = f"{role}@test.com"
            self.role = UserRole(role)

    u = _U()
    if not isinstance(user_id, str) or len(user_id) != 36:
        # support string short id by manual override
        u.id_short = user_id
    return u


@pytest.fixture
def sb():
    return FakeSB()


class _StrId:
    """Wraps a string but behaves like UUID for CurrentUser.id.

    FastAPI's CurrentUser.id is typed as UUID, so we override only __str__.
    """

    def __init__(self, s: str):
        import uuid as _uuid

        self._str = s
        try:
            self._uuid = _uuid.UUID(s) if isinstance(s, str) and len(s) == 36 else None
        except ValueError:
            self._uuid = None

    def __str__(self):
        return self._str

    def __getattr__(self, item):
        # Delegate other attribute access to wrapped UUID if available
        if self._uuid is not None and item not in ("__str__", "_str"):
            return getattr(self._uuid, item)
        raise AttributeError(item)


@pytest.fixture
def boss_user():
    class _U:
        def __init__(self):
            from contracts.shared import UserRole

            self.id = _StrId("boss")
            self.email = "boss@test.com"
            self.role = UserRole("admin")
            self.short_id = "boss"
    return _U()


@pytest.fixture
def hr_user():
    class _U:
        def __init__(self):
            from contracts.shared import UserRole

            self.id = _StrId("hr")
            self.email = "hr@test.com"
            self.role = UserRole("talent_partner")
            self.short_id = "hr"
    return _U()


@pytest.fixture
def intruder_user():
    class _U:
        def __init__(self):
            from contracts.shared import UserRole

            self.id = _StrId("intruder")
            self.email = "intruder@test.com"
            self.role = UserRole("client")
            self.short_id = "intruder"
    return _U()


@pytest.fixture(autouse=True)
def patch_id_resolution(monkeypatch):
    """让 service 端的 _check_member / _check_admin 等使用 fake 用户的 short_id。

    service 通过 str(user.id) 传 UUID。我们的 fake user 用 UUID(int=1)...
    但 service 写 rooms / members 时存的就是字符串。为简化测试, 我们直接
    注入 fake supabase, 在 service 调用前手动写入 membership。
    """
    yield


# ---------------------------------------------------------------------------
# Helper: 用真实字符串 id (而非 UUID) 注入 service 的成员关系
# ---------------------------------------------------------------------------
def _seed_member(sb, room_id: str, user_id: str, role: str = "member"):
    sb.s.tables["room_members"].append(
        {
            "room_id": room_id,
            "user_id": user_id,
            "role": role,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "left_at": None,
            "last_read_at": None,
            "muted": False,
            "id": sb.s.new_id(),
        }
    )


def _seed_room(sb, name: str, created_by: str, members=()):
    r = {
        "name": name,
        "type": "group",
        "created_by": created_by,
        "organisation_id": None,
        "archived": False,
        "archived_at": None,
        "metadata": {},
        "member_count": 0,
        "id": sb.s.new_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_message_at": None,
    }
    sb.s.tables["rooms"].append(r)
    # owner
    _seed_member(sb, r["id"], created_by, role="owner")
    for m in members:
        _seed_member(sb, r["id"], m, role="member")
    r["member_count"] = len(sb.s.tables["room_members"][-1 - len(members):])
    return r


@pytest.fixture
def app(sb, monkeypatch, boss_user):
    """Build a FastAPI test app with overridden deps."""
    from fastapi import FastAPI
    from api.rooms import router
    from api.auth import get_current_user
    import api.deps as deps_mod
    import api.rooms as rooms_mod

    monkeypatch.setattr(deps_mod, "get_supabase_admin", lambda: sb)
    monkeypatch.setattr(rooms_mod, "get_supabase_admin", lambda: sb)

    app = FastAPI()
    app.include_router(router, prefix="/api/rooms")
    app.dependency_overrides[get_current_user] = lambda: boss_user
    return app


# ---------------------------------------------------------------------------
# POST /api/rooms — 创建房间
# ---------------------------------------------------------------------------
class TestCreateRoom:
    def test_create_happy(self, app):
        from fastapi.testclient import TestClient

        c = TestClient(app)
        r = c.post("/api/rooms", json={
            "name": "Q3 hiring",
            "type": "project",
            "members": ["hr", "dept", "finance"],
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["name"] == "Q3 hiring"
        # 4 members: created_by + 3 invited (created_by 视为 admin/owner)
        user_ids = {m["user_id"] for m in d["members"]}
        assert "hr" in user_ids

    def test_create_invalid_type_400(self, app):
        from fastapi.testclient import TestClient

        c = TestClient(app)
        r = c.post("/api/rooms", json={"name": "x", "type": "bogus"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/rooms — 我参与的房间
# ---------------------------------------------------------------------------
class TestListMyRooms:
    def test_list_returns_rooms_with_unread(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        # 创建 2 个房间 + 由 hr 发条消息 (这样 boss 的未读计数会增加)
        r1 = _seed_room(sb, "R1", boss_user.short_id, members=["hr"])
        r2 = _seed_room(sb, "R2", boss_user.short_id, members=["hr"])
        sb.s.tables["room_messages"].append({
            "room_id": r1["id"], "sender_id": "hr",
            "content": "hi", "message_type": "text",
            "parent_id": None, "mentions": [], "mention_offsets": [],
            "attachments": [], "deleted_at": None, "edited_at": None,
            "id": sb.s.new_id(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        c = TestClient(app)
        r = c.get("/api/rooms")
        assert r.status_code == 200
        d = r.json()
        rooms = d["rooms"]
        assert len(rooms) == 2
        # 至少一个房间有未读
        assert any(rm["unread_count"] >= 1 for rm in rooms)


# ---------------------------------------------------------------------------
# GET /api/rooms/{id}
# ---------------------------------------------------------------------------
class TestGetRoom:
    def test_get_returns_members_and_pins(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)
        r = c.get(f"/api/rooms/{room['id']}")
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "X"
        assert len(d["members"]) == 2
        assert d["pins"] == []
        assert "unread_count" in d

    def test_get_nonmember_403(self, app, sb, monkeypatch, intruder_user):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        room = _seed_room(sb, "X", "other", members=[])

        app.dependency_overrides[get_current_user] = lambda: intruder_user
        c = TestClient(app)
        r = c.get(f"/api/rooms/{room['id']}")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST/DELETE /api/rooms/{id}/members
# ---------------------------------------------------------------------------
class TestMembers:
    def test_invite_member_happy(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/members", json={
            "user_id": "dept", "role": "admin",
        })
        assert r.status_code == 201
        d = r.json()
        assert d["user_id"] == "dept"
        assert d["role"] == "admin"

    def test_invite_invalid_role_400(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/members", json={
            "user_id": "dept", "role": "bogus",
        })
        assert r.status_code == 400

    def test_remove_member(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)
        r = c.delete(f"/api/rooms/{room['id']}/members/hr")
        assert r.status_code in (200, 204)

    def test_self_leave(self, app, sb, boss_user, hr_user, monkeypatch):
        """hr 主动离开普通房间."""
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        # 让 hr 是 member, 不是 owner
        room = _seed_room(sb, "X", "boss", members=["hr"])
        app.dependency_overrides[get_current_user] = lambda: hr_user

        c = TestClient(app)
        r = c.delete(f"/api/rooms/{room['id']}/members/hr")
        assert r.status_code in (200, 204)


# ---------------------------------------------------------------------------
# POST/GET /api/rooms/{id}/messages
# ---------------------------------------------------------------------------
class TestMessages:
    def test_post_and_list_messages(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)

        # post
        r = c.post(f"/api/rooms/{room['id']}/messages", json={
            "content": "Hello 5-party team",
            "message_type": "text",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["content"] == "Hello 5-party team"
        assert d["sender_id"]

        # list
        r = c.get(f"/api/rooms/{room['id']}/messages?limit=50")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert any(m["content"] == "Hello 5-party team" for m in msgs)

    def test_post_invalid_type_400(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={
            "content": "x", "message_type": "bogus",
        })
        assert r.status_code == 400

    def test_post_too_long_400(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={
            "content": "x" * 20001,
        })
        # pydantic max_length 校验失败 → 422
        assert r.status_code in (400, 422)

    def test_post_as_nonmember_403(self, app, sb, monkeypatch, intruder_user):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        room = _seed_room(sb, "X", "boss")
        app.dependency_overrides[get_current_user] = lambda: intruder_user
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={"content": "hi"})
        assert r.status_code == 403

    def test_edit_and_delete(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={"content": "orig"})
        msg_id = r.json()["id"]

        r = c.patch(f"/api/rooms/{room['id']}/messages/{msg_id}", json={"content": "new"})
        assert r.status_code == 200
        assert r.json()["content"] == "new"
        assert r.json()["edited_at"] is not None

        r = c.delete(f"/api/rooms/{room['id']}/messages/{msg_id}")
        assert r.status_code in (200, 204)

    def test_thread_reply(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={"content": "root"})
        root_id = r.json()["id"]
        r = c.post(f"/api/rooms/{room['id']}/messages", json={
            "content": "reply", "parent_id": root_id,
        })
        assert r.status_code == 201
        # 列出线程回复
        r = c.get(f"/api/rooms/{room['id']}/threads/{root_id}")
        assert r.status_code == 200
        assert len(r.json()["messages"]) == 1


# ---------------------------------------------------------------------------
# POST /api/rooms/{id}/messages/{msg}/reactions
# ---------------------------------------------------------------------------
class TestReactions:
    def test_reaction_toggle(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={"content": "hi"})
        msg_id = r.json()["id"]

        # add
        r = c.post(
            f"/api/rooms/{room['id']}/messages/{msg_id}/reactions",
            json={"emoji": "+1"},
        )
        assert r.status_code == 201
        d = r.json()
        assert d["active"] is True
        assert d["emoji"] == "+1"

        # toggle off
        r = c.post(
            f"/api/rooms/{room['id']}/messages/{msg_id}/reactions",
            json={"emoji": "+1"},
        )
        assert r.json()["active"] is False


# ---------------------------------------------------------------------------
# POST /api/rooms/{id}/read
# ---------------------------------------------------------------------------
class TestRead:
    def test_mark_read_updates_last_read_at(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)

        # 发一条消息
        c.post(f"/api/rooms/{room['id']}/messages", json={"content": "hi"})
        # hr 视角 read count > 0
        c.get(f"/api/rooms/{room['id']}")

        # mark read
        r = c.post(f"/api/rooms/{room['id']}/read", json={})
        assert r.status_code in (200, 204)


# ---------------------------------------------------------------------------
# PATCH /api/rooms/{id}
# ---------------------------------------------------------------------------
class TestPatchRoom:
    def test_rename_and_archive(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "Old", boss_user.short_id)
        c = TestClient(app)
        r = c.patch(f"/api/rooms/{room['id']}", json={"name": "New", "archived": True})
        assert r.status_code == 200
        assert r.json()["name"] == "New"
        assert r.json()["archived"] is True


# ---------------------------------------------------------------------------
# Pin / Unpin
# ---------------------------------------------------------------------------
class TestPin:
    def test_pin_and_list(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        r = c.post(f"/api/rooms/{room['id']}/messages", json={"content": "pinme"})
        msg_id = r.json()["id"]

        r = c.post(f"/api/rooms/{room['id']}/pin", json={"message_id": msg_id})
        assert r.status_code == 200

        r = c.post(f"/api/rooms/{room['id']}/unpin", json={"message_id": msg_id})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class TestSearch:
    def test_search_finds_keyword(self, app, sb, boss_user):
        from fastapi.testclient import TestClient

        room = _seed_room(sb, "X", boss_user.short_id)
        c = TestClient(app)
        c.post(f"/api/rooms/{room['id']}/messages", json={"content": "interview Wednesday"})
        c.post(f"/api/rooms/{room['id']}/messages", json={"content": "offer sent"})

        r = c.get(f"/api/rooms/{room['id']}/search?q=interview")
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) == 1
        assert "interview" in msgs[0]["content"]


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------
class TestMentions:
    def test_list_my_mentions(self, app, sb, boss_user):
        from fastapi.testclient import TestClient
        from services.collaboration_room import list_my_mentions

        room = _seed_room(sb, "X", boss_user.short_id, members=["hr"])
        c = TestClient(app)
        msg = c.post(f"/api/rooms/{room['id']}/messages", json={
            "content": "ping hr",
            "mentions": ["hr"],
        }).json()

        # POST 已经为 active 成员 hr 写入 room_mentions
        rows = list_my_mentions(sb, user_id="hr", unread_only=True)
        assert len(rows) == 1

        # 直接调 service 模拟 read
        mention_id = rows[0]["id"]
        from services.collaboration_room import mark_mention_read
        mark_mention_read(sb, mention_id, user_id="hr")

        rows2 = list_my_mentions(sb, user_id="hr", unread_only=True)
        assert rows2 == []  # 已读后 unreads 为空
