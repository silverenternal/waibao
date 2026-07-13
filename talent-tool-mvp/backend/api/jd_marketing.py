"""T3705 - JD marketing API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.jd_marketing import (
    marketing_package, score_jd, generate_seo, ab_variant_title,
)

logger = logging.getLogger("recruittech.api.jd_marketing")

router = APIRouter(prefix="/api/jd-marketing", tags=["jd_marketing"])


class BuildIn(BaseModel):
    payload: Dict[str, Any]


class ScoreIn(BaseModel):
    payload: Dict[str, Any]


class SeoIn(BaseModel):
    title: str
    description: str
    location: str = ""


class ABIn(BaseModel):
    role_title: str


@router.post("/package")
async def package(req: BuildIn) -> Dict[str, Any]:
    if not isinstance(req.payload, dict) or not req.payload.get("title"):
        raise HTTPException(400, "payload.title required")
    meta = marketing_package(req.payload)
    return meta.to_dict()


@router.post("/score")
async def score(req: ScoreIn) -> Dict[str, Any]:
    sc = score_jd(req.payload)
    return sc.to_dict()


@router.post("/seo")
async def seo(req: SeoIn) -> Dict[str, Any]:
    return generate_seo(req.title, req.description, req.location).__dict__


@router.post("/ab-variants")
async def variants(req: ABIn) -> Dict[str, Any]:
    return {"variants": ab_variant_title(req.role_title)}
