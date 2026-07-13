"""T3703 - strategy impact API."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.strategy_impact import analyze_strategy, fire_strategy_updated_event

logger = logging.getLogger("recruittech.api.strategy_impact")

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class StrategyIn(BaseModel):
    content: str = Field(..., min_length=1)
    version: Optional[str] = "1.0"


@router.post("/impact")
async def impact(req: StrategyIn) -> Dict[str, Any]:
    if not req.content.strip():
        raise HTTPException(400, "content empty")
    return analyze_strategy(req.content).to_dict()


@router.post("/publish")
async def publish(req: StrategyIn) -> Dict[str, Any]:
    """发布策略:触发 strategy.updated 事件 + 自动通知."""
    if not req.content.strip():
        raise HTTPException(400, "content empty")
    payload = fire_strategy_updated_event(req.content, req.version or "1.0")
    payload["published"] = True
    return payload
