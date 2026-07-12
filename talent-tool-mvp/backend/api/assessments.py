"""Assessment API (T1306).

  POST /api/assessments/invite
  GET  /api/assessments/{invitation_id}/result
  GET  /api/assessments
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_supabase_admin
from services.assessment_service import AssessmentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assessments", tags=["assessment"])


class InviteRequest(BaseModel):
    candidate_id: str
    assessment_id: str
    candidate_email: Optional[str] = None
    candidate_name: Optional[str] = None
    expires_in_hours: int = Field(72, ge=1, le=720)
    job_id: Optional[str] = None
    metadata: dict[str, str] | None = None


def _service(supabase=Depends(get_supabase_admin)) -> AssessmentService:
    return AssessmentService(supabase=supabase)


@router.post("/invite")
async def send_invite(
    body: InviteRequest,
    service: AssessmentService = Depends(_service),
) -> dict:
    try:
        row = await service.send_invite(
            candidate_id=body.candidate_id,
            assessment_id=body.assessment_id,
            candidate_email=body.candidate_email,
            candidate_name=body.candidate_name,
            expires_in_hours=body.expires_in_hours,
            job_id=body.job_id,
            metadata=body.metadata,
        )
        return {"ok": True, "data": row}
    except Exception as exc:  # noqa: BLE001
        logger.exception("assessments.invite.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{invitation_id}/result")
async def get_result(
    invitation_id: str,
    service: AssessmentService = Depends(_service),
) -> dict:
    if not invitation_id:
        raise HTTPException(status_code=400, detail="invitation_id is required")
    try:
        result = await service.get_result(invitation_id)
        return {"ok": True, "data": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("assessments.result.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("")
async def list_invitations(
    candidate_id: str | None = Query(None),
    job_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    supabase=Depends(get_supabase_admin),
) -> dict:
    q = supabase.table("assessment_invitations").select("*")
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if job_id:
        q = q.eq("job_id", job_id)
    q = q.order("created_at", desc=True).limit(limit)
    res = q.execute()
    return {"ok": True, "data": res.data or [], "count": len(res.data or [])}


__all__ = ["router"]
