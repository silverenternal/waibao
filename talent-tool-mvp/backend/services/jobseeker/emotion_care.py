"""v8.1 T3604 — Emotion Care Service.

需求 1.4: 情绪关怀.

工作流程:
    1. emotion_agent 检测到高风险 (moderate/severe) -> 触发关怀 workflow
    2. 根据风险等级 (light/medium/heavy) 决定关怀深度
    3. light: 智能体温暖回应 + 1 个减压资源
       medium: + 推送减压文章 + 安排 HR 关怀窗口
       heavy: + 立即通知 HR + 推送危机干预资源 + 安排专业回访
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.jobseeker.emotion_care")


# ---------------------------------------------------------------------------
# 关怀等级
# ---------------------------------------------------------------------------
CARE_LEVEL_LIGHT = "light"
CARE_LEVEL_MEDIUM = "medium"
CARE_LEVEL_HEAVY = "heavy"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class CareAction:
    """一次关怀的具体动作."""

    action_id: str
    user_id: str
    level: str
    action_type: str  # "warm_message" | "send_resource" | "schedule_hr_callback" | "notify_hr" | "send_crisis_resource"
    payload: Dict[str, Any] = field(default_factory=dict)
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    result: str = "queued"  # queued / sent / failed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CareTicket:
    """关怀工单 — 一个用户一次风险事件 = 一个 ticket."""

    id: str
    user_id: str
    level: str
    risk_level: str  # mild / moderate / severe
    primary_emotion: str
    trigger_text: str
    actions: List[str] = field(default_factory=list)  # action_ids
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    closed_at: Optional[str] = None
    hr_notified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class EmotionCareService:
    """情绪关怀编排器."""

    def __init__(self, *, data_dir: Optional[str] = None) -> None:
        self._tickets: Dict[str, CareTicket] = {}
        self._actions: Dict[str, CareAction] = {}
        self._resources: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.RLock()
        # 加载资源
        self._load_resources(data_dir or self._default_data_dir())

    # ----------------- 资源 -----------------
    def _default_data_dir(self) -> str:
        # backend/services/jobseeker/emotion_care.py -> backend/data
        here = Path(__file__).resolve()
        return str(here.parent.parent.parent / "data")

    def _load_resources(self, data_dir: str) -> None:
        path = Path(data_dir) / "wellness_resources.json"
        if not path.exists():
            logger.warning("wellness_resources.json not found at %s", path)
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for res in data.get("resources", []):
                self._resources.setdefault(res["category"], []).append(res)
            logger.info(
                "loaded %d wellness resources across %d categories",
                sum(len(v) for v in self._resources.values()),
                len(self._resources),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("failed to load wellness_resources.json: %s", e)

    def resources_for(self, category: str, *, limit: int = 5) -> List[Dict[str, Any]]:
        return list(self._resources.get(category, []))[:limit]

    def categories(self) -> List[str]:
        return sorted(self._resources.keys())

    # ----------------- 等级判定 -----------------
    @staticmethod
    def determine_level(risk_level: str, *, intensity: float = 0.5) -> str:
        """根据 emotion_agent 输出的 risk_level + intensity 选关怀等级."""
        risk = (risk_level or "none").lower()
        if risk == "severe" or intensity >= 0.85:
            return CARE_LEVEL_HEAVY
        if risk == "moderate" or intensity >= 0.6:
            return CARE_LEVEL_MEDIUM
        if risk == "mild" or intensity >= 0.3:
            return CARE_LEVEL_LIGHT
        return CARE_LEVEL_LIGHT

    # ----------------- 触发关怀 -----------------
    def trigger_care(
        self,
        user_id: str,
        *,
        risk_level: str,
        primary_emotion: str,
        trigger_text: str,
        intensity: float = 0.5,
    ) -> CareTicket:
        """高风险时调用,生成 ticket + actions."""
        level = self.determine_level(risk_level, intensity=intensity)
        ticket = CareTicket(
            id=_uuid(),
            user_id=user_id,
            level=level,
            risk_level=risk_level,
            primary_emotion=primary_emotion,
            trigger_text=trigger_text[:500],
        )
        with self._lock:
            self._tickets[ticket.id] = ticket
        # 编排动作
        self._orchestrate(ticket)
        return ticket

    def _orchestrate(self, ticket: CareTicket) -> None:
        """根据等级编排关怀动作."""
        emotion = ticket.primary_emotion or "general_wellbeing"
        # 1. 永远先发温暖消息
        warm = self._queue_warm_message(ticket)
        # 2. 至少 1 个减压资源
        cat = self._pick_resource_category(emotion)
        res_action = self._queue_resource(ticket, cat)
        # 3. level-specific
        extra_actions: list = []
        if ticket.level in (CARE_LEVEL_MEDIUM, CARE_LEVEL_HEAVY):
            cb = self._queue_hr_callback(ticket)
            extra_actions.append(cb)
            if ticket.level == CARE_LEVEL_HEAVY:
                nhr = self._queue_hr_notification(ticket)
                cr = self._queue_crisis_resource(ticket)
                extra_actions.append(nhr)
                extra_actions.append(cr)
        # 标记 ticket.actions
        with self._lock:
            ticket.actions = [
                a.action_id for a in (warm, res_action, *extra_actions) if a
            ]
            if ticket.level == CARE_LEVEL_HEAVY:
                ticket.hr_notified = True

    # ----------------- 动作构造 -----------------
    def _queue_warm_message(self, ticket: CareTicket) -> CareAction:
        msg = {
            CARE_LEVEL_LIGHT: f"我感受到你今天有点{_emotion_label(ticket.primary_emotion)}, 想跟你聊聊吗?",
            CARE_LEVEL_MEDIUM: f"看起来你最近压力有点大,记得照顾自己。我陪着你。",
            CARE_LEVEL_HEAVY: f"如果你现在很难受,请直接拨打心理援助热线。我会立刻帮你联系 HR。",
        }.get(ticket.level, "")
        action = CareAction(
            action_id=_uuid(),
            user_id=ticket.user_id,
            level=ticket.level,
            action_type="warm_message",
            payload={"text": msg},
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def _queue_resource(self, ticket: CareTicket, category: str) -> Optional[CareAction]:
        res = self.resources_for(category, limit=1)
        if not res:
            return None
        action = CareAction(
            action_id=_uuid(),
            user_id=ticket.user_id,
            level=ticket.level,
            action_type="send_resource",
            payload={
                "category": category,
                "title": res[0]["title"],
                "url": res[0]["url"],
                "format": res[0].get("format"),
                "duration_min": res[0].get("duration_min"),
            },
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def _queue_hr_callback(self, ticket: CareTicket) -> CareAction:
        action = CareAction(
            action_id=_uuid(),
            user_id=ticket.user_id,
            level=ticket.level,
            action_type="schedule_hr_callback",
            payload={
                "preferred_window": "next_24h",
                "ticket_id": ticket.id,
            },
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def _queue_hr_notification(self, ticket: CareTicket) -> CareAction:
        action = CareAction(
            action_id=_uuid(),
            user_id=ticket.user_id,
            level=ticket.level,
            action_type="notify_hr",
            payload={
                "severity": "high",
                "ticket_id": ticket.id,
                "summary": ticket.trigger_text[:200],
                "channel": "in_app+email",
            },
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def _queue_crisis_resource(self, ticket: CareTicket) -> CareAction:
        # 取 crisis 相关 (这里用 anxiety 兜底)
        crisis = self.resources_for("anxiety", limit=1)
        action = CareAction(
            action_id=_uuid(),
            user_id=ticket.user_id,
            level=ticket.level,
            action_type="send_crisis_resource",
            payload={
                "hotline": "400-161-9995 (全国心理援助)",
                "article": crisis[0] if crisis else {},
            },
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def _pick_resource_category(self, emotion: str) -> str:
        mapping = {
            "anxiety": "anxiety",
            "stress": "anxiety",
            "burnout": "burnout",
            "sad": "rejection_recovery",
            "sadness": "rejection_recovery",
            "lonely": "loneliness",
            "loneliness": "loneliness",
            "frustrated": "rejection_recovery",
            "angry": "burnout",
            "fear": "anxiety",
            "low_motivation": "low_motivation",
            "confusion": "career_confusion",
            "impostor": "imposter_syndrome",
        }
        return mapping.get((emotion or "").lower(), "general_wellbeing")

    # ----------------- 查询 -----------------
    def list_tickets(
        self,
        user_id: Optional[str] = None,
        *,
        level: Optional[str] = None,
        limit: int = 50,
    ) -> List[CareTicket]:
        with self._lock:
            tickets = list(self._tickets.values())
            if user_id:
                tickets = [t for t in tickets if t.user_id == user_id]
            if level:
                tickets = [t for t in tickets if t.level == level]
            return tickets[-limit:]

    def list_actions(self, ticket_id: str) -> List[CareAction]:
        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return []
            return [self._actions[a] for a in ticket.actions if a in self._actions]

    def close_ticket(self, ticket_id: str) -> Optional[CareTicket]:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t:
                t.closed_at = datetime.now(timezone.utc).isoformat()
            return t

    def dashboard_summary(self) -> Dict[str, Any]:
        """HR Mothership wellness dashboard."""
        with self._lock:
            total = len(self._tickets)
            by_level: Dict[str, int] = {}
            open_count = 0
            for t in self._tickets.values():
                by_level[t.level] = by_level.get(t.level, 0) + 1
                if not t.closed_at:
                    open_count += 1
            return {
                "total_tickets": total,
                "open_tickets": open_count,
                "by_level": by_level,
                "resource_categories": len(self._resources),
                "resources_total": sum(len(v) for v in self._resources.values()),
            }

    # ----------------- 测试 -----------------
    def reset(self) -> None:
        with self._lock:
            self._tickets.clear()
            self._actions.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _uuid() -> str:
    from uuid import uuid4

    return str(uuid4())


def _emotion_label(emotion: str) -> str:
    return {
        "anxiety": "焦虑",
        "stress": "压力",
        "burnout": "疲惫",
        "sadness": "低落",
        "loneliness": "孤单",
        "anger": "烦躁",
    }.get((emotion or "").lower(), "情绪波动")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[EmotionCareService] = None
_singleton_lock = threading.Lock()


def get_emotion_care_service() -> EmotionCareService:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = EmotionCareService()
        return _singleton


def reset_emotion_care_service() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None