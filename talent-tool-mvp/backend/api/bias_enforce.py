"""T3704 - bias enforcement API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.bias_enforcement import (
    scan_bias, substitute, build_impact_report, BIAS_LEXICON,
)

logger = logging.getLogger("recruittech.api.bias_enforce")

router = APIRouter(prefix="/api/bias", tags=["bias"])


class ScanIn(BaseModel):
    text: str


class SubstituteIn(BaseModel):
    text: str
    replacements: Optional[Dict[str, str]] = None


class ImpactIn(BaseModel):
    historic_jds: List[Dict[str, Any]] = Field(default_factory=list)
    months: int = 3


@router.post("/scan")
async def scan(req: ScanIn) -> Dict[str, Any]:
    if not req.text:
        raise HTTPException(400, "text empty")
    rep = scan_bias(req.text)
    return {"report": rep.to_dict(), "lexicon": list(BIAS_LEXICON.keys())}


@router.post("/substitute")
async def subs(req: SubstituteIn) -> Dict[str, Any]:
    if not req.text:
        raise HTTPException(400, "text empty")
    new = substitute(req.text, req.replacements)
    return {"original": req.text, "rewritten": new}


@router.post("/impact")
async def impact(req: ImpactIn) -> Dict[str, Any]:
    return build_impact_report(req.historic_jds, req.months)


@router.get("/lexicon")
async def lex() -> Dict[str, Any]:
    return {
        "categories": [
            {"code": k, "label": v["label"], "words": v["words"],
             "replacement": v["replacement"]}
            for k, v in BIAS_LEXICON.items()
        ],
    }
