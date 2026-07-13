"""T3707 - 沉默激活 + 通知调度."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("recruittech.services.silence_activator")

SILENCE_HOURS_DEFAULT = 24
NUDGE_HOURS_DEFAULT = 48
MORNING_HOUR = 9
AFTERNOON_HOUR = 17


@dataclass
class RoomState:
    room_id: str
    last_message_at: Optional[datetime] = None
    last_actor: Optional[str] = None
    participants: List[str] = field(default_factory=list)
    admin_id: Optional[str] = None

    def hours_silent(self, now: datetime) -> Optional[float]:
        if not self.last_message_at:
            return None
        return (now - self.last_message_at).total_seconds() / 3600.0


@dataclass
class Nudge:
    room_id: str
    reason: str
    severity: str  # info / warn / urgent
    suggested_message: str
    target_user: str


def detect_silence(
    rooms: Iterable[RoomState],
    now: Optional[datetime] = None,
    silence_hours: float = SILENCE_HOURS_DEFAULT,
) -> List[Nudge]:
    now = now or datetime.utcnow()
    nudges: List[Nudge] = []

    for r in rooms:
        h = r.hours_silent(now)
        if h is None:
            continue
        if h >= silence_hours:
            severity = "urgent" if h >= silence_hours * 2 else "warn"
            suggested = (
                f"@管理员 协作室 {r.room_id} 已沉默 {h:.1f} 小时,"
                f"请推进 / 关闭话题。")
            nudges.append(Nudge(
                room_id=r.room_id,
                reason=f"silence>={silence_hours}h (实际 {h:.1f}h)",
                severity=severity,
                suggested_message=suggested,
                target_user=r.admin_id or (r.participants[0] if r.participants else "admin"),
            ))
    return nudges


# --------- 通知调度 ---------

@dataclass
class ScheduleSlot:
    hour: int  # local hour
    audience: str  # all / hr / candidates
    template: str


DEFAULT_SCHEDULE: List[ScheduleSlot] = [
    ScheduleSlot(MORNING_HOUR, "all", "good_morning"),
    ScheduleSlot(AFTERNOON_HOUR, "all", "wrap_up_summary"),
    ScheduleSlot(MORNING_HOUR, "hr", "daily_hr_briefing"),
]


def plan_schedule(today: Optional[datetime] = None,
                  override: Optional[List[ScheduleSlot]] = None) -> List[Dict[str, Any]]:
    today = today or datetime.utcnow()
    slots = override if override is not None else DEFAULT_SCHEDULE
    out = []
    for s in slots:
        scheduled = today.replace(hour=s.hour, minute=0, second=0, microsecond=0)
        out.append({
            "scheduled_at": scheduled.isoformat(),
            "hour": s.hour,
            "audience": s.audience,
            "template": s.template,
        })
    return out


# --------- 沉默激活 (AI 主动 push) ---------

@dataclass
class ActivationAction:
    room_id: str
    action_type: str  # nudge_admin / split_topic / auto_summary / close
    detail: str
    payload: Dict[str, Any] = field(default_factory=dict)


def plan_activation(
    room: RoomState,
    nudges: List[Nudge],
    now: Optional[datetime] = None,
) -> List[ActivationAction]:
    now = now or datetime.utcnow()
    if not nudges:
        return [ActivationAction(
            room_id=room.room_id,
            action_type="auto_summary",
            detail="无新消息时,自动推送摘要给参与者,保持热度。",
        )]

    actions: List[ActivationAction] = []
    for n in nudges:
        if n.room_id != room.room_id:
            continue
        if n.severity == "urgent":
            actions.append(ActivationAction(
                room_id=room.room_id,
                action_type="nudge_admin",
                detail=n.suggested_message,
                payload={"to": n.target_user},
            ))
        else:
            actions.append(ActivationAction(
                room_id=room.room_id,
                action_type="split_topic",
                detail="将话题拆分为 2 个子任务,引导负责人分别决策。",
            ))
    return actions
