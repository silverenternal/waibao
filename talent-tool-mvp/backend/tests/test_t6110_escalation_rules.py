"""v11.0 T6110 — Mandatory human-escalation rules (self-harm + labour dispute).

Coverage:
  * agents.governance.EscalationRules keyword detection (both topics)
  * LLM advisory layer can only add, never suppress, a keyword hit
  * services.platform.escalation persist + ticket + notify + webhook
    side effects, and that raw_text is NEVER persisted
  * api.admin_risk_alerts GET (redacted) + POST /check (preview)
  * privacy: admin payload carries no verbatim conversation
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.governance import (
    EscalationRules,
    SELF_HARM_HOTLINE,
    SELF_HARM_MESSAGE,
    LABOUR_DISPUTE_MESSAGE,
)


# ===========================================================================
# EscalationRules — keyword detection
# ===========================================================================
class TestSelfHarmDetection:
    def test_detects_self_harm_chinese(self):
        rules = EscalationRules()
        hits = rules.scan("我真的不想活了,想自杀")
        assert rules.must_escalate("我真的不想活了,想自杀")
        sh = next(h for h in hits if h.rule == "self_harm")
        assert sh.risk_level == "critical"
        assert SELF_HARM_HOTLINE in sh.message
        assert "自杀" in sh.matched_keywords or "不想活" in sh.matched_keywords

    def test_detects_self_harm_english(self):
        rules = EscalationRules()
        hits = rules.scan("I want to kill myself")
        assert any(h.rule == "self_harm" for h in hits)
        assert hits[0].risk_level == "critical"

    def test_self_harm_message_contains_hotline(self):
        assert "400-161-9995" in SELF_HARM_MESSAGE

    def test_clean_text_no_hit(self):
        rules = EscalationRules()
        assert rules.must_escalate("我想了解一下公司的加班制度") is False
        assert rules.scan("今天天气真好") == []


class TestLabourDisputeDetection:
    def test_detects_arbitration(self):
        rules = EscalationRules()
        hits = rules.scan("我要申请劳动仲裁,公司违法解除合同")
        ld = next(h for h in hits if h.rule == "labour_dispute")
        assert ld.risk_level == "high"
        assert "仲裁" in ld.matched_keywords

    def test_detects_unpaid_wages(self):
        rules = EscalationRules()
        assert rules.must_escalate("公司拖欠工资三个月了")

    def test_detects_severance(self):
        rules = EscalationRules()
        hits = rules.scan("他们辞退我不给辞退补偿")
        assert any(h.rule == "labour_dispute" for h in hits)

    def test_labour_dispute_message_mentions_hr_legal(self):
        assert "HR" in LABOUR_DISPUTE_MESSAGE or "法务" in LABOUR_DISPUTE_MESSAGE


class TestSeverityOrdering:
    def test_self_harm_sorts_before_labour_dispute(self):
        rules = EscalationRules()
        # A message hitting BOTH topics returns critical first.
        hits = rules.scan("我想自杀,而且公司违法辞退我不给补偿")
        assert hits[0].rule == "self_harm"
        assert hits[0].risk_level == "critical"
        assert any(h.rule == "labour_dispute" for h in hits)

    def test_highest_returns_none_for_clean(self):
        assert EscalationRules().highest("聊聊面试安排") is None


# ===========================================================================
# LLM advisory layer — can only ADD detections, never suppress keyword hits
# ===========================================================================
class TestLLMAdvisory:
    def test_llm_cannot_suppress_keyword_hit(self):
        rules = EscalationRules(llm_confirm=True)
        bad_llm = MagicMock()
        bad_llm.complete.return_value = MagicMock(text="NO")  # model says no
        # keyword says YES → still must escalate
        assert rules.must_escalate("我想自杀", llm=bad_llm) is True
        hits = rules.scan("我想自杀", llm=bad_llm)
        assert any(h.rule == "self_harm" for h in hits)

    def test_llm_can_add_self_harm_on_borderline_text(self):
        rules = EscalationRules(llm_confirm=True)
        llm = MagicMock()
        llm.complete.return_value = MagicMock(text="YES")
        # euphemism that misses keywords but LLM flags
        hits = rules.scan("我不想再醒过来了", llm=llm)
        assert any(h.rule == "self_harm" for h in hits)

    def test_llm_error_falls_back_safely(self):
        rules = EscalationRules(llm_confirm=True)
        llm = MagicMock()
        llm.complete.side_effect = RuntimeError("boom")
        # clean text + broken LLM → no hit, no exception
        assert rules.scan("今天聊聊天", llm=llm) == []

    def test_llm_skipped_when_no_llm_supplied(self):
        rules = EscalationRules(llm_confirm=True)
        assert rules.must_escalate("普通问候") is False


# ===========================================================================
# services.platform.escalation — side effects + privacy
# ===========================================================================
class _FakeTable:
    def __init__(self, name, store):
        self.name = name
        self.store = store
        self._rows: list[dict] = []
        self._filters: dict = {}

    def insert(self, row):
        self._rows.append(row)
        return self

    def select(self, *_):
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def order(self, *a, **kw):
        return self

    def limit(self, n):
        return self

    def execute(self):
        if self.name == "risk_alerts":
            rows = self._rows
            for k, v in self._filters.items():
                rows = [r for r in rows if r.get(k) == v]
            self._filters = {}
            return MagicMock(data=list(rows))
        return MagicMock(data=[])


class _FakeSupabase:
    def __init__(self):
        self.inserted = []
        self.tables = {}

    def table(self, name):
        t = self.tables.setdefault(name, _FakeTable(name, self))
        # capture inserts for assertions
        orig_insert = t.insert

        def capturing(row):
            self.inserted.append((name, row))
            return orig_insert(row)

        t.insert = capturing
        return t


@pytest.mark.asyncio
async def test_escalate_self_harm_persists_critical_and_notifies():
    from services.platform.escalation import escalate

    sb = _FakeSupabase()
    with patch("services.platform.escalation._open_ticket", return_value="tick-1") as ot, \
         patch("services.platform.escalation._notify_hr", new=AsyncMock(return_value=True)) as nh, \
         patch("services.platform.escalation._fire_webhook") as wh:
        rec = await escalate(
            user_id="u-selfharm",
            reason="检测到自伤/自杀风险信号,需立即转人工",
            risk_level="critical",
            metadata={
                "rule": "self_harm",
                "matched_keywords": ["自杀"],
                "organisation_id": "org1",
                "message": SELF_HARM_MESSAGE,
            },
            supabase=sb,
        )
    assert rec.risk_level == "critical"
    assert rec.rule == "self_harm"
    assert rec.ticket_id == "tick-1"
    assert rec.notified is True
    ot.assert_called_once()
    nh.assert_awaited_once()
    wh.assert_called_once()

    # persisted to risk_alerts
    inserts = [r for (t, r) in sb.inserted if t == "risk_alerts"]
    assert len(inserts) == 1
    row = inserts[0]
    assert row["risk_level"] == "critical"
    assert row["rule"] == "self_harm"
    assert SELF_HARM_HOTLINE in row["message"]


@pytest.mark.asyncio
async def test_escalate_labour_dispute_opens_high_ticket():
    from services.platform.escalation import escalate

    sb = _FakeSupabase()
    with patch("services.platform.escalation._open_ticket", return_value="tick-2") as ot, \
         patch("services.platform.escalation._notify_hr", new=AsyncMock(return_value=True)), \
         patch("services.platform.escalation._fire_webhook"):
        rec = await escalate(
            user_id="u-dispute",
            reason="检测到劳动争议信号",
            risk_level="high",
            metadata={"rule": "labour_dispute", "matched_keywords": ["仲裁"]},
            supabase=sb,
        )
    assert rec.risk_level == "high"
    assert rec.rule == "labour_dispute"
    # ticket opened with high priority for labour dispute
    kwargs = ot.call_args.kwargs
    assert kwargs["risk_level"] == "high"
    assert kwargs["rule"] == "labour_dispute"


@pytest.mark.asyncio
async def test_escalate_coerces_unknown_risk_to_high():
    from services.platform.escalation import escalate

    with patch("services.platform.escalation._open_ticket", return_value=None), \
         patch("services.platform.escalation._notify_hr", new=AsyncMock(return_value=True)), \
         patch("services.platform.escalation._fire_webhook"), \
         patch("services.platform.escalation._persist_alert"):
        rec = await escalate(
            user_id="u",
            reason="r",
            risk_level="weird",
            metadata={"rule": "labour_dispute"},
            supabase=_FakeSupabase(),
        )
    assert rec.risk_level == "high"


@pytest.mark.asyncio
async def test_escalate_from_text_drives_full_pipeline():
    from services.platform import escalation as esc

    sb = _FakeSupabase()
    with patch("services.platform.escalation._open_ticket", return_value="tick-x"), \
         patch("services.platform.escalation._notify_hr", new=AsyncMock(return_value=True)), \
         patch("services.platform.escalation._fire_webhook"):
        recs = await esc.escalate_from_text(
            "我要自杀",
            user_id="u1",
            organisation_id="org1",
            supabase=sb,
        )
    assert len(recs) == 1
    assert recs[0].risk_level == "critical"


@pytest.mark.asyncio
async def test_escalate_from_text_clean_returns_empty():
    from services.platform import escalation as esc

    recs = await esc.escalate_from_text("聊聊面试", user_id="u1", supabase=_FakeSupabase())
    assert recs == []


def test_list_risk_alerts_returns_redacted_rows():
    from services.platform.escalation import list_risk_alerts

    sb = _FakeSupabase()
    # seed two rows directly into the fake table
    sb.tables["risk_alerts"] = _FakeTable("risk_alerts", sb)
    sb.tables["risk_alerts"]._rows = [
        {"id": "1", "user_id": "u1", "rule": "self_harm", "risk_level": "critical",
         "reason": "r1", "matched_keywords": ["自杀"], "message": "m1",
         "ticket_id": "t1", "notified": True, "created_at": "2026-01-01"},
        {"id": "2", "user_id": "u2", "rule": "labour_dispute", "risk_level": "high",
         "reason": "r2", "matched_keywords": ["仲裁"], "message": "m2",
         "ticket_id": None, "notified": False, "created_at": "2026-01-02"},
    ]
    rows = list_risk_alerts(sb, risk_level="critical")
    assert len(rows) == 1
    assert rows[0]["risk_level"] == "critical"
    # No raw conversation column exists in the projection
    assert "raw_text" not in rows[0]
    assert "conversation" not in rows[0]


# ===========================================================================
# api.admin_risk_alerts — redacted GET + preview POST /check
# ===========================================================================
@pytest.mark.asyncio
async def test_admin_risk_alerts_check_detects_self_harm():
    from api.admin_risk_alerts import CheckRequest, check_escalation

    out = await check_escalation(CheckRequest(text="我不想活了想自杀"))
    assert out["must_escalate"] is True
    assert out["hits"][0]["rule"] == "self_harm"
    assert out["hits"][0]["risk_level"] == "critical"
    # preview never echoes the verbatim text
    assert "raw_text" not in out


@pytest.mark.asyncio
async def test_admin_risk_alerts_check_clean():
    from api.admin_risk_alerts import CheckRequest, check_escalation

    out = await check_escalation(CheckRequest(text="今天面试几点"))
    assert out["must_escalate"] is False
    assert out["hits"] == []


@pytest.mark.asyncio
async def test_admin_risk_alerts_list_endpoint():
    from api.admin_risk_alerts import get_risk_alerts

    sb = _FakeSupabase()
    sb.tables["risk_alerts"] = _FakeTable("risk_alerts", sb)
    sb.tables["risk_alerts"]._rows = [
        {"id": "1", "user_id": "u1", "organisation_id": "org1", "rule": "self_harm",
         "risk_level": "critical", "reason": "r", "matched_keywords": [],
         "message": "m", "ticket_id": None, "notified": True, "created_at": "x"},
    ]
    with patch("api.admin_risk_alerts.get_supabase_admin", return_value=sb):
        rows = await get_risk_alerts(risk_level="critical")
    assert len(rows) == 1
    # In unit-test the function returns raw dicts (FastAPI response_model
    # coercion only happens over HTTP). Validate the redacted shape:
    assert rows[0]["risk_level"] == "critical"
    assert "raw_text" not in rows[0]


# ===========================================================================
# Privacy invariant — EscalationRecord never carries verbatim text
# ===========================================================================
def test_escalation_record_has_no_raw_text_field():
    from services.platform.escalation import EscalationRecord

    rec = EscalationRecord(
        id="x", user_id="u", organisation_id=None, rule="self_harm",
        risk_level="critical", reason="r", matched_keywords=["自杀"],
        message="m", ticket_id=None, notified=False, created_at="",
    )
    d = rec.to_dict()
    assert "raw_text" not in d
    assert "text" not in d
    assert "conversation" not in d
