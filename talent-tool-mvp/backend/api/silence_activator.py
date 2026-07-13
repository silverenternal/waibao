"""T3707 - silence activator API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.silence_activator import (
    detect_silence, plan_schedule, plan_activation, RoomState,
)

logger = logging.getLogger("recruittech.api.silence_activator")

router = APIRouter(prefix="/api/silence", tags=["silence"])


class RoomIn(BaseModel):
    room_id: str
    last_message_at: Optional[str] = None
    last_actor: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    admin_id: Optional[str] = None


class DetectIn(BaseModel):
    rooms: List[RoomIn] = Field(default_factory=list)
    silence_hours: float = 24.0


@router.post("/detect")
async def detect(req: DetectIn) -> Dict[str, Any]:
    states: List[RoomState] = []
    for r in req.rooms:
        last = None
        if r.last_message_at:
            try:
                last = datetime.fromisoformat(r.last_message_at)
            except Exception:
                raise HTTPException(400, f"bad timestamp on {r.room_id}")
        states.append(RoomState(
            room_id=r.room_id,
            last_message_at=last,
            last_actor=r.last_actor,
            participants=r.participants,
            admin_id=r.admin_id,
        ))
    nudges = detect_silence(states, silence_hours=req.silence_hours)
    return {
        "nudges": [
            {"room_id": n.room_id, "reason": n.reason,
             "severity": n.severity, "suggested_message": n.suggested_message,
             "target_user": n.target_user}
            for n in nudges
        ],
        "count": len(nudges),
    }


@router.get("/schedule")
async def schedule() -> Dict[str, Any]:
    return {"slots": plan_schedule()}


class PlanActivationIn(BaseModel):
    rooms: List[RoomIn] = Field(default_factory=list)
    silence_hours: float = 24.0


@router.post("/activate")
async def activate(req: PlanActivationIn) -> Dict[str, Any]:
    states = []
    for r in req.rooms:
        last = None
        if r.last_message_at:
            try:
                last = datetime.fromisoformat(r.last_message_at)
            except Exception:
                raise HTTPException(400, f"bad timestamp on {r.room_id}")
        states.append(RoomState(
            room_id=r.room_id,
            last_message_at=last,
            participants=r.participants,
            admin_id=r.admin_id,
        ))

    nudges = detect_silence(states, silence_hours=req.silence_hours)
    actions_by_room: Dict[str, List[Dict[str, Any]]] = {}
    for r in states:
        acts = plan_activation(r, nudges)
        actions_by_room[r.room_id] = [
            {"action_type": a.action_type, "detail": a.detail, "payload": a.payload}
            for a in acts
        ]
    return {"rooms": actions_by_room}
