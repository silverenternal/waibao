"""T703 — Persona Memory 单测.

覆盖:
    - set_pref / get_prefs / get_pref / delete_pref CRUD
    - confidence < 0.5 不写入
    - infer_prefs_from_text (LLM 成功路径 + 关键词 fallback)
    - render_prefs_for_prompt 渲染
    - PersonaAgent 集成 (system prompt 注入 + 自动学习)
    - sensitive 触发 escalation
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.employer.persona_agent import PersonaAgent, _is_sensitive
from agents.runtime import AgentInput
from services.persona_memory import (
    MIN_CONFIDENCE,
    SOURCE_EXPLICIT,
    SOURCE_INFERRED,
    delete_pref,
    get_pref,
    get_prefs,
    infer_prefs_from_text,
    render_prefs_for_prompt,
    set_pref,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _FakeSupabase:
    """记录所有 upsert/select/delete 操作."""

    def __init__(self, existing=None):
        self.existing = dict(existing or {})  # key -> row
        self.upserts: list[dict] = []
        self.deletes: list[dict] = []

    def table(self, name):
        return _FakeTable(self, name)


class _FakeTable:
    def __init__(self, store: _FakeSupabase, name: str):
        self.store = store
        self.name = name
        self._filters: dict = {}

    def select(self, *_):
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def upsert(self, record, on_conflict=None):
        self.store.upserts.append(record)
        key = (record.get("user_id"), record.get("organisation_id"), record.get("pref_key"))
        self.store.existing[key] = record
        return self  # supabase SDK chain returns self, then .execute()

    def delete(self):
        return self

    def execute(self):
        # After upsert: return last upserted row
        if self.store.upserts and not self._filters:
            return _FakeResult([self.store.upserts[-1]])
        if self._filters.get("user_id"):
            user_id = self._filters["user_id"]
            pref_key = self._filters.get("pref_key")
            org_id = self._filters.get("organisation_id")
            rows = []
            for (u, o, k), r in self.store.existing.items():
                if u != user_id:
                    continue
                if pref_key is not None and k != pref_key:
                    continue
                if org_id is not None and o != org_id:
                    continue
                rows.append(r)
            # delete: pop
            if pref_key is not None:
                for k in list(self.store.existing.keys()):
                    if k[0] == user_id and k[2] == pref_key:
                        if org_id is None or k[1] == org_id:
                            del self.store.existing[k]
                            self.store.deletes.append({"user_id": user_id, "pref_key": pref_key})
            return _FakeResult(rows)
        return _FakeResult([])


class _FakeResult:
    def __init__(self, data):
        self.data = data


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_pref_basic():
    sb = _FakeSupabase()
    row = await set_pref(
        sb, user_id="u1", organisation_id="org1",
        pref_key="communication_style", pref_value={"value": "direct"},
        confidence=0.9,
    )
    assert row is not None
    assert row["pref_key"] == "communication_style"
    assert sb.upserts[0]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_set_pref_low_confidence_rejected():
    sb = _FakeSupabase()
    row = await set_pref(
        sb, user_id="u1", organisation_id="org1",
        pref_key="preferred_terms", pref_value=["x"],
        confidence=0.4,  # < MIN_CONFIDENCE
    )
    assert row is None
    assert sb.upserts == []  # nothing written


@pytest.mark.asyncio
async def test_set_pref_default_confidence_explicit():
    sb = _FakeSupabase()
    row = await set_pref(
        sb, user_id="u1", organisation_id="org1",
        pref_key="time_zone", pref_value="Asia/Shanghai",
    )
    assert row is not None
    assert row["source"] == SOURCE_EXPLICIT
    assert row["confidence"] >= MIN_CONFIDENCE


@pytest.mark.asyncio
async def test_get_prefs_filters_by_user():
    sb = _FakeSupabase(existing={
        ("u1", "org1", "communication_style"): {"pref_key": "communication_style", "pref_value": {"value": "direct"}, "confidence": 0.9},
        ("u2", "org1", "communication_style"): {"pref_key": "communication_style", "pref_value": {"value": "gentle"}, "confidence": 0.9},
    })
    prefs = await get_prefs(sb, "u1", "org1")
    assert "communication_style" in prefs
    assert prefs["communication_style"]["pref_value"]["value"] == "direct"


@pytest.mark.asyncio
async def test_get_prefs_no_org_filter():
    sb = _FakeSupabase(existing={
        ("u1", "org1", "k1"): {"pref_key": "k1", "pref_value": "v1"},
        ("u1", "org2", "k2"): {"pref_key": "k2", "pref_value": "v2"},
    })
    prefs = await get_prefs(sb, "u1")  # both orgs
    assert len(prefs) == 2


@pytest.mark.asyncio
async def test_get_pref_returns_single():
    sb = _FakeSupabase(existing={
        ("u1", "org1", "communication_style"): {"pref_key": "communication_style", "pref_value": {"value": "direct"}},
    })
    p = await get_pref(sb, "u1", "communication_style", "org1")
    assert p is not None


@pytest.mark.asyncio
async def test_delete_pref():
    sb = _FakeSupabase(existing={
        ("u1", "org1", "x"): {"pref_key": "x", "pref_value": "v"},
    })
    ok = await delete_pref(sb, "u1", "x", "org1")
    assert ok is True
    assert sb.deletes


# ---------------------------------------------------------------------------
# 自动学习 — LLM 成功路径
# ---------------------------------------------------------------------------
class _FakeLLM:
    def __init__(self, json_response):
        self.json_response = json_response

    async def call(self, messages, response_format=None, **kw):
        return (self.json_response, 100, 50)


@pytest.mark.asyncio
async def test_infer_prefs_from_text_llm_success():
    sb = _FakeSupabase()
    llm = _FakeLLM(json.dumps({
        "prefs": [
            {"key": "communication_style", "value": "direct", "confidence": 0.85},
            {"key": "preferred_terms", "value": ["迭代", "数据驱动"], "confidence": 0.7},
        ]
    }))
    rows = await infer_prefs_from_text(sb, "u1", "org1", "我们直接做,不要绕", llm=llm)
    assert len(rows) == 2
    keys = {r["pref_key"] for r in rows}
    assert keys == {"communication_style", "preferred_terms"}


@pytest.mark.asyncio
async def test_infer_prefs_filters_low_confidence():
    sb = _FakeSupabase()
    llm = _FakeLLM(json.dumps({
        "prefs": [
            {"key": "communication_style", "value": "direct", "confidence": 0.85},
            {"key": "preferred_terms", "value": ["x"], "confidence": 0.3},  # 低 → 拒
        ]
    }))
    rows = await infer_prefs_from_text(sb, "u1", "org1", "我们直接做", llm=llm)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_infer_prefs_empty_text():
    sb = _FakeSupabase()
    rows = await infer_prefs_from_text(sb, "u1", "org1", "", llm=None)
    assert rows == []


# ---------------------------------------------------------------------------
# 关键词 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_infer_prefs_keyword_fallback_direct():
    sb = _FakeSupabase()
    rows = await infer_prefs_from_text(sb, "u1", "org1", "直接说,不要绕弯子", llm=None)
    keys = {r["pref_key"] for r in rows}
    assert "communication_style" in keys


@pytest.mark.asyncio
async def test_infer_prefs_keyword_fallback_gentle():
    sb = _FakeSupabase()
    rows = await infer_prefs_from_text(sb, "u1", "org1", "麻烦你了,辛苦,感谢!", llm=None)
    styles = [r for r in rows if r["pref_key"] == "communication_style"]
    assert styles and styles[0]["pref_value"] == "gentle"


@pytest.mark.asyncio
async def test_infer_prefs_keyword_fallback_formal():
    sb = _FakeSupabase()
    rows = await infer_prefs_from_text(sb, "u1", "org1", "根据以下材料,依据政策", llm=None)
    styles = [r for r in rows if r["pref_key"] == "communication_style"]
    assert styles and styles[0]["pref_value"] == "formal"


# ---------------------------------------------------------------------------
# render_prefs_for_prompt
# ---------------------------------------------------------------------------
def test_render_prefs_empty():
    assert render_prefs_for_prompt({}) == ""


def test_render_prefs_with_data():
    prefs = {
        "communication_style": {
            "pref_value": {"value": "direct"},
            "source": "explicit",
            "confidence": 0.9,
        },
        "preferred_terms": {
            "pref_value": ["迭代", "数据驱动"],
            "source": "inferred",
            "confidence": 0.7,
        },
    }
    out = render_prefs_for_prompt(prefs)
    assert "communication_style" in out
    assert "direct" in out
    assert "迭代" in out
    assert "confidence=0.90" in out


# ---------------------------------------------------------------------------
# PersonaAgent 集成
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_persona_agent_injects_prefs():
    sb = _FakeSupabase(existing={
        ("u1", "org1", "communication_style"): {
            "pref_key": "communication_style",
            "pref_value": {"value": "direct"},
            "source": "explicit",
            "confidence": 0.95,
        }
    })
    agent = PersonaAgent(llm=None, memory=None)
    captured = {}

    async def fake_llm_call(llm, user_msg, system="", **kw):
        captured["system"] = system
        return "好的,我会直接回答。"

    with patch("agents.employer.persona_agent.llm_call", new=fake_llm_call), \
         patch("agents.employer.persona_agent.infer_prefs_from_text", new=AsyncMock(return_value=[])):
        out = await agent.run(AgentInput(
            user_id="u1", persona="boss", text="我想谈谈招聘策略",
            context={"supabase": sb, "organisation_id": "org1"},
        ))
    assert out.success
    assert "communication_style" in captured["system"]
    assert "direct" in captured["system"]
    assert out.artifacts["prefs_count"] >= 1


@pytest.mark.asyncio
async def test_persona_agent_sensitive_triggers_escalation():
    sb = _FakeSupabase()

    # 模拟 ticket_service.create_ticket
    fake_ticket = MagicMock(id="ticket-abc-123", no="T-001")
    with patch("services.ticket_service.create_ticket", return_value=fake_ticket) as ct, \
         patch("agents.employer.persona_agent.llm_call", new=AsyncMock(return_value="敏感问题已升级")), \
         patch("agents.employer.persona_agent.infer_prefs_from_text", new=AsyncMock(return_value=[])):
        agent = PersonaAgent(llm=None, memory=None)
        out = await agent.run(AgentInput(
            user_id="u1", persona="hr", text="我被拖欠工资了",
            context={"supabase": sb, "organisation_id": "org1", "asker_role": "employee"},
        ))
    assert out.success
    assert out.artifacts["sensitive_detected"] is True
    assert out.artifacts["escalation"]["ticket_id"] == "ticket-abc-123"
    assert "ticket-a" in out.text  # truncated to 8 chars


@pytest.mark.asyncio
async def test_persona_agent_sensitive_urgent_priority():
    sb = _FakeSupabase()
    fake_ticket = MagicMock(id="ticket-urgent", no="T-002")
    with patch("services.ticket_service.create_ticket", return_value=fake_ticket) as ct, \
         patch("agents.employer.persona_agent.llm_call", new=AsyncMock(return_value="ok")), \
         patch("agents.employer.persona_agent.infer_prefs_from_text", new=AsyncMock(return_value=[])):
        agent = PersonaAgent(llm=None, memory=None)
        await agent.run(AgentInput(
            user_id="u1", persona="hr", text="我不想活了",
            context={"supabase": sb, "organisation_id": "org1"},
        ))
    assert ct.called
    kwargs = ct.call_args.kwargs
    assert kwargs["priority"] == "urgent"


@pytest.mark.asyncio
async def test_persona_agent_escalation_failure_does_not_crash():
    sb = _FakeSupabase()
    with patch("services.ticket_service.create_ticket", side_effect=RuntimeError("db down")), \
         patch("agents.employer.persona_agent.llm_call", new=AsyncMock(return_value="好")), \
         patch("agents.employer.persona_agent.infer_prefs_from_text", new=AsyncMock(return_value=[])):
        agent = PersonaAgent(llm=None, memory=None)
        out = await agent.run(AgentInput(
            user_id="u1", persona="hr", text="我被解雇",
            context={"supabase": sb, "organisation_id": "org1"},
        ))
    assert out.success
    assert out.artifacts["escalation"]["escalated"] is False


@pytest.mark.asyncio
async def test_persona_agent_persona_check_blocks_other_personas():
    agent = PersonaAgent(llm=None, memory=None)
    out = await agent.run(AgentInput(
        user_id="u1", persona="jobseeker", text="我想了解",
    ))
    assert not out.success
    assert "persona" in (out.error or "")


# ---------------------------------------------------------------------------
# _is_sensitive helper
# ---------------------------------------------------------------------------
def test_is_sensitive_true():
    assert _is_sensitive("我想了解工资条") is True
    assert _is_sensitive("老板要解雇我") is True
    assert _is_sensitive("不想活了") is True


def test_is_sensitive_false():
    assert _is_sensitive("如何招聘") is False
    assert _is_sensitive("今天天气不错") is False