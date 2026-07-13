"""T3702 - PS detection API."""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ps_detection import build_report, expiry_warning

logger = logging.getLogger("recruittech.api.ps_detection")

router = APIRouter(prefix="/api/ps", tags=["ps_detection"])


class VerifyIn(BaseModel):
    target: str = Field(..., description="证件名称")
    image_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    known_hashes: Optional[List[str]] = None
    expiry_text: Optional[str] = None
    sources: Optional[Dict[str, str]] = None


@router.post("/verify")
async def verify(req: VerifyIn) -> Dict[str, Any]:
    if not req.target:
        raise HTTPException(400, "target empty")
    img = b""
    if req.image_base64:
        try:
            img = base64.b64decode(req.image_base64)
        except Exception as e:
            raise HTTPException(400, f"image_base64 invalid: {e}")

    report = build_report(
        target=req.target,
        image_bytes=img,
        metadata=req.metadata,
        known_hashes=req.known_hashes,
        expiry_text=req.expiry_text,
        sources=req.sources,
    )
    return report.to_dict()


class ExpiryIn(BaseModel):
    expiry_text: str


@router.post("/expiry-warning")
async def exp_warn(req: ExpiryIn) -> Dict[str, Any]:
    if not req.expiry_text:
        raise HTTPException(400, "expiry_text empty")
    warning = expiry_warning(req.expiry_text)
    return {"warning": warning}
