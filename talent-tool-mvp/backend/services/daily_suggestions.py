"""T3709 - 主动 HR 每日建议生成."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.daily_suggestions")

ACTION_OFFER = "send_offer"
ACTION_INTERVIEW = "schedule_interview"
ACTION_TICKET = "process_ticket"
ACTION_CARE = "candidate_care"
ACTION_FOLLOW_UP = "follow_up"
ACTION_REVIEW = "jd_review"


@dataclass
class DailySuggestion:
    category: str
    title: str
    reason: str
    priority: int  # 1 (highest) - 5
    action_type: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def generate_suggestions(
    pending_offers: List[Dict[str, Any]] = None,
    pending_interviews: List[Dict[str, Any]] = None,
    open_tickets: List[Dict[str, Any]] = None,
    waiting_candidates: List[Dict[str, Any]] = None,
    stale_jds: List[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> List[DailySuggestion]:
    pending_offers = pending_offers or []
    pending_interviews = pending_interviews or []
    open_tickets = open_tickets or []
    waiting_candidates = waiting_candidates or []
    stale_jds = stale_jds or []

    now = now or datetime.utcnow()
    sugs: List[DailySuggestion] = []

    # offer
    for o in pending_offers[:3]:
        days = o.get("days_waiting", 0) or 0
        pri = 1 if days >= 3 else 2
        sugs.append(DailySuggestion(
            category="offer",
            title=f"该发 offer:{o.get('candidate_name', '')}",
            reason=f"已等 {days} 天,再不发送候选人可能流失",
            priority=pri,
            action_type=ACTION_OFFER,
            payload={"candidate_id": o.get("candidate_id"),
                     "role": o.get("role")},
        ))

    # 面试
    for iv in pending_interviews[:3]:
        scheduled = iv.get("scheduled_at")
        priority = 1 if (scheduled and scheduled < (now + timedelta(hours=24)).isoformat()) else 2
        sugs.append(DailySuggestion(
            category="interview",
            title=f"该面试:{iv.get('candidate_name', '')}",
            reason=f"计划 {scheduled},建议提醒面试官",
            priority=priority,
            action_type=ACTION_INTERVIEW,
            payload={"candidate_id": iv.get("candidate_id"),
                     "scheduled_at": scheduled},
        ))

    # 工单
    for t in open_tickets[:3]:
        age = t.get("age_hours", 0)
        pri = 1 if age >= 48 else 3
        sugs.append(DailySuggestion(
            category="ticket",
            title=f"处理工单 #{t.get('id', '')}",
            reason=f"工单积压 {age} 小时,SLA 风险",
            priority=pri,
            action_type=ACTION_TICKET,
            payload={"ticket_id": t.get("id")},
        ))

    # 候选人关怀
    for c in waiting_candidates[:3]:
        sugs.append(DailySuggestion(
            category="care",
            title=f"关怀候选人:{c.get('name', '')}",
            reason=f"候选人已等待 {c.get('days_waiting', 0)} 天,无回应",
            priority=4,
            action_type=ACTION_CARE,
            payload={"candidate_id": c.get("id")},
        ))

    # JD 复审
    for j in stale_jds[:2]:
        sugs.append(DailySuggestion(
            category="jd",
            title=f"复审 JD:{j.get('title', '')}",
            reason=f"JD 已 {j.get('age_days', 0)} 天未优化",
            priority=5,
            action_type=ACTION_REVIEW,
            payload={"role_id": j.get("id")},
        ))

    sugs.sort(key=lambda s: (s.priority, s.category))
    return sugs


def priority_summary(sugs: List[DailySuggestion]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for s in sugs:
        summary[s.priority] = summary.get(s.priority, 0) + 1
    return summary
