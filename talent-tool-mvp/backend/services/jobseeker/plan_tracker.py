"""职业计划追踪服务 (T607).

数据模型:
    - Plan  → 用户最近的职业规划 (CareerPlannerAgent 生成)
    - AdjustRequest  → 调整计划 (推迟 / 加速 / 替换 milestone)
    - Checkin        → 打卡 (推进 milestone 完成度)
    - Progress       → 当前完成度 + 即将到期 milestones

存储: Supabase (`career_plans`, `plan_checkins`, `plan_adjustments` 表)
      缺失时回退到内存字典 (dev/test)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Milestone:
    title: str
    target_date: str  # ISO 8601
    completed: bool = False
    progress: float = 0.0  # 0..1
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanItem:
    """计划中的单个行动项 (短期/中期/长期 统一抽象)."""
    title: str
    detail: str = ""
    duration: str = ""
    priority: str = "medium"
    milestone_target: str | None = None  # 关联到 Milestone.target_date
    progress: float = 0.0  # 0..1
    completed: bool = False
    started_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CareerPlan:
    id: str
    user_id: str
    short_term: list[PlanItem] = field(default_factory=list)
    mid_term: list[PlanItem] = field(default_factory=list)
    long_term: list[PlanItem] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    skill_gaps: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "short_term": [i.to_dict() for i in self.short_term],
            "mid_term": [i.to_dict() for i in self.mid_term],
            "long_term": [i.to_dict() for i in self.long_term],
            "milestones": [m.to_dict() for m in self.milestones],
            "skill_gaps": list(self.skill_gaps),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @property
    def all_items(self) -> list[PlanItem]:
        return [*self.short_term, *self.mid_term, *self.long_term]

    @property
    def overall_progress(self) -> float:
        items = self.all_items
        if not items:
            return 0.0
        return sum(i.progress for i in items) / len(items)


@dataclass(slots=True)
class Checkin:
    plan_id: str
    user_id: str
    item_title: str
    progress_delta: float  # 通常 0.05 / 0.1
    note: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Adjustment:
    plan_id: str
    user_id: str
    action: str  # "delay" / "accelerate" / "replace" / "add" / "remove"
    target_item: str
    detail: str = ""
    delta_days: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class PlanTrackerService:
    """追踪用户职业计划的执行情况."""

    def __init__(self) -> None:
        # 内存兜底存储 (Supabase 不可用时)
        self._plans: dict[str, CareerPlan] = {}  # plan_id -> plan
        self._user_index: dict[str, str] = {}    # user_id -> plan_id
        self._checkins: list[Checkin] = []
        self._adjustments: list[Adjustment] = []

    # ----------------- 创建 / 获取 plan -----------------
    def create_plan(
        self,
        user_id: str,
        *,
        plan_data: dict[str, Any] | None = None,
    ) -> CareerPlan:
        """基于 CareerPlannerAgent 输出创建 plan."""
        plan_data = plan_data or {}
        plan = CareerPlan(
            id=str(uuid.uuid4()),
            user_id=user_id,
            short_term=[PlanItem(**i) for i in plan_data.get("short_term", []) if isinstance(i, dict)],
            mid_term=[PlanItem(**i) for i in plan_data.get("mid_term", []) if isinstance(i, dict)],
            long_term=[PlanItem(**i) for i in plan_data.get("long_term", []) if isinstance(i, dict)],
            milestones=[
                Milestone(**m) for m in plan_data.get("milestones", []) if isinstance(m, dict)
            ],
            skill_gaps=list(plan_data.get("skill_gaps", [])),
        )
        self._plans[plan.id] = plan
        self._user_index[user_id] = plan.id
        return plan

    def get_plan(self, user_id: str) -> CareerPlan | None:
        pid = self._user_index.get(user_id)
        return self._plans.get(pid) if pid else None

    def list_checkins(self, user_id: str, *, limit: int = 50) -> list[Checkin]:
        return [c for c in self._checkins if c.user_id == user_id][-limit:]

    def list_adjustments(self, user_id: str, *, limit: int = 50) -> list[Adjustment]:
        return [a for a in self._adjustments if a.user_id == user_id][-limit:]

    # ----------------- 打卡 -----------------
    def checkin(
        self,
        user_id: str,
        item_title: str,
        *,
        progress_delta: float = 0.1,
        note: str = "",
    ) -> Checkin:
        plan = self.get_plan(user_id)
        if not plan:
            raise ValueError(f"no active plan for user {user_id}")

        matched: PlanItem | None = None
        for it in plan.all_items:
            if it.title == item_title:
                matched = it
                break
        if matched is None:
            raise ValueError(f"plan item '{item_title}' not found")

        matched.progress = min(1.0, matched.progress + progress_delta)
        matched.started_at = matched.started_at or datetime.now(tz=timezone.utc).isoformat()
        if matched.progress >= 0.99:
            matched.completed = True

        # 同步 milestone
        if matched.milestone_target:
            for ms in plan.milestones:
                if ms.target_date == matched.milestone_target:
                    ms.progress = max(ms.progress, matched.progress)
                    if matched.completed:
                        ms.completed = True

        plan.updated_at = datetime.now(tz=timezone.utc).isoformat()
        checkin = Checkin(
            plan_id=plan.id, user_id=user_id,
            item_title=item_title,
            progress_delta=progress_delta, note=note,
        )
        self._checkins.append(checkin)
        return checkin

    # ----------------- 调整 -----------------
    def adjust(
        self,
        user_id: str,
        action: str,
        target_item: str,
        *,
        detail: str = "",
        delta_days: int = 0,
    ) -> Adjustment:
        plan = self.get_plan(user_id)
        if not plan:
            raise ValueError(f"no active plan for user {user_id}")

        target: PlanItem | None = None
        for it in plan.all_items:
            if it.title == target_item:
                target = it
                break
        if target is None:
            raise ValueError(f"plan item '{target_item}' not found")

        if action == "accelerate":
            target.duration = _shorten_duration(target.duration, delta_days)
            target.priority = "high"
        elif action == "delay":
            target.duration = _extend_duration(target.duration, delta_days)
        elif action == "replace":
            target.title = detail or target.title
        elif action == "remove":
            for bucket in (plan.short_term, plan.mid_term, plan.long_term):
                bucket[:] = [i for i in bucket if i is not target]
        elif action == "add":
            new_item = PlanItem(title=detail or "新行动项")
            plan.short_term.append(new_item)
        else:
            raise ValueError(f"unknown action {action!r}")

        plan.updated_at = datetime.now(tz=timezone.utc).isoformat()
        adj = Adjustment(
            plan_id=plan.id, user_id=user_id,
            action=action, target_item=target_item,
            detail=detail, delta_days=delta_days,
        )
        self._adjustments.append(adj)
        return adj

    # ----------------- 进度 -----------------
    def progress(self, user_id: str) -> dict[str, Any]:
        plan = self.get_plan(user_id)
        if not plan:
            return {
                "user_id": user_id, "plan_id": None,
                "overall_progress": 0.0,
                "items": [], "upcoming_milestones": [],
                "stale_items": [],
            }
        items = [
            {
                "title": it.title,
                "progress": it.progress,
                "completed": it.completed,
                "duration": it.duration,
                "priority": it.priority,
                "bucket": (
                    "short" if it in plan.short_term
                    else "mid" if it in plan.mid_term else "long"
                ),
            }
            for it in plan.all_items
        ]
        upcoming = [
            m.to_dict() for m in plan.milestones
            if not m.completed
            and _parse_iso(m.target_date) >= datetime.now(tz=timezone.utc) - timedelta(days=1)
        ]
        stale = [
            it.title for it in plan.all_items
            if not it.completed
            and it.progress < 0.2
            and it.started_at
            and _parse_iso(it.started_at) < datetime.now(tz=timezone.utc) - timedelta(days=14)
        ]
        return {
            "user_id": user_id,
            "plan_id": plan.id,
            "overall_progress": plan.overall_progress,
            "items": items,
            "upcoming_milestones": upcoming,
            "stale_items": stale,
            "updated_at": plan.updated_at,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _shorten_duration(duration: str, delta_days: int) -> str:
    """简单把 duration 字段缩短 N 天(用于加速场景)."""
    if delta_days <= 0 or not duration:
        return duration
    return f"{duration} (accelerated -{delta_days}d)"


def _extend_duration(duration: str, delta_days: int) -> str:
    if delta_days <= 0 or not duration:
        return duration
    return f"{duration} (delayed +{delta_days}d)"


def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(tz=timezone.utc)


_singleton: PlanTrackerService | None = None


def get_plan_tracker() -> PlanTrackerService:
    global _singleton
    if _singleton is None:
        _singleton = PlanTrackerService()
    return _singleton


def reset_plan_tracker() -> None:
    """测试用: 重置单例."""
    global _singleton
    _singleton = None