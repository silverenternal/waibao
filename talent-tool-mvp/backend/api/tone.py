"""T3701 - 语气学习 API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.tone_learner import (
    aggregate_history,
    classify_tone,
    extract_few_shot_samples,
    render_tone_for_prompt,
    rewrite_template,
    ALL_TONES,
    ToneProfile,
)

logger = logging.getLogger("recruittech.api.tone")

router = APIRouter(prefix="/api/tone", tags=["tone"])


class HistoryIn(BaseModel):
    user_id: str
    history: List[str] = Field(default_factory=list)
    manual_override: Optional[str] = None


class ClassifyIn(BaseModel):
    text: str


class RewriteIn(BaseModel):
    template: str
    user_id: Optional[str] = None
    history: List[str] = Field(default_factory=list)
    manual_override: Optional[str] = None


@router.post("/aggregate")
async def aggregate(req: HistoryIn) -> Dict[str, Any]:
    if not req.history:
        raise HTTPException(400, "history is empty")
    prof = aggregate_history(req.history)
    prof.user_id = req.user_id
    if req.manual_override and req.manual_override in ALL_TONES:
        prof.manual_override = req.manual_override
    return {
        "user_id": prof.user_id,
        "primary_tone": prof.primary_tone,
        "tone_scores": prof.tone_scores,
        "sample_count": prof.sample_count,
        "render_for_prompt": render_tone_for_prompt(prof),
        "manual_override": prof.manual_override,
    }


@router.post("/classify")
async def classify(req: ClassifyIn) -> Dict[str, Any]:
    if not req.text:
        raise HTTPException(400, "text empty")
    return {"text": req.text, "scores": classify_tone(req.text)}


@router.post("/few-shot")
async def few_shot(req: HistoryIn) -> Dict[str, Any]:
    if not req.history:
        return {"samples": []}
    prof = aggregate_history(req.history)
    primary = req.manual_override or prof.primary_tone
    samples = extract_few_shot_samples(req.history, primary)
    return {"primary": primary, "samples": samples}


@router.post("/rewrite")
async def rewrite(req: RewriteIn) -> Dict[str, Any]:
    if not req.template:
        raise HTTPException(400, "template empty")
    if req.history:
        prof = aggregate_history(req.history)
        prof.user_id = req.user_id or "anon"
        if req.manual_override and req.manual_override in ALL_TONES:
            prof.manual_override = req.manual_override
        out = rewrite_template(req.template, prof)
    else:
        out = rewrite_template(req.template, ToneProfile(user_id=req.user_id or "anon"))
    return {"result": out}


@router.get("/tones")
async def tones() -> Dict[str, Any]:
    return {"tones": ALL_TONES}
