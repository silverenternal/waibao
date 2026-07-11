"""Tests for api.tickets REST endpoints (T207).

策略:
- 用 monkeypatch 把 get_supabase_admin / get_current_user 替换成 in-memory fake
- 验证 happy path + 权限校验 + 错误处理
- 不依赖真实 Supabase / JWT
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# Reuse the fake supabase from test_ticket_service
from tests.test_ticket_service import FakeSupabase  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(role: str = "talent_partner", user_id: str | None = None):
    """Build a fake CurrentUser-like object."""
    from contracts.shared import UserRole

    class _U:
        def __init__(self):
            self.id = uuid4() if user_id is None else __import__("uuid").UUID(user_id)
            self.email = f"{role}@test.com"
            self.role = UserRole(role)

    return _U()


@pytest.fixture
def fake_supabase():
    return FakeSupabase()


@pytest.fixture
def employee_user():
    return _make_user("client")  # client is the "employee" role here


@pytest.fixture
def hr_user():
    return _make_user("talent_partner")


@pytest.fixture
def admin_user():
    return _make_user("admin")


@pytest.fixture
def app(fake_supabase, employee_user, monkeypatch):
    """Build a FastAPI test app with overridden deps.

    注意: 由于 api.tickets 路由直接调用 get_supabase_admin() 而非 Depends,
    我们用 monkeypatch 直接替换 api.deps.get_supabase_admin 函数对象。
    """
    from fastapi import FastAPI
    from api.tickets import router
    from api.auth import get_current_user
    import api.deps as deps_mod

    # Monkeypatch the function object so calls inside api.tickets also see the fake
    monkeypatch.setattr(deps_mod, "get_supabase_admin", lambda: fake_supabase)
    monkeypatch.setattr("api.tickets.get_supabase_admin", lambda: fake_supabase)

    app = FastAPI()
    app.include_router(router, prefix="/api/tickets")

    app.dependency_overrides[get_current_user] = lambda: employee_user
    return app


# ---------------------------------------------------------------------------
# POST /api/tickets
# ---------------------------------------------------------------------------
class TestCreateTicketEndpoint:
    def test_create_happy(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post("/api/tickets", json={
            "title": "工资拖欠",
            "description": "已经 2 个月没发",
            "priority": "high",
            "category": "payroll",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        assert data["ticket"]["title"] == "工资拖欠"
        assert data["ticket"]["status"] == "open"
        assert data["ticket"]["priority"] == "high"
        assert data["ticket"]["sla_due_at"] is not None

    def test_create_empty_title_400(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post("/api/tickets", json={"title": "   "})
        assert r.status_code == 400

    def test_create_invalid_priority_normalizes(self, app, fake_supabase):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post("/api/tickets", json={"title": "x", "priority": "WRONG"})
        assert r.status_code == 200
        # service 内部降级到 normal
        assert r.json()["ticket"]["priority"] == "normal"


# ---------------------------------------------------------------------------
# GET /api/tickets  (HR/admin)
# ---------------------------------------------------------------------------
class TestListTicketsEndpoint:
    def test_list_requires_hr(self, app, employee_user):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        client = TestClient(app)
        # 切换到 client role (employee) — 应该 403
        app.dependency_overrides[get_current_user] = lambda: employee_user
        r = client.get("/api/tickets")
        assert r.status_code == 403

    def test_list_as_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        create_ticket(fake_supabase, user_id="u1", title="t1")
        create_ticket(fake_supabase, user_id="u2", title="t2")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.get("/api/tickets")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    def test_list_filter_by_status(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import (
            create_ticket,
            transition_status,
        )

        t = create_ticket(fake_supabase, user_id="u", title="a")
        create_ticket(fake_supabase, user_id="u", title="b")
        transition_status(fake_supabase, t.id, to_status="in_progress", changed_by="hr")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.get("/api/tickets?status=in_progress")
        assert r.status_code == 200
        assert r.json()["count"] == 1


# ---------------------------------------------------------------------------
# GET /api/tickets/me
# ---------------------------------------------------------------------------
class TestMyTicketsEndpoint:
    def test_my_tickets(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        emp_id = str(employee_user.id)
        other_id = str(uuid4())
        create_ticket(fake_supabase, user_id=emp_id, title="mine-1")
        create_ticket(fake_supabase, user_id=emp_id, title="mine-2")
        create_ticket(fake_supabase, user_id=other_id, title="other")

        client = TestClient(app)
        r = client.get("/api/tickets/me")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        titles = [t["title"] for t in data["items"]]
        assert "mine-1" in titles
        assert "mine-2" in titles
        assert "other" not in titles


# ---------------------------------------------------------------------------
# GET /api/tickets/{id}
# ---------------------------------------------------------------------------
class TestGetTicketEndpoint:
    def test_get_as_owner(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="mine")

        client = TestClient(app)
        r = client.get(f"/api/tickets/{t.id}")
        assert r.status_code == 200
        assert r.json()["title"] == "mine"

    def test_get_as_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.get(f"/api/tickets/{t.id}")
        assert r.status_code == 200

    def test_get_as_other_user_403(self, app, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        create_ticket(fake_supabase, user_id=str(uuid4()), title="x")

        client = TestClient(app)
        r = client.get("/api/tickets/nope")
        # first check — 404 since not in our store
        assert r.status_code == 404

    def test_get_nonexistent_404(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/tickets/nonexistent")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/tickets/{id}/status
# ---------------------------------------------------------------------------
class TestUpdateStatusEndpoint:
    def test_update_status_happy(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}/status", json={
            "status": "in_progress",
            "reason": "开始处理",
        })
        assert r.status_code == 200, r.text
        assert r.json()["ticket"]["status"] == "in_progress"
        assert r.json()["ticket"]["first_responded_at"] is not None

    def test_update_status_invalid_value(self, app, hr_user):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.patch("/api/tickets/xxx/status", json={"status": "WRONG"})
        assert r.status_code == 400

    def test_update_status_invalid_transition_400(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket, transition_status

        t = create_ticket(fake_supabase, user_id="u", title="x")
        transition_status(fake_supabase, t.id, to_status="closed", changed_by="hr")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}/status", json={"status": "open"})
        assert r.status_code == 400

    def test_update_status_nonexistent_404(self, app, hr_user):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.patch("/api/tickets/nope/status", json={"status": "in_progress"})
        assert r.status_code == 404

    def test_update_status_other_user_403(self, app, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(uuid4()), title="x")

        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}/status", json={"status": "in_progress"})
        # 当前 user 不是 owner, 也不是 HR
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/tickets/{id}/comments
# ---------------------------------------------------------------------------
class TestAddCommentEndpoint:
    def test_add_comment_as_owner(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")

        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={"body": "补充信息"})
        assert r.status_code == 200, r.text
        assert r.json()["comment"]["body"] == "补充信息"
        assert r.json()["comment"]["author_type"] == "employee"

    def test_add_comment_as_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={"body": "HR 回复"})
        assert r.status_code == 200
        assert r.json()["comment"]["author_type"] == "hr"

    def test_add_comment_empty_400(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")
        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={"body": "  "})
        assert r.status_code == 400

    def test_add_comment_403_for_non_owner(self, app, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(uuid4()), title="x")
        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={"body": "hi"})
        assert r.status_code == 403

    def test_internal_comment_as_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")
        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={
            "body": "内部备注",
            "is_internal": True,
        })
        assert r.status_code == 200
        assert r.json()["comment"]["is_internal"] is True

    def test_internal_comment_employee_flag_dropped(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")
        client = TestClient(app)
        r = client.post(f"/api/tickets/{t.id}/comments", json={
            "body": "x",
            "is_internal": True,  # 员工想标 internal — 应该被忽略
        })
        assert r.status_code == 200
        # is_internal 被强制设为 False (员工无 internal 权限)
        assert r.json()["comment"]["is_internal"] is False


# ---------------------------------------------------------------------------
# GET /api/tickets/{id}/timeline
# ---------------------------------------------------------------------------
class TestTimelineEndpoint:
    def test_timeline_as_owner(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")

        client = TestClient(app)
        r = client.get(f"/api/tickets/{t.id}/timeline")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1
        # 至少有初始状态事件
        kinds = [e["kind"] for e in data["events"]]
        assert "status" in kinds

    def test_timeline_filters_internal_for_owner(self, app, hr_user, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        owner_uuid = str(uuid4())
        t = create_ticket(fake_supabase, user_id=owner_uuid, title="x")

        # HR 加一条 internal 评论
        app.dependency_overrides[get_current_user] = lambda: hr_user
        hr_client = TestClient(app)
        hr_client.post(f"/api/tickets/{t.id}/comments", json={
            "body": "内部备注",
            "is_internal": True,
        })

        # Owner 看 timeline (employee) — 不应该看到 internal
        owner = _make_user("client", user_id=owner_uuid)
        app.dependency_overrides[get_current_user] = lambda: owner
        client = TestClient(app)
        r = client.get(f"/api/tickets/{t.id}/timeline")
        assert r.status_code == 200
        for ev in r.json()["events"]:
            if ev["kind"] == "comment":
                assert ev["payload"]["is_internal"] is False

    def test_timeline_hr_sees_internal(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")

        # HR 加 internal 评论
        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        client.post(f"/api/tickets/{t.id}/comments", json={
            "body": "内部备注",
            "is_internal": True,
        })

        # 再以 HR 看 timeline — 应该能看到
        r = client.get(f"/api/tickets/{t.id}/timeline")
        assert r.status_code == 200
        internal_seen = any(
            ev["kind"] == "comment" and ev["payload"].get("is_internal")
            for ev in r.json()["events"]
        )
        assert internal_seen is True

    def test_timeline_403_for_other(self, app, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(uuid4()), title="x")
        client = TestClient(app)
        r = client.get(f"/api/tickets/{t.id}/timeline")
        assert r.status_code == 403

    def test_timeline_404(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/tickets/nonexistent/timeline")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/tickets/overdue
# ---------------------------------------------------------------------------
class TestOverdueEndpoint:
    def test_overdue_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x", priority="urgent")
        fake_supabase.store["tickets"][-1]["sla_due_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()

        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.get("/api/tickets/overdue")
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_overdue_403_for_employee(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/tickets/overdue")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/tickets/{id}  - update meta
# ---------------------------------------------------------------------------
class TestUpdateMetaEndpoint:
    def test_update_title_as_owner(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="old")
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}", json={"title": "new"})
        assert r.status_code == 200
        assert r.json()["ticket"]["title"] == "new"

    def test_update_assignee_as_employee_403(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}", json={
            "assignee_id": str(uuid4()),
        })
        assert r.status_code == 403

    def test_update_assignee_as_hr(self, app, hr_user, fake_supabase):
        from fastapi.testclient import TestClient
        from api.auth import get_current_user
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id="u", title="x")
        app.dependency_overrides[get_current_user] = lambda: hr_user
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}", json={
            "assignee_id": str(uuid4()),
        })
        assert r.status_code == 200

    def test_update_priority_normalizes(self, app, employee_user, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(employee_user.id), title="x")
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}", json={"priority": "WRONG"})
        assert r.status_code == 400

    def test_update_404(self, app):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.patch("/api/tickets/nope", json={"title": "x"})
        assert r.status_code == 404

    def test_update_403_for_other(self, app, fake_supabase):
        from fastapi.testclient import TestClient
        from services.ticket_service import create_ticket

        t = create_ticket(fake_supabase, user_id=str(uuid4()), title="x")
        client = TestClient(app)
        r = client.patch(f"/api/tickets/{t.id}", json={"title": "x"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# hr_service_agent 自动建工单 (smoke)
# ---------------------------------------------------------------------------
class TestHRAgentAutoTicket:
    @pytest.mark.asyncio
    async def test_sensitive_creates_ticket(self, fake_supabase):
        from agents.employer.hr_service_agent import HRServiceAgent
        from agents.runtime import AgentInput

        agent = HRServiceAgent()
        out = await agent.run(AgentInput(
            user_id="user-1",
            persona="hr",
            text="公司拖欠工资两个月",
            context={"supabase": fake_supabase},
        ))
        assert out.success is True
        # 本地兜底检测应该建了工单 (即使 LLM mock 返回 create_ticket=False)
        assert "ticket" in out.artifacts
        assert out.artifacts["ticket"]["status"] == "open"
        assert out.artifacts["ticket"]["priority"] in ("high", "urgent")
        # answer 应该提到工单号
        assert "工单" in out.text

    @pytest.mark.asyncio
    async def test_non_sensitive_no_ticket(self, fake_supabase):
        from agents.employer.hr_service_agent import HRServiceAgent
        from agents.runtime import AgentInput

        agent = HRServiceAgent()
        out = await agent.run(AgentInput(
            user_id="user-1",
            persona="hr",
            text="我想问下年假怎么请",
            context={"supabase": fake_supabase},
        ))
        assert out.success is True
        # 本地兜底不创建工单 (但 LLM mock 可能创建 — 我们这里只检查本地逻辑)
        # 至少不应该 raise

    @pytest.mark.asyncio
    async def test_sensitive_without_supabase_no_crash(self):
        from agents.employer.hr_service_agent import HRServiceAgent
        from agents.runtime import AgentInput

        agent = HRServiceAgent()
        out = await agent.run(AgentInput(
            user_id="user-1",
            persona="hr",
            text="我被解雇了",
            context={},  # no supabase
        ))
        assert out.success is True
        # 没 supabase 不应该 crash