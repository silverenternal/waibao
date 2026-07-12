"""AI Interview v2 API — T2202.

Endpoints
---------
- POST /api/ai-interview-v2/start              start a 5-stage interview
- GET  /api/ai-interview-v2/{id}/plan          list all questions
- GET  /api/ai-interview-v2/{id}/current       get current question
- POST /api/ai-interview-v2/{id}/answer        submit answer (text)
- POST /api/ai-interview-v2/{id}/probe         decide follow-up
- POST /api/ai-interview-v2/{id}/advance       move to next question
- POST /api/ai-interview-v2/{id}/finish        finish & generate report
- GET  /api/ai-interview-v2/{id}/transcript    full transcript
- GET  /api/ai-interview-v2/{id}/report        report
- POST /api/ai-interview-v2/realtime-session   create a Realtime session for the interview
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.jobseeker.ai_interviewer_v2 import (
    AIInterviewerV2,
    InterviewAnswer,
    InterviewQuestion,
    STAGE_LABELS,
)
from services.jobseeker.interview_personas import (
    PERSONAS,
    PERSONA_IDS,
    list_personas,
)

logger = logging.getLogger("recruittech.api.ai_interview_v2")
router = APIRouter()


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_INTERVIEWS: dict[str, dict[str, Any]] = {}        # interview_id -> meta
_PLANS: dict[str, list[dict[str, Any]]] = {}       # interview_id -> question list
_ANSWERS: dict[str, dict[str, InterviewAnswer]] = {}  # interview_id -> qid -> answer
_CURRENT: dict[str, str] = {}                       # interview_id -> current qid
_REPORTS: dict[str, dict[str, Any]] = {}            # interview_id -> report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------
class StartBody(BaseModel):
    role: str = Field(..., description="岗位 e.g. backend_engineer")
    role_label: Optional[str] = None
    difficulty: str = "mid"
    persona_id: str = "friendly_warm"
    realtime: bool = False
    realtime_voice: Optional[str] = None


class AnswerBody(BaseModel):
    question_id: str
    transcript: str
    duration_sec: float = 0.0
    use_realtime: bool = False


class AdvanceBody(BaseModel):
    to_question_id: Optional[str] = None  # explicit (e.g. follow-up)


class RealtimeSessionBody(BaseModel):
    interview_id: str
    voice: Optional[str] = None
    instructions: Optional[str] = None
    force_mock: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _interviewer_for(persona_id: str) -> AIInterviewerV2:
    return AIInterviewerV2(persona_id=persona_id)


def _plan_to_dict(q: InterviewQuestion) -> dict[str, Any]:
    return {
        "id": q.id,
        "stage": q.stage,
        "stage_label": STAGE_LABELS.get(q.stage, q.stage),
        "seq": q.seq,
        "stage_seq": q.stage_seq,
        "title": q.title,
        "prompt": q.prompt,
        "expected_points": q.expected_points,
        "skills": q.skills,
        "is_follow_up": q.is_follow_up,
        "parent_question_id": q.parent_question_id,
    }


def _answer_to_dict(a: InterviewAnswer) -> dict[str, Any]:
    return {
        "question_id": a.question_id,
        "stage": a.stage,
        "transcript": a.transcript,
        "duration_sec": a.duration_sec,
        "follow_ups": a.follow_ups,
        "depth_score": a.depth_score,
        "coverage_signals": a.coverage_signals,
        "evaluation": a.evaluation,
        "feedback": a.feedback,
        "strengths": a.strengths,
        "improvements": a.improvements,
        "ts": a.ts,
    }


def _persist_interview(row: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        sb.table("ai_interviews_v2").upsert(row).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_interview_v2 failed: %s", e)


def _persist_answer_row(interview_id: str, qid: str, ans: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        row = {"interview_id": interview_id, "question_id": qid, **ans}
        sb.table("ai_interview_answers_v2").upsert(
            row, on_conflict="interview_id,question_id"
        ).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_answer_v2 failed: %s", e)


def _persist_report(interview_id: str, report: dict[str, Any]) -> None:
    try:
        from api.deps import get_supabase_admin
        sb = get_supabase_admin()
        sb.table("ai_interview_reports_v2").upsert(report).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("persist_report_v2 failed: %s", e)


# ---------------------------------------------------------------------------
# GET /personas — list available personas
# ---------------------------------------------------------------------------
@router.get("/personas", summary="列出全部面试官人格")
async def list_all_personas():
    return {
        "items": [
            {
                "id": p.id,
                "label": p.label,
                "description": p.description,
                "voice": p.voice,
                "temperature": p.temperature,
                "tags": p.tags,
                "weights": p.weights,
            }
            for p in list_personas()
        ]
    }


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------
@router.post("/start", summary="开启一场 5 阶段 AI 面试")
async def start_interview(
    body: StartBody,
    user: CurrentUser = Depends(get_current_user),
):
    if body.persona_id not in PERSONAS:
        raise HTTPException(status_code=400, detail=f"unknown persona: {body.persona_id}")
    interview_id = f"iv_{uuid.uuid4().hex[:12]}"
    interviewer = _interviewer_for(body.persona_id)
    plan = interviewer.plan(
        role=body.role,
        difficulty=body.difficulty,
        role_label=body.role_label,
    )
    plan_rows = [_plan_to_dict(q) for q in plan]
    persona = PERSONAS[body.persona_id]
    row = {
        "id": interview_id,
        "user_id": str(user.id),
        "role": body.role,
        "role_label": body.role_label or body.role,
        "difficulty": body.difficulty,
        "persona_id": body.persona_id,
        "persona_label": persona.label,
        "status": "in_progress",
        "realtime": body.realtime,
        "started_at": _now(),
        "total_questions": len(plan_rows),
    }
    _INTERVIEWS[interview_id] = row
    _PLANS[interview_id] = plan_rows
    _ANSWERS[interview_id] = {}
    _CURRENT[interview_id] = plan_rows[0]["id"] if plan_rows else ""
    _persist_interview(row)

    # T2204: LiveKit 视频面试房间 (失败不影响主流程)
    livekit_room: dict[str, Any] | None = None
    try:
        import os
        if (os.getenv("VIDEO_PROVIDER") or "").lower() == "livekit":
            from providers.video_interview.livekit import LiveKitProvider
            from providers.video_interview.types import Participant as _P
            lk = LiveKitProvider()
            meeting = await lk.create_meeting(
                topic=f"AI Interview: {body.role}",
                start_time=datetime.now(timezone.utc),
                duration_min=max(30, body.difficulty == "senior" and 60 or 30),
                participants=[_P(email=str(user.email), name=str(user.email), role="host")],
                host_email=str(user.email),
                metadata={"interview_id": interview_id, "persona_id": body.persona_id},
            )
            livekit_room = {
                "room_name": meeting.meeting_id,
                "livekit_url": meeting.metadata.get("livekit_url"),
                "host_token": meeting.metadata.get("host_token"),
                "host_url": meeting.host_url,
                "join_url": meeting.join_url,
                "token_expires_at": meeting.metadata.get("token_expires_at"),
            }
            row["livekit_room"] = meeting.meeting_id
    except Exception as e:  # noqa: BLE001
        logger.debug(f"LiveKit room creation skipped: {e}")

    return {
        "id": interview_id,
        "persona": {"id": persona.id, "label": persona.label, "voice": persona.voice},
        "role": row["role"],
        "role_label": row["role_label"],
        "difficulty": row["difficulty"],
        "status": row["status"],
        "started_at": row["started_at"],
        "total_questions": row["total_questions"],
        "stages": [
            {"id": s, "label": STAGE_LABELS[s], "count": sum(1 for q in plan_rows if q["stage"] == s)}
            for s in ["intro", "behavioral", "technical", "reverse_q", "closing"]
        ],
        "current_question": plan_rows[0] if plan_rows else None,
        "livekit": livekit_room,
    }


# ---------------------------------------------------------------------------
# GET /{id}/plan
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/plan", summary="获取完整题目列表")
async def get_plan(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    return {
        "interview_id": interview_id,
        "questions": _PLANS.get(interview_id, []),
    }


# ---------------------------------------------------------------------------
# GET /{id}/current
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/current", summary="当前题目")
async def get_current(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    qid = _CURRENT.get(interview_id, "")
    plan = _PLANS.get(interview_id, [])
    q = next((q for q in plan if q["id"] == qid), None)
    return {
        "interview_id": interview_id,
        "current": q,
        "answered_count": len(_ANSWERS.get(interview_id, {})),
        "remaining": sum(1 for q in plan if q["id"] not in _ANSWERS.get(interview_id, {})),
    }


# ---------------------------------------------------------------------------
# POST /{id}/answer
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/answer", summary="提交答案")
async def submit_answer(
    interview_id: str,
    body: AnswerBody,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    plan = _PLANS.get(interview_id, [])
    q = next((q for q in plan if q["id"] == body.question_id), None)
    if not q:
        raise HTTPException(status_code=400, detail="question not found")
    interview = _INTERVIEWS[interview_id]
    persona_id = interview.get("persona_id", "friendly_warm")
    interviewer = _interviewer_for(persona_id)
    # Build the InterviewQuestion & answer
    q_obj = InterviewQuestion(
        id=q["id"],
        stage=q["stage"],
        seq=q["seq"],
        stage_seq=q["stage_seq"],
        title=q["title"],
        prompt=q["prompt"],
        expected_points=q.get("expected_points", []),
        skills=q.get("skills", []),
        is_follow_up=q.get("is_follow_up", False),
        parent_question_id=q.get("parent_question_id"),
    )
    answer = InterviewAnswer(
        question_id=q["id"],
        stage=q["stage"],
        transcript=body.transcript,
        duration_sec=body.duration_sec,
    )
    # Evaluate (5 dims)
    ev = await interviewer.evaluate(question=q_obj, answer=answer)
    answer.evaluation = ev
    answer.depth_score = ev.get("depth_score", 0)
    answer.coverage_signals = ev.get("coverage_signals", [])
    answer.feedback = ev.get("feedback", "")
    answer.strengths = ev.get("strengths", [])
    answer.improvements = ev.get("improvements", [])

    # Decide follow-up
    decision = interviewer.probe(question=q_obj, answer=answer)
    if decision.should_follow_up and decision.follow_up_question:
        follow_up = interviewer.build_follow_up(question=q_obj, answer=answer)
        # Insert as a sibling at the end of the same stage
        plan.append(_plan_to_dict(follow_up))
        _PLANS[interview_id] = plan
        answer.follow_ups = 1
    # Save answer
    _ANSWERS[interview_id][q["id"]] = answer
    _persist_answer_row(interview_id, q["id"], _answer_to_dict(answer))

    return {
        "interview_id": interview_id,
        "question_id": q["id"],
        "evaluation": ev,
        "probing": decision.to_dict(),
        "next_question_id": follow_up.id if decision.should_follow_up and decision.follow_up_question else None,
    }


# ---------------------------------------------------------------------------
# POST /{id}/advance
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/advance", summary="推进到下一题")
async def advance(
    interview_id: str,
    body: AdvanceBody,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    plan = _PLANS.get(interview_id, [])
    if body.to_question_id:
        if body.to_question_id not in [q["id"] for q in plan]:
            raise HTTPException(status_code=400, detail="unknown question")
        _CURRENT[interview_id] = body.to_question_id
    else:
        current = _CURRENT.get(interview_id, "")
        answered = set(_ANSWERS.get(interview_id, {}).keys())
        # Find the first unanswered question
        next_q = next((q for q in plan if q["id"] not in answered), None)
        if next_q:
            _CURRENT[interview_id] = next_q["id"]
        else:
            _CURRENT[interview_id] = ""
    qid = _CURRENT[interview_id]
    q = next((q for q in plan if q["id"] == qid), None)
    return {
        "interview_id": interview_id,
        "current": q,
        "remaining": sum(1 for q in plan if q["id"] not in _ANSWERS.get(interview_id, {})),
    }


# ---------------------------------------------------------------------------
# POST /{id}/finish
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/finish", summary="结束面试, 生成报告")
async def finish(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    interview = _INTERVIEWS[interview_id]
    persona_id = interview.get("persona_id", "friendly_warm")
    interviewer = _interviewer_for(persona_id)
    answers = list(_ANSWERS.get(interview_id, {}).values())
    if not answers:
        raise HTTPException(status_code=400, detail="no answers to evaluate")
    report = await interviewer.build_report(
        interview_id=interview_id,
        role=interview.get("role", ""),
        answers=answers,
    )
    report_dict = report.to_dict()
    _REPORTS[interview_id] = report_dict
    interview["status"] = "completed"
    interview["finished_at"] = _now()
    _INTERVIEWS[interview_id] = interview
    _persist_interview(interview)
    row = {
        "interview_id": interview_id,
        "user_id": str(user.id),
        "role": interview.get("role", ""),
        "persona_id": persona_id,
        "report": report_dict,
        "created_at": _now(),
    }
    _persist_report(interview_id, row)
    return {"interview_id": interview_id, "status": "completed", "report": report_dict}


# ---------------------------------------------------------------------------
# GET /{id}/transcript
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/transcript", summary="完整对话转写")
async def get_transcript(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    plan = _PLANS.get(interview_id, [])
    answers = _ANSWERS.get(interview_id, {})
    items = []
    for q in plan:
        a = answers.get(q["id"])
        if a:
            items.append(
                {
                    "question": _plan_to_dict_for_transcript(q),
                    "answer": _answer_to_dict(a),
                }
            )
    return {
        "interview_id": interview_id,
        "items": items,
        "count": len(items),
    }


def _plan_to_dict_for_transcript(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": q["id"],
        "stage": q["stage"],
        "stage_label": STAGE_LABELS.get(q["stage"], q["stage"]),
        "title": q["title"],
        "prompt": q["prompt"],
        "is_follow_up": q.get("is_follow_up", False),
    }


# ---------------------------------------------------------------------------
# GET /{id}/report
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/report", summary="面试报告")
async def get_report(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    rep = _REPORTS.get(interview_id)
    if not rep:
        raise HTTPException(status_code=404, detail="report not generated; finish first")
    return rep


# ---------------------------------------------------------------------------
# POST /realtime-session
# ---------------------------------------------------------------------------
@router.post("/realtime-session", summary="为这场面试创建 Realtime 语音会话")
async def create_realtime_session(
    body: RealtimeSessionBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a GPT-4o Realtime session tied to a particular interview.

    The interview must have been started with ``realtime: true`` or have
    a known persona. The returned ``session_id`` can be used to connect
    via the v2 WebSocket endpoint.
    """
    if body.interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    interview = _INTERVIEWS[body.interview_id]
    persona_id = interview.get("persona_id", "friendly_warm")
    persona = PERSONAS.get(persona_id) or PERSONAS["friendly_warm"]
    interviewer = AIInterviewerV2(persona_id=persona_id)
    instructions = body.instructions or interviewer.realtime_instructions(
        role=interview.get("role_label") or interview.get("role", "")
    )
    voice = body.voice or persona.voice
    # Forward to realtime_v2 internal handler
    from api.realtime_v2 import _SESSIONS as RT_SESSIONS, _TRANSCRIPTS
    from pydantic import BaseModel as _BM
    # Re-use the create_session logic via a fake body
    class _Body(_BM):
        conversation_id: str = ""
        model: str = "gpt-4o-realtime-preview"
        voice: str = ""
        instructions: Optional[str] = None
        modalities: list[str] = ["audio", "text"]
        input_audio_format: str = "pcm16"
        output_audio_format: str = "pcm16"
        temperature: float = persona.temperature
        tools: list = []
        metadata: dict = {"interview_id": body.interview_id, "persona_id": persona_id}
        force_mock: bool = body.force_mock

    body_obj = _Body(
        voice=voice,
        instructions=instructions,
        tools=interviewer.realtime_tools(),
    )
    # NOTE: We can't call create_session directly because it requires Depends(user).
    # Instead, replicate a subset inline.
    from services.platform.realtime_session import make_session_id
    session_id = make_session_id()
    RT_SESSIONS[session_id] = {
        "id": session_id,
        "user_id": str(user.id),
        "conversation_id": f"interview_{body.interview_id}",
        "model": "gpt-4o-realtime-preview",
        "voice": voice,
        "status": "created",
        "created_at": _now(),
        "metadata": json.dumps({"interview_id": body.interview_id, "persona_id": persona_id}, ensure_ascii=False),
    }
    return {
        "session_id": session_id,
        "interview_id": body.interview_id,
        "persona": {"id": persona.id, "label": persona.label, "voice": voice},
        "ws_path": f"/api/realtime-v2/ws/{session_id}",
        "instructions_preview": instructions[:200],
    }
