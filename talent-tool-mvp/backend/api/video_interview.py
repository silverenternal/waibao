"""VideoInterview API (T1305).

  POST   /api/video-interviews
  DELETE /api/video-interviews/{id}
  GET    /api/video-interviews/{id}/recording
  POST   /api/video-interviews/webhooks/{provider}
  GET    /api/video-interviews                 - 列表

依赖: services.video_interview_service.VideoInterviewService
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_supabase_admin
from services.video_interview_service import VideoInterviewService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video-interviews", tags=["video-interview"])


# ----------------------------------------------------------------------
# request / response
# ----------------------------------------------------------------------
class CreateVideoInterviewRequest(BaseModel):
    ticket_id: Optional[str] = None
    match_id: Optional[str] = None
    candidate_id: str
    employer_id: str
    host_email: str = Field(..., min_length=3)
    topic: str = Field(..., min_length=1, max_length=255)
    start_time: datetime
    duration_min: int = Field(30, ge=5, le=480)
    participant_emails: list[str] = Field(default_factory=list)
    preferred_provider: Optional[str] = None
    calendar_tokens: dict[str, str] | None = None

    @field_validator("preferred_provider")
    @classmethod
    def _valid_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"zoom", "tencent_meeting", "mock"}:
            raise ValueError("provider must be zoom / tencent_meeting / mock")
        return v

    @field_validator("candidate_id", "employer_id")
    @classmethod
    def _valid_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid uuid {v}") from exc
        return v


class WebhookPayload(BaseModel):
    event_type: str = Field(..., min_length=1)
    meeting_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def _service(supabase=Depends(get_supabase_admin)) -> VideoInterviewService:
    return VideoInterviewService(supabase=supabase)


# ----------------------------------------------------------------------
# endpoints
# ----------------------------------------------------------------------
@router.post("")
async def create_interview(
    body: CreateVideoInterviewRequest,
    service: VideoInterviewService = Depends(_service),
) -> dict:
    try:
        row = await service.schedule_interview(
            ticket_id=UUID(body.ticket_id) if body.ticket_id else None,
            match_id=UUID(body.match_id) if body.match_id else None,
            candidate_id=UUID(body.candidate_id),
            employer_id=UUID(body.employer_id),
            host_email=body.host_email,
            topic=body.topic,
            start_time=body.start_time,
            duration_min=body.duration_min,
            participant_emails=body.participant_emails,
            preferred_provider=body.preferred_provider,
            calendar_tokens=body.calendar_tokens,
        )
        return {"ok": True, "data": row}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("video_interview.create.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{video_interview_id}")
async def cancel_interview(
    video_interview_id: str,
    service: VideoInterviewService = Depends(_service),
) -> dict:
    try:
        UUID(video_interview_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid uuid") from exc
    try:
        out = await service.cancel_interview(UUID(video_interview_id))
        return {"ok": True, "data": out}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("video_interview.cancel.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{video_interview_id}/recording")
async def get_recording(
    video_interview_id: str,
    service: VideoInterviewService = Depends(_service),
) -> dict:
    try:
        UUID(video_interview_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid uuid") from exc
    try:
        return {
            "ok": True,
            "data": await service.get_recording(UUID(video_interview_id)),
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("video_interview.recording.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("")
async def list_interviews(
    candidate_id: str | None = Query(None),
    employer_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    service: VideoInterviewService = Depends(_service),
    supabase=Depends(get_supabase_admin),
) -> dict:
    q = supabase.table("video_interviews").select("*")
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if employer_id:
        q = q.eq("employer_id", employer_id)
    q = q.order("start_time", desc=False).limit(limit)
    res = q.execute()
    return {"ok": True, "data": res.data or [], "count": len(res.data or [])}


@router.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    body: WebhookPayload,
    service: VideoInterviewService = Depends(_service),
) -> dict:
    if provider not in {"zoom", "tencent_meeting"}:
        raise HTTPException(status_code=400, detail="unsupported provider")
    ok = await service.handle_webhook(
        provider=provider,
        event_type=body.event_type,
        meeting_id=body.meeting_id,
        payload=body.payload,
    )
    return {"ok": ok}


__all__ = ["router"]
