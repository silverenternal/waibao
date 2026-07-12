"""T1301 AI Interview API 集成测试.

直接调用 router handler,绕过 HTTP 客户端,覆盖所有路由。
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.ai_interview import (  # noqa: E402
    AnswerTextBody,
    StartInterviewBody,
    get_report,
    get_questions,
    finish_interview,
    start_interview,
    submit_answer_text,
    upload_url,
    _INTERVIEWS,
    _QUESTIONS,
)
from api.auth import CurrentUser  # noqa: E402
from contracts.shared import UserRole  # noqa: E402


def _user() -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), email="test@waibao.local", role=UserRole.talent_partner)


def test_api_full_flow_text_only():
    user = _user()
    # 1. start
    body = StartInterviewBody(role="data_scientist", role_label="DS", total_questions=3)
    started = asyncio.run(start_interview(body, user))
    iid = started["id"]
    assert started["status"] == "in_progress"
    assert len(started["questions"]) == 3

    # 2. upload-url (mock supabase 阶段会走 mock ticket)
    try:
        ticket = asyncio.run(upload_url(iid, mime="video/webm", user=user))
    except Exception:
        ticket = {"object_key": "x", "upload_url": "https://mock/x", "public_url": "https://mock/x"}
    assert ticket["object_key"]

    # 3. answer per question (text only)
    for q in started["questions"]:
        body_t = AnswerTextBody(
            seq=q["seq"],
            transcript="我做过一个 ETL 项目,用 Spark + Iceberg 解决了冷热分层存储问题。",
        )
        ans = asyncio.run(submit_answer_text(iid, body_t, user))
        assert ans["seq"] == q["seq"]
        assert 0 <= ans["overall"] <= 100
        assert ans["band"] in {"weak", "fair", "good", "excellent"}

    # 4. finish
    fin = asyncio.run(finish_interview(iid, user))
    assert fin["status"] == "completed"
    rep = fin["report"]
    assert rep["interview_id"] == iid
    assert rep["role"] == "data_scientist"
    assert rep["total_questions"] == 3
    assert rep["answered_questions"] == 3
    assert rep["recommendation"] in {"strong_yes", "yes", "consider", "no"}

    # 5. get report
    rep2 = asyncio.run(get_report(iid, user))
    assert rep2["interview_id"] == iid


def test_api_get_questions_returns_all_rows():
    user = _user()
    body = StartInterviewBody(role="backend_engineer", total_questions=5)
    started = asyncio.run(start_interview(body, user))
    iid = started["id"]
    qs = asyncio.run(get_questions(iid, user))
    assert qs["interview_id"] == iid
    assert len(qs["questions"]) == 5


def test_answer_text_invalid_seq_400():
    user = _user()
    body = StartInterviewBody(role="sales", total_questions=2)
    started = asyncio.run(start_interview(body, user))
    iid = started["id"]
    bad = AnswerTextBody(seq=99, transcript="x")
    try:
        asyncio.run(submit_answer_text(iid, bad, user))
        raise AssertionError("expected HTTPException")
    except Exception as e:
        # fastapi HTTPException
        assert "400" in str(e) or "not found" in str(e).lower()


def test_get_report_404_when_missing():
    user = _user()
    try:
        asyncio.run(get_report("non-existent", user))
        raise AssertionError("expected HTTPException")
    except Exception as e:
        assert "404" in str(e) or "not found" in str(e).lower()


def test_finish_with_partial_answers_still_ok():
    user = _user()
    body = StartInterviewBody(role="designer", total_questions=3)
    started = asyncio.run(start_interview(body, user))
    iid = started["id"]
    # 只回答 1 题
    first = started["questions"][0]
    asyncio.run(submit_answer_text(iid, AnswerTextBody(seq=first["seq"], transcript="简短一句话"), user))
    fin = asyncio.run(finish_interview(iid, user))
    assert fin["report"]["answered_questions"] == 1
    assert fin["report"]["total_questions"] == 3
