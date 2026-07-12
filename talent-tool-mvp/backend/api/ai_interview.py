"""AI Interview API — T1301.

Endpoints:
    POST /api/ai-interview/start                 创建一场面试(候选人指定 role)
    GET  /api/ai-interview/{id}/questions        获取题目
    POST /api/ai-interview/{id}/upload-url       申请上传视频的签名 URL
    POST /api/ai-interview/{id}/answer           提交答案 (multipart: video file + transcript)
    POST /api/ai-interview/{id}/answer-text      提交答案 (text only,跳过 STT)
    POST /api/ai-interview/{id}/finish           完成 → 生成报告
    GET  /api/ai-interview/{id}/report           拉取报告

所有写操作都尝试落 Supabase;失败则仅走内存,保证 mocked/local 模式也能跑通。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.ai_interviewer import AIInterviewer, ai_interviewer
from services.question_bank import Question, question_bank
from services.video_processing import (
    create_upload_ticket,
    parse_video_meta,
    upload_to_storage,
)

logger = logging.getLogger("recruittech.api.ai_interview")
router = APIRouter()

# ---------------------------------------------------------------------------
# 内存仓储(供 mock / 离线场景;Supabase 在线时双写)
# ---------------------------------------------------------------------------
_INTERVIEWS: dict[str, dict[str, Any]] = {}
_QUESTIONS: dict[str, list[dict[str, Any]]] = {}
_ANSWERS: dict[str, dict[str, dict[str, Any]]] = {}  # interview_id -> {q_id: {}}
_REPORTS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class StartInterviewBody(BaseModel):
    role: str = Field(..., description="岗位 category,e.g. backend_engineer")
    role_label: Optional[str] = None
    difficulty: Optional[str] = "mid"  # junior/mid/senior/lead
    total_questions: int = Field(10, ge=1, le=20)
    language: str = "auto"


class AnswerTextBody(BaseModel):
    seq: int = Field(..., description="第几题,1 开始")
    transcript: str
    video_url: Optional[str] = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_interview(interview: dict[str, Any]) -> None:
    try:
        sb = get_supabase_admin()
        sb.table("ai_interviews").upsert(interview).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"persist_interview supabase failed: {e}")


def _persist_questions(interview_id: str, items: list[dict[str, Any]]) -> None:
    try:
        sb = get_supabase_admin()
        sb.table("ai_interview_questions").delete().eq("interview_id", interview_id).execute()
        for q in items:
            row = {**q, "interview_id": interview_id}
            sb.table("ai_interview_questions").upsert(row, on_conflict="interview_id,seq").execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"persist_questions failed: {e}")


def _persist_answer(interview_id: str, qid: str, ans: dict[str, Any]) -> None:
    try:
        sb = get_supabase_admin()
        row = {**ans, "interview_id": interview_id, "question_id": qid}
        sb.table("ai_interview_answers").upsert(row, on_conflict="interview_id,question_id").execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"persist_answer failed: {e}")


def _persist_report(interview_id: str, rep: dict[str, Any]) -> None:
    try:
        sb = get_supabase_admin()
        sb.table("ai_interview_reports").upsert(rep).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"persist_report failed: {e}")


def _question_to_row(q: Question, seq: int) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "seq": seq,
        "category": q.category,
        "title": q.title,
        "prompt": q.prompt,
        "expected_points": q.expected_points,
        "skills": q.skills,
        "difficulty": q.difficulty,
        "qtype": q.type,
        "duration_sec": q.duration_sec,
        "weights": q.weights,
        "source": "static" if not q.id.startswith("q_gen_") else "llm",
    }


def _interview_started_view(interview: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": interview["id"],
        "role": interview["role"],
        "role_label": interview.get("role_label") or interview["role"],
        "difficulty": interview.get("difficulty", "mid"),
        "total_questions": interview.get("total_questions", 10),
        "status": interview.get("status", "created"),
        "language": interview.get("language", "auto"),
        "started_at": interview.get("started_at"),
        "questions": _QUESTIONS.get(interview["id"], []),
    }


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------
@router.post("/start", summary="创建 AI 面试会话")
async def start_interview(
    body: StartInterviewBody,
    user: CurrentUser = Depends(get_current_user),
):
    """根据 role 选择题目列表(10 道)+ 写到内存 + 尝试落 Supabase。"""
    qs = await ai_interviewer.generate_questions(
        body.role,
        count=body.total_questions,
        difficulty=body.difficulty,
    )
    interview_id = str(uuid.uuid4())
    q_rows = [_question_to_row(q, idx + 1) for idx, q in enumerate(qs)]
    interview = {
        "id": interview_id,
        "user_id": str(user.id),
        "role": body.role,
        "role_label": body.role_label or body.role,
        "difficulty": body.difficulty or "mid",
        "total_questions": len(q_rows),
        "status": "in_progress",
        "language": body.language or "auto",
        "started_at": _now(),
        "extra": json.dumps({"llm_provider": "auto"}, ensure_ascii=False),
    }
    _INTERVIEWS[interview_id] = interview
    _QUESTIONS[interview_id] = q_rows
    _ANSWERS[interview_id] = {}
    _persist_interview(interview)
    _persist_questions(interview_id, q_rows)
    return _interview_started_view(interview)


# ---------------------------------------------------------------------------
# GET /questions
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/questions", summary="获取面试题目")
async def get_questions(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    interview = _INTERVIEWS.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")
    return {"interview_id": interview_id, "questions": _QUESTIONS.get(interview_id, [])}


# ---------------------------------------------------------------------------
# POST /upload-url
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/upload-url", summary="申请视频上传 URL")
async def upload_url(
    interview_id: str,
    mime: str = "video/webm",
    user: CurrentUser = Depends(get_current_user),
):
    if interview_id not in _INTERVIEWS:
        raise HTTPException(status_code=404, detail="interview not found")
    try:
        sb = get_supabase_admin()
    except Exception:
        sb = None
    ticket = create_upload_ticket(
        user_id=str(user.id),
        interview_id=interview_id,
        mime=mime,
        supabase_admin=sb,
    )
    return {
        "object_key": ticket.object_key,
        "upload_url": ticket.upload_url,
        "public_url": ticket.public_url,
        "method": ticket.method,
        "headers": ticket.headers or {},
        "expires_in_sec": ticket.expires_in_sec,
    }


# ---------------------------------------------------------------------------
# POST /answer (multipart: video file)
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/answer", summary="提交答案(视频上传)")
async def submit_answer_multipart(
    interview_id: str,
    seq: int = Form(...),
    video: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    interview = _INTERVIEWS.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")
    qs = _QUESTIONS.get(interview_id, [])
    q = next((q for q in qs if q["seq"] == seq), None)
    if not q:
        raise HTTPException(status_code=400, detail=f"question seq={seq} not found")

    mime = video.content_type or "video/webm"
    blob = await video.read()
    # 上传
    try:
        sb = get_supabase_admin()
    except Exception:
        sb = None
    object_key = f"interviews/{user.id}/{interview_id}/{q['id']}.webm"
    video_url = upload_to_storage(blob, object_key, mime=mime, supabase_admin=sb)
    return await _evaluate_and_store(
        user=user,
        interview_id=interview_id,
        question_row=q,
        video_url=video_url,
        audio_bytes=blob,
        audio_mime=mime,
        transcript=None,
        language=interview.get("language", "auto"),
    )


# ---------------------------------------------------------------------------
# POST /answer-text (transcript)
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/answer-text", summary="提交答案(纯文本)")
async def submit_answer_text(
    interview_id: str,
    body: AnswerTextBody,
    user: CurrentUser = Depends(get_current_user),
):
    interview = _INTERVIEWS.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")
    qs = _QUESTIONS.get(interview_id, [])
    q = next((q for q in qs if q["seq"] == body.seq), None)
    if not q:
        raise HTTPException(status_code=400, detail=f"question seq={body.seq} not found")
    return await _evaluate_and_store(
        user=user,
        interview_id=interview_id,
        question_row=q,
        video_url=body.video_url,
        audio_bytes=None,
        audio_mime="text/plain",
        transcript=body.transcript,
        language=interview.get("language", "auto"),
    )


async def _evaluate_and_store(
    *,
    user: CurrentUser,
    interview_id: str,
    question_row: dict[str, Any],
    video_url: str | None,
    audio_bytes: bytes | None,
    audio_mime: str,
    transcript: str | None,
    language: str,
):
    """统一评估 + 储存。"""
    # 构造 Question dataclass
    q_obj = Question(
        id=question_row["id"],
        category=question_row["category"],
        title=question_row["title"],
        prompt=question_row["prompt"],
        expected_points=question_row.get("expected_points", []),
        skills=question_row.get("skills", []),
        difficulty=question_row.get("difficulty", "mid"),
        duration_sec=question_row.get("duration_sec", 120),
        type=question_row.get("qtype", "behavioral"),
        weights=question_row.get("weights", {}),
    )
    interviewer: AIInterviewer = ai_interviewer
    score = await interviewer.evaluate_answer(
        q_obj,
        video_url=video_url,
        audio_bytes=audio_bytes,
        audio_mime=audio_mime,
        transcript=transcript,
        language=language,
    )
    # 视频元信息(在不依赖 ffprobe 的前提下粗略计算)
    meta = parse_video_meta(audio_bytes or b"", mime=audio_mime, suggested_url=video_url)

    ans_row = {
        "id": str(uuid.uuid4()),
        "interview_id": interview_id,
        "question_id": question_row["id"],
        "seq": question_row["seq"],
        "video_url": video_url,
        "audio_object_key": (video_url.split("/")[-1] if video_url else ""),
        "transcript": score.transcript,
        "transcript_provider": score.transcript_provider,
        "duration_sec": meta.duration_sec,
        "overall": score.overall,
        "band": score.band,
        "dimensions": score.dimensions,
        "strengths": score.strengths,
        "improvements": score.improvements,
        "feedback": score.feedback,
        "vision_notes": score.vision_notes,
    }
    _ANSWERS.setdefault(interview_id, {})[question_row["id"]] = ans_row
    _persist_answer(interview_id, question_row["id"], ans_row)
    # 输出时不暴露 raw byte
    return {
        "question_id": question_row["id"],
        "seq": question_row["seq"],
        "overall": score.overall,
        "band": score.band,
        "dimensions": score.dimensions,
        "strengths": score.strengths,
        "improvements": score.improvements,
        "feedback": score.feedback,
        "transcript_provider": score.transcript_provider,
        "video_url": video_url,
        "vision_notes": score.vision_notes,
    }


# ---------------------------------------------------------------------------
# POST /finish
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/finish", summary="结束面试,生成报告")
async def finish_interview(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    interview = _INTERVIEWS.get(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")
    qs = _QUESTIONS.get(interview_id, [])
    answers = _ANSWERS.get(interview_id, {})

    from services.ai_interviewer import AnswerScore

    score_objs: list[AnswerScore] = []
    answered_count = 0
    for q in qs:
        ans = answers.get(q["id"]) or {}
        # 仅当有 transcript 或 video_url 才视为已作答
        is_answered = bool((ans.get("transcript") or "").strip() or (ans.get("video_url") or "").strip())
        if not is_answered:
            continue
        answered_count += 1
        dims = ans.get("dimensions") or {}
        score_objs.append(
            AnswerScore(
                question_id=q["id"],
                overall=float(ans.get("overall") or 0.0),
                dimensions={k: float(v) for k, v in dims.items()} if isinstance(dims, dict) else {},
                band=ans.get("band") or "fair",
                transcript=ans.get("transcript") or "",
                transcript_provider=ans.get("transcript_provider") or "mock_stt",
                video_url=ans.get("video_url"),
                vision_notes=ans.get("vision_notes"),
                feedback=ans.get("feedback") or "",
                strengths=list(ans.get("strengths") or []),
                improvements=list(ans.get("improvements") or []),
            )
        )

    reporter: AIInterviewer = ai_interviewer
    report = await reporter.generate_feedback(
        score_objs,
        interview_id=interview_id,
        role=interview.get("role", ""),
    )

    rep_row = {
        "id": str(uuid.uuid4()),
        "interview_id": interview_id,
        "user_id": str(user.id),
        "role": interview.get("role", ""),
        "overall_score": report.overall_score,
        "dimension_scores": report.dimension_scores,
        "radar": report.radar,
        "summary": report.summary,
        "recommendation": report.recommendation,
        "strengths": report.strengths,
        "improvements": report.improvements,
        "total_questions": interview.get("total_questions", len(qs)),
        "answered_questions": answered_count,
        "provider": report.provider,
    }
    _REPORTS[interview_id] = rep_row
    interview["status"] = "completed"
    interview["finished_at"] = _now()
    _INTERVIEWS[interview_id] = interview
    _persist_interview(interview)
    _persist_report(interview_id, rep_row)

    return {
        "interview_id": interview_id,
        "status": interview["status"],
        "finished_at": interview["finished_at"],
        "report": _serialize_report(rep_row),
    }


# ---------------------------------------------------------------------------
# GET /report
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/report", summary="获取面试报告")
async def get_report(
    interview_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    rep = _REPORTS.get(interview_id)
    if not rep:
        raise HTTPException(status_code=404, detail="report not found; finish interview first")
    return _serialize_report(rep)


def _serialize_report(rep: dict[str, Any]) -> dict[str, Any]:
    return {
        "interview_id": rep.get("interview_id"),
        "role": rep.get("role"),
        "overall_score": rep.get("overall_score"),
        "recommendation": rep.get("recommendation"),
        "summary": rep.get("summary"),
        "radar": rep.get("radar") or {},
        "dimension_scores": rep.get("dimension_scores") or {},
        "strengths": rep.get("strengths") or [],
        "improvements": rep.get("improvements") or [],
        "total_questions": rep.get("total_questions"),
        "answered_questions": rep.get("answered_questions"),
        "provider": rep.get("provider"),
    }
