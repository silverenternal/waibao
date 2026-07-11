"""Tests for services.ticket_service (T207)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Fake supabase — 用 dict 模拟表 + 链式 API
# ---------------------------------------------------------------------------
class _FakeQuery:
    """链式查询: 收集所有过滤条件,execute() 时统一跑."""

    def __init__(self, table_state: "_TableState"):
        self.state = table_state
        self._filters: list[tuple[str, tuple]] = []  # (method, args)
        self._limit: int | None = None
        self._offset: int | None = None
        self._order_desc = False
        self._order_field: str | None = None
        self._range: tuple | None = None
        self._single = False
        self._maybe_single = False

    # ---- filters ----
    def eq(self, k, v):
        self._filters.append(("eq", (k, v)))
        return self

    def gt(self, k, v):
        self._filters.append(("gt", (k, v)))
        return self

    def lt(self, k, v):
        self._filters.append(("lt", (k, v)))
        return self

    def gte(self, k, v):
        self._filters.append(("gte", (k, v)))
        return self

    def lte(self, k, v):
        self._filters.append(("lte", (k, v)))
        return self

    def in_(self, k, vs):
        self._filters.append(("in", (k, tuple(vs))))
        return self

    def not_(self):
        # Fallback: 同样实现 neg filter 包装器 (与 _ChainQuery 共享逻辑)
        outer = self
        class _Neg:
            def in_(self_inner, k, vs):
                outer._neg_filters.append(("in", (k, tuple(vs))))
                return outer

            def eq(self_inner, k, v):
                outer._neg_filters.append(("eq", (k, v)))
                return outer

            def is_(self_inner, k, v):
                outer._neg_filters.append(("is", (k, v)))
                return outer
        return _Neg()

    def ilike(self, k, v):
        self._filters.append(("ilike", (k, v)))
        return self

    # ---- ordering / paging ----
    def order(self, field, desc=False):
        self._order_field = field
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    def offset(self, n):
        self._offset = n
        return self

    # ---- single / maybe_single ----
    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    # ---- execute ----
    def execute(self):
        return self.state.run(self)


class _TableState:
    """单张表的内存状态 + 过滤执行."""

    def __init__(self, name: str, store: dict[str, list[dict]]):
        self.name = name
        self.store = store
        self.inserts: list[dict] = []
        self.updates: list[dict] = []
        self.deletes: list[dict] = []

    def _match(self, row: dict, ftype: str, fargs: tuple) -> bool:
        k, v = fargs
        if ftype == "eq":
            return row.get(k) == v
        if ftype == "gt":
            return row.get(k) is not None and row.get(k) > v
        if ftype == "lt":
            return row.get(k) is not None and row.get(k) < v
        if ftype == "gte":
            return row.get(k) is not None and row.get(k) >= v
        if ftype == "lte":
            return row.get(k) is not None and row.get(k) <= v
        if ftype == "in":
            return row.get(k) in v
        if ftype == "ilike":
            target = str(row.get(k) or "")
            needle = str(v).strip("%")
            return needle in target
        return True

    def run(self, q: "_FakeQuery"):
        # SELECT path
        if self.name in self.store:
            rows = list(self.store[self.name])
            for ftype, fargs in q._filters:
                rows = [r for r in rows if self._match(r, ftype, fargs)]
            if q._order_field:
                rows.sort(
                    key=lambda r: r.get(q._order_field) or "",
                    reverse=q._order_desc,
                )
            if q._range:
                a, b = q._range
                rows = rows[a:b + 1]
            if q._limit:
                rows = rows[:q._limit]
            if q._single:
                if not rows:
                    raise RuntimeError("no rows for single()")
                return SimpleNamespace(data=rows[0], count=len(rows))
            if q._maybe_single:
                return SimpleNamespace(data=rows[0] if rows else None, count=len(rows))
            return SimpleNamespace(data=rows, count=len(rows))
        # INSERT path
        if hasattr(q, "_insert_payload"):
            payload = q._insert_payload
            if isinstance(payload, list):
                inserted = []
                for p in payload:
                    p = dict(p)
                    if "id" not in p:
                        p["id"] = f"uuid-{len(self.inserts)}-{len(self.store.get(self.name, []))}"
                    p.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    self.inserts.append(p)
                    self.store.setdefault(self.name, []).append(p)
                    inserted.append(p)
                return SimpleNamespace(data=inserted, count=len(inserted))
            p = dict(payload)
            if "id" not in p:
                p["id"] = f"uuid-{len(self.inserts)}-{len(self.store.get(self.name, []))}"
            p.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            self.inserts.append(p)
            self.store.setdefault(self.name, []).append(p)
            return SimpleNamespace(data=[p], count=1)
        # UPDATE path
        if hasattr(q, "_update_payload"):
            payload = q._update_payload
            updated = []
            for ftype, fargs in q._filters:
                pass  # simple
            for row in self.store.get(self.name, []):
                ok = all(self._match(row, ftype, fargs) for ftype, fargs in q._filters)
                if ok:
                    row.update(payload)
                    updated.append(dict(row))
            self.updates.append({"payload": payload, "filters": q._filters})
            return SimpleNamespace(data=updated, count=len(updated))
        return SimpleNamespace(data=[], count=0)


class FakeSupabase:
    """最小 supabase 替身,支持 table().select/insert/update().execute()."""

    def __init__(self):
        self.store: dict[str, list[dict]] = {
            "tickets": [],
            "ticket_comments": [],
            "ticket_status_history": [],
            "ticket_sla_rules": [
                {"priority": "urgent", "first_response_hrs": 1, "resolution_hrs": 8, "is_active": True},
                {"priority": "high", "first_response_hrs": 2, "resolution_hrs": 24, "is_active": True},
                {"priority": "normal", "first_response_hrs": 8, "resolution_hrs": 72, "is_active": True},
                {"priority": "low", "first_response_hrs": 24, "resolution_hrs": 168, "is_active": True},
            ],
        }

    def table(self, name: str) -> _FakeQuery:
        if name not in self.store:
            self.store[name] = []
        q = _FakeQuery(_TableState(name, self.store))
        return q

    # 高阶方法
    def insert(self, payload):
        q = _FakeQuery(_TableState(self._last_table, self.store))
        q._insert_payload = payload
        return q

    def update(self, payload):
        q = _FakeQuery(_TableState(self._last_table, self.store))
        q._update_payload = payload
        return q

    def delete(self):
        return _FakeQuery(_TableState(self._last_table, self.store))

    def select(self, *_):
        return _FakeQuery(_TableState(self._last_table, self.store))


# 关键: supabase 客户端代码都是 `sb.table("x").insert(...).execute()` —
# 我们的 Fake 需要让 .table() 返回的对象既支持 .select / .insert / .update /
# .delete 等顶层调用,也支持链式 .eq().execute().
# 重新设计: 把 insert/update/select 当作 _FakeQuery 的方法 (table state 上).

class FakeSupabaseV2(FakeSupabase):
    """V2 — 把 insert/update/select 当 _FakeQuery 的方法,而不是顶层."""

    def table(self, name: str) -> _FakeQuery:
        if name not in self.store:
            self.store[name] = []
        ts = _TableState(name, self.store)
        return _ChainQuery(ts)


class _ChainQuery(_FakeQuery):
    """支持 _insert_payload / _update_payload."""

    def __init__(self, state: _TableState):
        super().__init__(state)
        self._insert_payload = None
        self._update_payload = None
        self._delete_mode = False
        self._neg_filters: list[tuple[str, tuple]] = []  # for .not_().in_()

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def delete(self):
        self._delete_mode = True
        return self

    def select(self, _fields: str = "*"):
        return self

    def not_(self):
        # 简化: 返回一个包装对象,其 .in_() 记录成 neg-filter
        outer = self
        class _Neg:
            def in_(self_inner, k, vs):
                outer._neg_filters.append(("in", (k, tuple(vs))))
                return outer

            def eq(self_inner, k, v):
                outer._neg_filters.append(("eq", (k, v)))
                return outer

            def is_(self_inner, k, v):
                outer._neg_filters.append(("is", (k, v)))
                return outer
        return _Neg()

    def execute(self):
        st = self.state
        if self._insert_payload is not None:
            payload = self._insert_payload
            if isinstance(payload, list):
                inserted = []
                for p in payload:
                    p = dict(p)
                    if "id" not in p:
                        p["id"] = f"uuid-{len(st.inserts)}-{len(st.store.get(st.name, []))}"
                    p.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                    st.inserts.append(p)
                    st.store.setdefault(st.name, []).append(p)
                    inserted.append(p)
                return SimpleNamespace(data=inserted, count=len(inserted))
            p = dict(payload)
            if "id" not in p:
                p["id"] = f"uuid-{len(st.inserts)}-{len(st.store.get(st.name, []))}"
            now_iso = datetime.now(timezone.utc).isoformat()
            p.setdefault("created_at", now_iso)
            p.setdefault("updated_at", now_iso)
            p.setdefault("changed_at", now_iso)
            st.inserts.append(p)
            st.store.setdefault(st.name, []).append(p)
            return SimpleNamespace(data=[p], count=1)
        if self._update_payload is not None:
            payload = self._update_payload
            updated = []
            for row in st.store.get(st.name, []):
                ok = all(st._match(row, ftype, fargs) for ftype, fargs in self._filters)
                if ok:
                    row.update(payload)
                    updated.append(dict(row))
            st.updates.append({"payload": payload, "filters": self._filters})
            return SimpleNamespace(data=updated, count=len(updated))
        if self._delete_mode:
            deleted = []
            for row in list(st.store.get(st.name, [])):
                ok = all(st._match(row, ftype, fargs) for ftype, fargs in self._filters)
                if ok:
                    st.store[st.name].remove(row)
                    deleted.append(row)
            st.deletes.append({"filters": self._filters})
            return SimpleNamespace(data=deleted, count=len(deleted))
        # SELECT path with optional negation
        if st.name in st.store:
            rows = list(st.store[st.name])
            for ftype, fargs in self._filters:
                rows = [r for r in rows if st._match(r, ftype, fargs)]
            for ftype, fargs in self._neg_filters:
                rows = [r for r in rows if not st._match(r, ftype, fargs)]
            if self._order_field:
                rows.sort(
                    key=lambda r: r.get(self._order_field) or "",
                    reverse=self._order_desc,
                )
            if self._range:
                a, b = self._range
                rows = rows[a:b + 1]
            if self._limit:
                rows = rows[:self._limit]
            if self._single:
                if not rows:
                    raise RuntimeError("no rows for single()")
                return SimpleNamespace(data=rows[0], count=len(rows))
            if self._maybe_single:
                return SimpleNamespace(data=rows[0] if rows else None, count=len(rows))
            return SimpleNamespace(data=rows, count=len(rows))
        return SimpleNamespace(data=[], count=0)


# 替换: 用 V2 作为默认 fake
FakeSupabase = FakeSupabaseV2


@pytest.fixture
def fake_supabase():
    return FakeSupabase()


# ---------------------------------------------------------------------------
# 1. SLA 计算
# ---------------------------------------------------------------------------
class TestSLAComputation:
    def test_compute_sla_due_at_default(self):
        from services.ticket_service import compute_sla_due_at

        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_at("urgent", base=now)
        assert due == now + timedelta(hours=8)

    def test_compute_sla_due_at_normal(self):
        from services.ticket_service import compute_sla_due_at

        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_at("normal", base=now)
        assert due == now + timedelta(hours=72)

    def test_compute_sla_due_at_low(self):
        from services.ticket_service import compute_sla_due_at

        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_at("low", base=now)
        assert due == now + timedelta(hours=168)

    def test_compute_sla_due_at_invalid_priority(self):
        from services.ticket_service import compute_sla_due_at

        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_at("WRONG", base=now)
        assert due == now + timedelta(hours=72)  # 降级 normal

    def test_compute_sla_due_from_rules_table(self, fake_supabase):
        from services.ticket_service import compute_sla_due_from_rules

        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_from_rules(fake_supabase, "urgent", base=now)
        assert due == now + timedelta(hours=8)

    def test_compute_sla_due_from_rules_fallback(self, fake_supabase):
        from services.ticket_service import compute_sla_due_from_rules

        # 删掉规则 → fallback
        fake_supabase.store["ticket_sla_rules"] = []
        now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
        due = compute_sla_due_from_rules(fake_supabase, "urgent", base=now)
        assert due == now + timedelta(hours=8)  # 默认


# ---------------------------------------------------------------------------
# 2. 状态机
# ---------------------------------------------------------------------------
class TestStateMachine:
    def test_open_to_in_progress(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("open", "in_progress") is True

    def test_open_to_closed(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("open", "closed") is True

    def test_closed_is_terminal(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("closed", "open") is False
        assert is_valid_transition("closed", "in_progress") is False

    def test_awaiting_user_roundtrip(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("in_progress", "awaiting_user") is True
        assert is_valid_transition("awaiting_user", "in_progress") is True

    def test_resolved_can_reopen(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("resolved", "in_progress") is True
        assert is_valid_transition("resolved", "closed") is True
        assert is_valid_transition("resolved", "open") is False

    def test_same_status_noop(self):
        from services.ticket_service import is_valid_transition

        assert is_valid_transition("open", "open") is True

    def test_assert_invalid_raises(self):
        from services.ticket_service import (
            InvalidTransitionError,
            assert_valid_transition,
        )

        with pytest.raises(InvalidTransitionError):
            assert_valid_transition("closed", "open")


# ---------------------------------------------------------------------------
# 3. create_ticket
# ---------------------------------------------------------------------------
class TestCreateTicket:
    def test_basic_create(self, fake_supabase):
        from services.ticket_service import create_ticket

        t = create_ticket(
            fake_supabase,
            user_id="user-1",
            title="工资被拖欠",
            description="已经 2 个月没发工资了",
            priority="high",
            category="payroll",
        )
        assert t.title == "工资被拖欠"
        assert t.status == "open"
        assert t.priority == "high"
        assert t.user_id == "user-1"
        assert t.sla_due_at is not None

    def test_create_writes_initial_history(self, fake_supabase):
        from services.ticket_service import create_ticket

        t = create_ticket(
            fake_supabase,
            user_id="user-1",
            title="x",
            auto_create=True,
        )
        # ticket_status_history 应该有一条初始 (None → open)
        hist = fake_supabase.store["ticket_status_history"]
        assert len(hist) == 1
        assert hist[0]["from_status"] is None
        assert hist[0]["to_status"] == "open"
        assert hist[0]["reason"] == "auto_create"
        assert hist[0]["metadata"]["source"] == "auto"

    def test_create_strips_empty_title(self):
        from services.ticket_service import TicketError, create_ticket

        with pytest.raises(TicketError):
            create_ticket(MagicMock(), user_id="u", title="   ")

    def test_create_invalid_priority_fallback(self, fake_supabase):
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x", priority="WRONG")
        assert t.priority == "normal"

    def test_create_invalid_category_fallback(self, fake_supabase):
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x", category="WRONG")
        assert t.category == "hr"

    def test_create_with_metadata(self, fake_supabase):
        from services.ticket_service import create_ticket

        t = create_ticket(
            fake_supabase,
            user_id="u",
            title="x",
            metadata={"source": "agent", "agent_name": "hr_service_agent"},
        )
        assert t.metadata["source"] == "agent"
        assert t.metadata["agent_name"] == "hr_service_agent"


# ---------------------------------------------------------------------------
# 4. 状态转移
# ---------------------------------------------------------------------------
class TestTransitionStatus:
    def _seed(self, fake_supabase):
        from services.ticket_service import create_ticket

        return create_ticket(fake_supabase, user_id="user-1", title="t")

    def test_open_to_in_progress_records_first_response(self, fake_supabase):
        from services.ticket_service import transition_status

        t = self._seed(fake_supabase)
        updated = transition_status(
            fake_supabase, t.id, to_status="in_progress", changed_by="hr-1"
        )
        assert updated.status == "in_progress"
        assert updated.first_responded_at is not None

    def test_to_resolved_records_resolved_at(self, fake_supabase):
        from services.ticket_service import transition_status

        t = self._seed(fake_supabase)
        # 先 in_progress
        transition_status(fake_supabase, t.id, to_status="in_progress", changed_by="hr")
        # 再 resolved
        updated = transition_status(fake_supabase, t.id, to_status="resolved", changed_by="hr")
        assert updated.status == "resolved"
        assert updated.resolved_at is not None

    def test_to_closed_records_closed_at(self, fake_supabase):
        from services.ticket_service import transition_status

        t = self._seed(fake_supabase)
        updated = transition_status(fake_supabase, t.id, to_status="closed", changed_by="hr")
        assert updated.status == "closed"
        assert updated.closed_at is not None

    def test_invalid_transition_raises(self, fake_supabase):
        from services.ticket_service import (
            InvalidTransitionError,
            create_ticket,
            transition_status,
        )

        t = create_ticket(fake_supabase, user_id="u", title="t")
        transition_status(fake_supabase, t.id, to_status="closed", changed_by="hr")
        with pytest.raises(InvalidTransitionError):
            transition_status(fake_supabase, t.id, to_status="open", changed_by="hr")

    def test_status_history_written(self, fake_supabase):
        from services.ticket_service import create_ticket, transition_status

        t = create_ticket(fake_supabase, user_id="u", title="t")
        transition_status(fake_supabase, t.id, to_status="in_progress", changed_by="hr")
        transition_status(fake_supabase, t.id, to_status="resolved", changed_by="hr")

        hist = fake_supabase.store["ticket_status_history"]
        # 1 (initial) + 2 transitions = 3
        assert len(hist) == 3
        assert hist[1]["from_status"] == "open"
        assert hist[1]["to_status"] == "in_progress"
        assert hist[2]["from_status"] == "in_progress"
        assert hist[2]["to_status"] == "resolved"

    def test_not_found_raises(self, fake_supabase):
        from services.ticket_service import TicketError, transition_status

        with pytest.raises(TicketError):
            transition_status(fake_supabase, "nonexistent", to_status="in_progress", changed_by="u")

    def test_same_status_noop(self, fake_supabase):
        from services.ticket_service import create_ticket, transition_status

        t = create_ticket(fake_supabase, user_id="u", title="t")
        result = transition_status(fake_supabase, t.id, to_status="open", changed_by="hr")
        assert result.id == t.id


# ---------------------------------------------------------------------------
# 5. 评论 + Timeline
# ---------------------------------------------------------------------------
class TestCommentsAndTimeline:
    def test_add_comment(self, fake_supabase):
        from services.ticket_service import add_comment, create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="t")
        c = add_comment(
            fake_supabase,
            t.id,
            author_id="u",
            body="补充信息",
            author_type="employee",
        )
        assert c["body"] == "补充信息"
        assert c["author_type"] == "employee"

    def test_add_comment_empty_body(self, fake_supabase):
        from services.ticket_service import (
            TicketError,
            add_comment,
            create_ticket,
        )

        t = create_ticket(fake_supabase, user_id="u", title="t")
        with pytest.raises(TicketError):
            add_comment(fake_supabase, t.id, author_id="u", body="   ")

    def test_add_comment_invalid_author_type(self, fake_supabase):
        from services.ticket_service import add_comment, create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="t")
        c = add_comment(
            fake_supabase,
            t.id,
            author_id="u",
            body="hi",
            author_type="WRONG",
        )
        assert c["author_type"] == "employee"

    def test_timeline_merges_history_and_comments(self, fake_supabase):
        from services.ticket_service import (
            add_comment,
            create_ticket,
            get_timeline,
            transition_status,
        )

        t = create_ticket(fake_supabase, user_id="u", title="t")
        transition_status(fake_supabase, t.id, to_status="in_progress", changed_by="hr")
        add_comment(fake_supabase, t.id, author_id="u", body="补充")

        timeline = get_timeline(fake_supabase, t.id)
        kinds = [e["kind"] for e in timeline]
        # 1 status (initial) + 1 status transition + 1 comment = 3
        assert len(timeline) == 3
        assert kinds.count("status") == 2
        assert kinds.count("comment") == 1
        # 排序按时间
        for i in range(len(timeline) - 1):
            assert timeline[i]["at"] <= timeline[i + 1]["at"]


# ---------------------------------------------------------------------------
# 6. list / get / overdue
# ---------------------------------------------------------------------------
class TestListAndGet:
    def test_get_ticket(self, fake_supabase):
        from services.ticket_service import create_ticket, get_ticket

        t = create_ticket(fake_supabase, user_id="u", title="t")
        got = get_ticket(fake_supabase, t.id)
        assert got is not None
        assert got.title == "t"

    def test_get_nonexistent(self, fake_supabase):
        from services.ticket_service import get_ticket

        assert get_ticket(fake_supabase, "nope") is None

    def test_list_my_tickets(self, fake_supabase):
        from services.ticket_service import (
            create_ticket,
            list_my_tickets,
            list_tickets,
        )

        create_ticket(fake_supabase, user_id="u1", title="t1")
        create_ticket(fake_supabase, user_id="u1", title="t2")
        create_ticket(fake_supabase, user_id="u2", title="t3")

        mine = list_my_tickets(fake_supabase, "u1")
        assert len(mine) == 2

        all_t = list_tickets(fake_supabase)
        assert len(all_t) == 3

    def test_list_filter_by_status(self, fake_supabase):
        from services.ticket_service import (
            create_ticket,
            list_tickets,
            transition_status,
        )

        t1 = create_ticket(fake_supabase, user_id="u", title="a")
        create_ticket(fake_supabase, user_id="u", title="b")
        transition_status(fake_supabase, t1.id, to_status="in_progress", changed_by="hr")

        in_prog = list_tickets(fake_supabase, status="in_progress")
        assert len(in_prog) == 1
        open_t = list_tickets(fake_supabase, status="open")
        assert len(open_t) == 1

    def test_list_overdue(self, fake_supabase):
        from services.ticket_service import (
            create_ticket,
            list_overdue_tickets,
            transition_status,
        )

        t = create_ticket(fake_supabase, user_id="u", title="t", priority="urgent")
        # 把 sla_due_at 改成过去
        ts = fake_supabase.store["tickets"][-1]
        ts["sla_due_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        overdue = list_overdue_tickets(fake_supabase)
        assert len(overdue) == 1
        assert overdue[0]["id"] == t.id


# ---------------------------------------------------------------------------
# 7. update_ticket_meta
# ---------------------------------------------------------------------------
class TestUpdateMeta:
    def test_update_title(self, fake_supabase):
        from services.ticket_service import (
            create_ticket,
            update_ticket_meta,
        )

        t = create_ticket(fake_supabase, user_id="u", title="old")
        updated = update_ticket_meta(fake_supabase, t.id, title="new")
        assert updated.title == "new"

    def test_update_empty(self, fake_supabase):
        from services.ticket_service import create_ticket, update_ticket_meta

        t = create_ticket(fake_supabase, user_id="u", title="x")
        updated = update_ticket_meta(fake_supabase, t.id)
        assert updated.title == "x"  # no change

    def test_update_invalid_priority(self, fake_supabase):
        from services.ticket_service import (
            TicketError,
            create_ticket,
            update_ticket_meta,
        )

        t = create_ticket(fake_supabase, user_id="u", title="x")
        with pytest.raises(TicketError):
            update_ticket_meta(fake_supabase, t.id, priority="WRONG")

    def test_update_not_found(self, fake_supabase):
        from services.ticket_service import (
            TicketError,
            update_ticket_meta,
        )

        with pytest.raises(TicketError):
            update_ticket_meta(fake_supabase, "nope", title="x")


# ---------------------------------------------------------------------------
# 8. 工单 ↔ dict
# ---------------------------------------------------------------------------
class TestTicketDataclass:
    def test_from_row(self):
        from services.ticket_service import Ticket

        row = {
            "id": "t-1",
            "user_id": "u-1",
            "organisation_id": None,
            "title": "hi",
            "description": "d",
            "status": "open",
            "priority": "high",
            "category": "hr",
            "assignee_id": None,
            "sla_due_at": None,
            "first_responded_at": None,
            "resolved_at": None,
            "closed_at": None,
            "metadata": {},
            "tags": [],
            "created_at": "2026-07-01T00:00:00Z",
            "updated_at": "2026-07-01T00:00:00Z",
        }
        t = Ticket.from_row(row)
        assert t.id == "t-1"
        d = t.to_dict()
        assert d["title"] == "hi"
        assert d["status"] == "open"


# ---------------------------------------------------------------------------
# 9. hr_service_agent 敏感检测
# ---------------------------------------------------------------------------
class TestHRSensitiveDetection:
    def test_detect_sensitive_payroll(self):
        from agents.employer.hr_service_agent import _detect_sensitive

        s, cat, pri = _detect_sensitive("公司拖欠工资两个月")
        assert s is True
        assert cat == "payroll"
        assert pri == "high"

    def test_detect_sensitive_harassment(self):
        from agents.employer.hr_service_agent import _detect_sensitive

        s, cat, pri = _detect_sensitive("我遭受了性骚扰")
        assert s is True
        assert pri == "urgent"

    def test_detect_sensitive_mental_crisis(self):
        from agents.employer.hr_service_agent import _detect_sensitive

        s, cat, pri = _detect_sensitive("最近想轻生")
        assert s is True
        assert pri == "urgent"

    def test_detect_sensitive_firing(self):
        from agents.employer.hr_service_agent import _detect_sensitive

        s, cat, pri = _detect_sensitive("我被解雇了")
        assert s is True
        assert pri == "urgent"

    def test_detect_sensitive_none(self):
        from agents.employer.hr_service_agent import _detect_sensitive

        s, _, _ = _detect_sensitive("我想问下年假怎么请")
        assert s is False

    def test_detect_stage_onboarding(self):
        from agents.employer.hr_service_agent import _detect_stage

        assert _detect_stage("明天入职需要带什么材料") == "onboarding"

    def test_detect_stage_offboarding(self):
        from agents.employer.hr_service_agent import _detect_stage

        assert _detect_stage("我准备离职,last day 怎么算") == "offboarding"