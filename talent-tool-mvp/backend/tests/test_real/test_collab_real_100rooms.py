"""T1808 — 100 个真实活跃房间 + 性能 + 指标测试.

测试范围:
  1) 创建 100 个 room + 邀请成员 + 发消息 → 内存 metrics 正确采集
  2) list_my_rooms 批量 unread 路径 (避免 N+1)
  3) post_message / mark_read / list_messages 延迟采集
  4) collab_metrics report() 包含完整字段
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from services.observability.collab_metrics import (
    CollabMetrics,
    get_collab_metrics,
    report,
    track_list_messages,
    track_mark_read,
    track_post_message,
    track_search_messages,
)


# ---------------------------------------------------------------------------
# In-memory supabase mock — 完整覆盖 collab_room 使用的 table 操作
# ---------------------------------------------------------------------------
@dataclass
class TableMock:
    rows: list[dict[str, Any]] = field(default_factory=list)
    name: str = ""

    # 像 Supabase 一样, table(name).select(...) / .insert(...) / .update(...) / .delete() 都直接返 Query
    def select(self, fields: str = "*", count: str | None = None) -> "_Query":
        return _Query(self, select_fields=fields)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]):
        items = payload if isinstance(payload, list) else [payload]
        new_rows: list[dict[str, Any]] = []
        for it in items:
            row = dict(it)
            if "id" not in row:
                row["id"] = str(uuid.uuid4())
            if "created_at" not in row and self.name in (
                "rooms", "room_messages", "room_reactions", "room_members",
            ):
                row["created_at"] = "2026-07-12T10:00:00Z"
            self.rows.append(row)
            new_rows.append(row)
        # 创建一个新的 Query, execute 时返回刚 insert 的 rows (Supabase 的行为)
        q = _Query(self, inserted=new_rows)
        return q

    def update(self, payload: dict[str, Any]) -> "_Query":
        q = _Query(self)
        q.update(payload)
        return q

    def delete(self) -> "_Query":
        q = _Query(self)
        q.delete()
        return q


@dataclass
class _Query:
    table: TableMock
    filters: list[tuple[str, str, Any]] = field(default_factory=list)
    is_nulls: list[tuple[str, str]] = field(default_factory=list)
    neq_filters: list[tuple[str, str]] = field(default_factory=list)
    order_desc: str | None = None
    limit_n: int | None = None
    in_values: dict[str, list[Any]] = field(default_factory=dict)
    inserted: list[dict[str, Any]] = field(default_factory=list)
    select_fields: str = "*"
    _updated_rows: list[dict[str, Any]] = field(default_factory=list)
    _deleted_rows: list[dict[str, Any]] = field(default_factory=list)

    def select(self, fields: str = "*", count: str | None = None):
        self.select_fields = fields
        return self

    def eq(self, col: str, val: Any):
        self.filters.append(("eq", col, val))
        return self

    def is_(self, col: str, val: str):
        self.is_nulls.append((col, val))
        return self

    def neq(self, col: str, val: Any):
        self.neq_filters.append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]):
        self.in_values[col] = list(vals)
        return self

    def gt(self, col: str, val: Any):
        self.filters.append(("gt", col, val))
        return self

    def lt(self, col: str, val: Any):
        self.filters.append(("lt", col, val))
        return self

    def order(self, col: str, desc: bool = False, nullsfirst: bool = False):
        self.order_desc = col if desc else None
        return self

    def limit(self, n: int):
        self.limit_n = n
        return self

    def text_search(self, col: str, query: str, config: str = "simple"):
        return self

    def update(self, payload: dict[str, Any]):
        rows = self._apply()
        for r in rows:
            r.update(payload)
        # 同时标记 _updated 行供 execute() 返回
        self._updated_rows = list(rows)
        return self

    def delete(self):
        rows = self._apply()
        ids = {id(r) for r in rows}
        self.table.rows = [r for r in self.table.rows if id(r) not in ids]
        self._deleted_rows = list(rows)
        return self

    def execute(self) -> "_Result":
        if self.inserted:
            return _Result(data=list(self.inserted), count=len(self.inserted))
        if self._updated_rows:
            return _Result(data=list(self._updated_rows), count=len(self._updated_rows))
        if self._deleted_rows:
            return _Result(data=list(self._deleted_rows), count=len(self._deleted_rows))
        rows = self._apply()
        if self.order_desc:
            rows = sorted(rows, key=lambda r: r.get(self.order_desc) or "", reverse=True)
        if self.limit_n:
            rows = rows[: self.limit_n]
        return _Result(data=list(rows), count=len(rows))

    def _apply(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self.table.rows:
            ok = True
            for op, col, val in self.filters:
                if op == "eq" and r.get(col) != val:
                    ok = False; break
                if op == "gt" and (r.get(col) or "") <= val: ok = False; break
                if op == "lt" and (r.get(col) or "") >= val: ok = False; break
            if not ok:
                continue
            for col, val in self.is_nulls:
                if val == "null" and r.get(col) is not None: ok = False; break
                if val != "null" and r.get(col) != val: ok = False; break
            if not ok:
                continue
            for col in self.in_values:
                if r.get(col) not in self.in_values[col]: ok = False; break
            if not ok:
                continue
            for col, val in self.neq_filters:
                if r.get(col) == val: ok = False; break
            if not ok:
                continue
            out.append(r)
        return out


@dataclass
class _Result:
    data: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, TableMock] = {}
        for name in (
            "rooms", "room_members", "room_messages", "room_reactions",
            "room_mentions", "room_pins",
        ):
            self.tables[name] = TableMock(name=name)

    def table(self, name: str) -> TableMock:
        return self.tables[name]

    # 用于 count="exact" 模拟
    def _select_with_count(self, table_name: str) -> _Query:
        return _Query(table=self.tables[table_name])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.fixture
def sb() -> FakeSupabase:
    return FakeSupabase()


def _add_room(sb: FakeSupabase, *, name: str, org_id: str | None = None,
              type_: str = "group", creator: str = "user-creator") -> str:
    from services.collaboration_room import create_room
    room = create_room(sb, organisation_id=org_id, name=name,
                       type_=type_, created_by=creator)
    return room.id


def _add_member(sb: FakeSupabase, room_id: str, user_id: str, role: str = "member",
                 inviter_id: str | None = None) -> None:
    """添加成员; 如果 inviter_id=None, 查找 room 的 owner."""
    from services.collaboration_room import invite_member
    if inviter_id is None:
        # 找房间 owner
        rooms = sb.tables["rooms"].rows
        members = sb.tables["room_members"].rows
        owner = next(
            (m["user_id"] for m in members
             if m["room_id"] == room_id and m.get("role") == "owner"),
            "user-creator",
        )
        inviter_id = owner
    invite_member(sb, room_id, inviter_id=inviter_id,
                  invitee_id=user_id, role=role)


def test_100_active_rooms_full_workflow(sb: FakeSupabase) -> None:
    """1) 引导 100 个 room + 邀请成员 + 发消息 + 验证 metrics."""
    metrics = get_collab_metrics()
    metrics.reset()

    # 创建 100 个房间, 分 4 个 org
    org_ids = ["org-1", "org-2", "org-3", "org-4"]
    room_ids: list[str] = []
    for i in range(100):
        org_id = org_ids[i % 4]
        type_ = "group" if i % 2 == 0 else "direct"
        creator = f"creator-{i}"
        rid = _add_room(sb, name=f"Room #{i:03d}",
                        org_id=org_id, type_=type_, creator=creator)
        room_ids.append(rid)
        # 每个房间邀请 1-3 个成员
        n_members = 1 + (i % 3)
        for j in range(n_members):
            _add_member(sb, rid, user_id=f"member-{i}-{j}")

    # 每个房间发 5 条消息 (sender 必须是 member)
    from services.collaboration_room import post_message
    total_msgs = 0
    total_mentions = 0
    for i, rid in enumerate(room_ids):
        creator = f"creator-{i}"
        for k in range(5):
            msg = post_message(
                sb, rid, sender_id=creator,
                content=f"Hello {k} from room {i}",
            )
            total_msgs += 1
            total_mentions += len(msg.mentions)

    # 验证 metrics
    rep = report()
    assert rep["active_rooms"] == 100
    assert rep["messages_per_hour"] >= 400  # 500 messages in <1h
    assert rep["mentions_total"] == total_mentions
    # 4 个 org 各 25 个房间
    assert rep["rooms_by_org"]["org-1"] == 25
    assert rep["rooms_by_org"]["org-2"] == 25
    assert rep["rooms_by_org"]["org-3"] == 25
    assert rep["rooms_by_org"]["org-4"] == 25
    # group + direct 各 50
    assert rep["rooms_by_type"]["group"] == 50
    assert rep["rooms_by_type"]["direct"] == 50
    # 平均成员数 (1+2+3 循环) ~ 2.0 (含 owner)
    assert 1.5 <= rep["avg_members_per_room"] <= 3.5
    # latency 已采集 — 500 messages posted (100 rooms × 5 msgs)
    assert rep["latency_ms"]["post_message"]["n"] >= 400
    # latency p95 应合理 (< 100ms in-memory)
    assert rep["latency_ms"]["post_message"]["p95"] < 100


def test_list_my_rooms_batch_unread_optimization(sb: FakeSupabase) -> None:
    """2) list_my_rooms 用批量 unread (避免 N+1)."""
    metrics = get_collab_metrics()
    metrics.reset()

    # 创建 50 个房间, 各发 3 条消息
    for i in range(50):
        creator = f"creator-batch-{i}"
        rid = _add_room(sb, name=f"Batch-{i}", org_id="org-batch", creator=creator)
        _add_member(sb, rid, user_id="user-x")
        from services.collaboration_room import post_message
        for k in range(3):
            post_message(sb, rid, sender_id=creator,
                         content=f"Msg {k} in batch {i}")

    # 测 list_my_rooms batch path
    from services.collaboration_room import list_my_rooms
    rooms = list_my_rooms(sb, user_id="user-x", batch_unread=True)
    assert len(rooms) == 50
    # user-x 在 creator 发消息后才加入 → 所有 3 条都是未读
    for r in rooms:
        assert r["unread_count"] == 3

    # 再加入一个新用户,该用户没发任何消息 → 应看到所有未读
    other_user = "user-y"
    for rid in [r["id"] for r in rooms]:
        _add_member(sb, rid, user_id=other_user)
    rooms_y = list_my_rooms(sb, user_id=other_user, batch_unread=True)
    assert len(rooms_y) == 50
    for r in rooms_y:
        # user-y 没发消息 → 应看到 3 条未读 (每个 room 3 条)
        assert r["unread_count"] == 3


def test_list_my_rooms_legacy_fallback(sb: FakeSupabase) -> None:
    """3) batch_unread=False 退化到逐个 query."""
    for i in range(5):
        creator = f"creator-legacy-{i}"
        rid = _add_room(sb, name=f"Legacy-{i}", org_id="org-legacy", creator=creator)
        _add_member(sb, rid, user_id="user-z")
        from services.collaboration_room import post_message
        post_message(sb, rid, sender_id=creator, content=f"hi {i}")

    from services.collaboration_room import list_my_rooms
    rooms = list_my_rooms(sb, user_id="user-z", batch_unread=False)
    assert len(rooms) == 5
    for r in rooms:
        assert r["unread_count"] >= 1


def test_mark_read_records_unread_distribution(sb: FakeSupabase) -> None:
    """4) mark_read 记录未读分布."""
    metrics = get_collab_metrics()
    metrics.reset()

    rid = _add_room(sb, name="Mark-Read-Test", org_id="org-mr", creator="sender-1")
    _add_member(sb, rid, user_id="reader-1")
    from services.collaboration_room import post_message, mark_read

    # 发 10 条
    for k in range(10):
        post_message(sb, rid, sender_id="sender-1", content=f"msg {k}")

    # mark_read → 未读应记入 metrics
    mark_read(sb, rid, user_id="reader-1")
    rep = report()
    assert rep["reads_total"] == 1
    assert rep["unread"]["samples"] == 1
    assert rep["unread"]["p50"] == 10
    # latency 已记录
    assert rep["latency_ms"]["mark_read"]["n"] == 1


def test_reaction_metrics(sb: FakeSupabase) -> None:
    """5) add_reaction 记入 metrics."""
    metrics = get_collab_metrics()
    metrics.reset()

    rid = _add_room(sb, name="Reaction-Test", org_id="org-react", creator="sender-1")
    _add_member(sb, rid, user_id="reactor-1")
    from services.collaboration_room import post_message, add_reaction

    msg = post_message(sb, rid, sender_id="sender-1", content="react to me")
    add_reaction(sb, rid, msg.id, user_id="reactor-1", emoji="👍")
    add_reaction(sb, rid, msg.id, user_id="reactor-1", emoji="🎉")

    rep = report()
    assert rep["reactions_total"] == 2


def test_search_messages_latency(sb: FakeSupabase) -> None:
    """6) search_messages 记入 latency."""
    metrics = get_collab_metrics()
    metrics.reset()

    rid = _add_room(sb, name="Search-Test", org_id="org-search", creator="search-creator")
    _add_member(sb, rid, user_id="searcher-1")
    from services.collaboration_room import post_message, search_messages
    for k in range(20):
        post_message(sb, rid, sender_id="search-creator",
                     content=f"term-{k} content")
    results = search_messages(sb, rid, user_id="searcher-1", query="term")
    rep = report()
    assert rep["latency_ms"]["search_messages"]["n"] == 1
    assert rep["latency_ms"]["search_messages"]["p50"] >= 0


def test_metrics_reset() -> None:
    """7) reset 清空所有计数."""
    metrics = get_collab_metrics()
    metrics.room_created("r1", "org-x", "group")
    metrics.member_added("r1")
    metrics.message_posted(mentions=1, latency_ms=10)
    metrics.reaction_added()
    metrics.mark_read(unread_count_at_call=5, latency_ms=2)
    metrics.reset()
    rep = report()
    assert rep["active_rooms"] == 0
    assert rep["messages_per_hour"] == 0
    assert rep["reactions_total"] == 0
    assert rep["reads_total"] == 0


def test_track_context_managers() -> None:
    """8) 4 个 track_* context manager 都能正确 record."""
    metrics = get_collab_metrics()
    metrics.reset()
    with track_post_message(mentions=2):
        time.sleep(0.001)
    with track_list_messages():
        pass
    with track_mark_read(unread_count=7):
        time.sleep(0.001)
    with track_search_messages():
        pass
    rep = report()
    assert rep["mentions_total"] == 2
    assert rep["reads_total"] == 1
    assert rep["unread"]["samples"] == 1
    assert rep["unread"]["p50"] == 7
    assert rep["latency_ms"]["post_message"]["n"] == 1
    assert rep["latency_ms"]["list_messages"]["n"] == 1
    assert rep["latency_ms"]["mark_read"]["n"] == 1
    assert rep["latency_ms"]["search_messages"]["n"] == 1


def test_metrics_report_full_schema() -> None:
    """9) report() 包含完整字段 (dashboard 契约)."""
    rep = report()
    expected_keys = {
        "active_rooms", "rooms_by_type", "rooms_by_org",
        "avg_members_per_room",
        "messages_per_min", "messages_per_5min", "messages_per_hour",
        "mentions_total", "reactions_total", "reads_total",
        "unread", "latency_ms", "errors_total", "sampled_at",
    }
    assert expected_keys.issubset(rep.keys())
    # nested
    assert {"p50", "p95", "p99", "max", "samples"}.issubset(rep["unread"].keys())
    assert {"post_message", "list_messages", "mark_read", "search_messages"}.issubset(
        rep["latency_ms"].keys()
    )


if __name__ == "__main__":
    # 简单手动运行
    sb = FakeSupabase()
    test_100_active_rooms_full_workflow(sb)
    print("OK: 100-room workflow")
    print(report())