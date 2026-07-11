"""T704 — Escalation + HRBP ticket tests.

覆盖:
    - /api/escalation 创建工单 + 自动建议 HRBP
    - 优先级推断 (urgent / high / normal)
    - 部门推断
    - HRBP 候选人搜索 (按部门 + role 匹配)
    - 升级失败路径
    - 工单 metadata 含 suggested_hrbp
    - /api/escalation/suggest-hrbp
    - PersonaAgent / hr_service_agent 触发 escalation
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _FakeSupabase:
    def __init__(self, members=None):
        self.members = members or []  # list of dict rows for org_members
        self.upserts: list[dict] = []
        self._current = None

    def table(self, name):
        self._current = name
        return self

    def select(self, *_):
        return self

    def eq(self, k, v):
        if self._current == "org_members":
            self.members = [m for m in self.members if m.get(k) == v] or self.members
        return self

    def upsert(self, record, on_conflict=None):
        self.upserts.append(record)
        return self

    def execute(self):
        if self._current == "org_members":
            return MagicMock(data=self.members)
        return MagicMock(data=[])


# ---------------------------------------------------------------------------
# 优先级推断
# ---------------------------------------------------------------------------
def test_infer_priority_urgent():
    from api.escalation import _infer_priority
    assert _infer_priority("我不想活了") == "urgent"
    assert _infer_priority("老板性骚扰我") == "urgent"
    assert _infer_priority("发生工伤") == "urgent"


def test_infer_priority_high():
    from api.escalation import _infer_priority
    assert _infer_priority("公司要降薪") == "high"
    assert _infer_priority("拖欠加班费") == "high"
    assert _infer_priority("仲裁") == "high"


def test_infer_priority_normal():
    from api.escalation import _infer_priority
    assert _infer_priority("普通咨询") == "normal"


def test_infer_priority_override():
    from api.escalation import _infer_priority
    assert _infer_priority("不想活了", default="low") == "low"
    assert _infer_priority("普通咨询", default="urgent") == "urgent"


def test_infer_priority_invalid_default():
    from api.escalation import _infer_priority
    assert _infer_priority("普通咨询", default="bogus") == "normal"


# ---------------------------------------------------------------------------
# 部门推断
# ---------------------------------------------------------------------------
def test_infer_department_payroll():
    from api.escalation import _infer_department
    assert _infer_department("工资不对") == "payroll"
    assert _infer_department("加班费") == "payroll"


def test_infer_department_it():
    from api.escalation import _infer_department
    assert _infer_department("代码权限") == "it"


def test_infer_department_recruiting():
    from api.escalation import _infer_department
    assert _infer_department("面试安排") == "recruiting"


def test_infer_department_training():
    from api.escalation import _infer_department
    assert _infer_department("培训课程") == "training"


def test_infer_department_general():
    from api.escalation import _infer_department
    assert _infer_department("随便聊聊") == "general"


def test_infer_department_override():
    from api.escalation import _infer_department
    assert _infer_department("工资不对", ctx_dept="it") == "it"


# ---------------------------------------------------------------------------
# HRBP 建议
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_suggest_hrbp_match_by_role_and_dept():
    from api.escalation import _suggest_hrbp

    members = [
        {"user_id": "u1", "role": "hr", "department": "payroll", "display_name": "Alice HR"},
        {"user_id": "u2", "role": "engineer", "department": "payroll", "display_name": "Bob Eng"},
        {"user_id": "u3", "role": "dept_head", "department": "it", "display_name": "Carol DH"},
    ]
    sb = _FakeSupabase(members)
    suggested = await _suggest_hrbp(sb, "payroll", "org1")
    assert suggested is not None
    assert suggested["user_id"] == "u1"
    assert suggested["match_score"] >= 2


@pytest.mark.asyncio
async def test_suggest_hrbp_match_dept_head_when_dept_matches():
    from api.escalation import _suggest_hrbp

    members = [
        {"user_id": "u1", "role": "dept_head", "department": "it", "display_name": "Carol DH"},
        {"user_id": "u2", "role": "hr", "department": "general", "display_name": "Bob HR"},
    ]
    sb = _FakeSupabase(members)
    suggested = await _suggest_hrbp(sb, "it", "org1")
    # u2(hr) score=2; u1(dept_head+it match) score=2 → tie → first wins
    assert suggested is not None


@pytest.mark.asyncio
async def test_suggest_hrbp_fallback_first_member():
    from api.escalation import _suggest_hrbp

    members = [{"user_id": "u1", "role": "engineer", "department": "tech", "display_name": "X"}]
    sb = _FakeSupabase(members)
    suggested = await _suggest_hrbp(sb, "payroll", "org1")
    assert suggested["user_id"] == "u1"
    assert suggested["match_score"] == 0


@pytest.mark.asyncio
async def test_suggest_hrbp_no_members_returns_none():
    from api.escalation import _suggest_hrbp

    sb = _FakeSupabase([])
    suggested = await _suggest_hrbp(sb, "payroll", "org1")
    assert suggested is None


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_escalation_endpoint_creates_ticket():
    from api.escalation import EscalationRequest, escalate_to_human

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"

    sb = _FakeSupabase(members=[
        {"user_id": "hr1", "role": "hr", "department": "general", "display_name": "HR Alice"},
    ])
    fake_ticket = MagicMock(id="ticket-001", no="T-001")

    with patch("api.escalation.get_supabase_admin", return_value=sb), \
         patch("services.ticket_service.create_ticket", return_value=fake_ticket) as ct:
        out = await escalate_to_human(
            EscalationRequest(text="我想投诉上司", department="general"),
            user=fake_user,
        )
    assert out.success is True
    assert out.ticket_id == "ticket-001"
    assert out.assignee_id == "hr1"
    assert out.suggested_hrbp["user_id"] == "hr1"
    assert ct.called
    kwargs = ct.call_args.kwargs
    assert kwargs["priority"] == "normal"  # 投诉 → normal (no keyword match)
    assert "suggested_hrbp" in kwargs["metadata"]


@pytest.mark.asyncio
async def test_escalation_endpoint_no_hrbp():
    from api.escalation import EscalationRequest, escalate_to_human

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"

    sb = _FakeSupabase(members=[])
    fake_ticket = MagicMock(id="ticket-002", no="T-002")

    with patch("api.escalation.get_supabase_admin", return_value=sb), \
         patch("services.ticket_service.create_ticket", return_value=fake_ticket) as ct:
        out = await escalate_to_human(
            EscalationRequest(text="普通问题", department="general"),
            user=fake_user,
        )
    assert out.success is True
    assert out.suggested_hrbp is None
    assert out.assignee_id is None


@pytest.mark.asyncio
async def test_escalation_endpoint_rejects_empty_text():
    from api.escalation import EscalationRequest, escalate_to_human
    from fastapi import HTTPException

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"
    with pytest.raises(HTTPException):
        await escalate_to_human(
            EscalationRequest(text="   "),
            user=fake_user,
        )


@pytest.mark.asyncio
async def test_escalation_endpoint_ticket_creation_fails():
    from api.escalation import EscalationRequest, escalate_to_human
    from fastapi import HTTPException

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"

    sb = _FakeSupabase(members=[])
    with patch("api.escalation.get_supabase_admin", return_value=sb), \
         patch("services.ticket_service.create_ticket", side_effect=RuntimeError("db down")):
        with pytest.raises(HTTPException) as exc:
            await escalate_to_human(
                EscalationRequest(text="help"),
                user=fake_user,
            )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_suggest_hrbp_endpoint():
    from api.escalation import suggest_hrbp_endpoint

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"

    sb = _FakeSupabase(members=[
        {"user_id": "hr2", "role": "hr", "department": "it", "display_name": "HR Bob"},
    ])
    with patch("api.escalation.get_supabase_admin", return_value=sb):
        out = await suggest_hrbp_endpoint(department="it", organisation_id="org1", user=fake_user)
    assert out["department"] == "it"
    assert out["suggested_hrbp"]["user_id"] == "hr2"


# ---------------------------------------------------------------------------
# PersonaAgent 集成 (T704 的一部分)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_persona_agent_creates_ticket_for_sensitive():
    from agents.employer.persona_agent import PersonaAgent
    from agents.runtime import AgentInput

    sb = _FakeSupabase(members=[
        {"user_id": "hr3", "role": "hr", "department": "general", "display_name": "HR Carol"},
    ])
    fake_ticket = MagicMock(id="ticket-sens", no="T-S-1")

    with patch("services.ticket_service.create_ticket", return_value=fake_ticket) as ct, \
         patch("agents.employer.persona_agent.llm_call", new=MagicMock(__await__=None)), \
         patch("agents.employer.persona_agent.infer_prefs_from_text", new=MagicMock(__await__=None)):
        # patch llm_call as AsyncMock return
        from unittest.mock import AsyncMock
        with patch("agents.employer.persona_agent.llm_call", new=AsyncMock(return_value="好")), \
             patch("agents.employer.persona_agent.infer_prefs_from_text", new=AsyncMock(return_value=[])):
            agent = PersonaAgent(llm=None, memory=None)
            out = await agent.run(AgentInput(
                user_id="u1", persona="hr", text="我被性骚扰了",
                context={"supabase": sb, "organisation_id": "org1"},
            ))
    assert out.success
    assert out.artifacts["sensitive_detected"] is True
    assert out.artifacts["escalation"]["ticket_id"] == "ticket-sens"
    assert ct.call_args.kwargs["priority"] == "urgent"
    assert "needs_hrbp" in ct.call_args.kwargs["tags"]


# ---------------------------------------------------------------------------
# 工单 metadata 包含 suggested_hrbp
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_escalation_metadata_includes_department_and_hrbp():
    from api.escalation import EscalationRequest, escalate_to_human

    fake_user = MagicMock()
    fake_user.id = "u1"
    fake_user.role.value = "employee"
    sb = _FakeSupabase(members=[
        {"user_id": "hr4", "role": "hr", "department": "payroll", "display_name": "HR Eve"},
    ])
    fake_ticket = MagicMock(id="t9", no="T-9")
    captured = {}
    def fake_create(supabase, **kwargs):
        captured.update(kwargs)
        return fake_ticket

    with patch("api.escalation.get_supabase_admin", return_value=sb), \
         patch("services.ticket_service.create_ticket", side_effect=fake_create):
        await escalate_to_human(
            EscalationRequest(text="工资算错了", department="payroll"),
            user=fake_user,
        )
    md = captured["metadata"]
    assert md["department"] == "payroll"
    assert md["suggested_hrbp"]["user_id"] == "hr4"
    assert "needs_hrbp" not in captured["tags"]  # not via persona_agent
    assert "manual" in captured["tags"]