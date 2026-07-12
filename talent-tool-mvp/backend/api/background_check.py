"""BackgroundCheck API (T1307).

  POST   /api/background-checks
  GET    /api/background-checks/{id}/status
  GET    /api/background-checks
  POST   /api/background-checks/trigger-pre-offer
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_supabase_admin
from providers.background_check.types import CheckType
from services.background_check_service import BackgroundCheckService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/background-checks", tags=["background-check"])


class CheckTypeItem(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = ""
    required: bool = True


class InitiateRequest(BaseModel):
    candidate_id: str
    candidate_email: Optional[str] = None
    candidate_name: Optional[str] = None
    offer_id: Optional[str] = None
    job_id: Optional[str] = None
    check_types: list[CheckTypeItem] | None = None
    metadata: dict[str, str] | None = None


class TriggerPreOfferRequest(BaseModel):
    candidate_id: str
    candidate_email: Optional[str] = None
    candidate_name: Optional[str] = None
    offer_id: Optional[str] = None
    job_id: Optional[str] = None


def _service(supabase=Depends(get_supabase_admin)) -> BackgroundCheckService:
    return BackgroundCheckService(supabase=supabase)


@router.post("")
async def initiate(
    body: InitiateRequest,
    service: BackgroundCheckService = Depends(_service),
) -> dict:
    try:
        types = [
            CheckType(code=t.code, name=t.name, required=t.required)
            for t in (body.check_types or [])
        ]
        row = await service.initiate(
            candidate_id=body.candidate_id,
            candidate_email=body.candidate_email,
            candidate_name=body.candidate_name,
            offer_id=body.offer_id,
            job_id=body.job_id,
            check_types=types or None,
            metadata=body.metadata,
        )
        return {"ok": True, "data": row}
    except Exception as exc:  # noqa: BLE001
        logger.exception("bg_check.initiate.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/trigger-pre-offer")
async def trigger_pre_offer(
    body: TriggerPreOfferRequest,
    service: BackgroundCheckService = Depends(_service),
) -> dict:
    try:
        out = await service.trigger_pre_offer(
            candidate_id=body.candidate_id,
            candidate_email=body.candidate_email,
            candidate_name=body.candidate_name,
            offer_id=body.offer_id,
            job_id=body.job_id,
        )
        return {"ok": True, "data": out}
    except Exception as exc:  # noqa: BLE001
        logger.exception("bg_check.trigger_pre_offer.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{check_id}/status")
async def get_status(
    check_id: str,
    service: BackgroundCheckService = Depends(_service),
) -> dict:
    if not check_id:
        raise HTTPException(status_code=400, detail="check_id is required")
    try:
        return {"ok": True, "data": await service.get_status(check_id)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("bg_check.get_status.failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("")
async def list_checks(
    candidate_id: str | None = Query(None),
    offer_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    supabase=Depends(get_supabase_admin),
) -> dict:
    q = supabase.table("background_checks").select("*")
    if candidate_id:
        q = q.eq("candidate_id", candidate_id)
    if offer_id:
        q = q.eq("offer_id", offer_id)
    q = q.order("created_at", desc=True).limit(limit)
    res = q.execute()
    return {"ok": True, "data": res.data or [], "count": len(res.data or [])}


__all__ = ["router"]
