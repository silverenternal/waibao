"""Probation Service (T2404).

Manages probation period tracking:
- Auto-creates tasks: 入职当天 / D+30 / D+90 / D+180
- 3-day reminder before manager assessment
- 5-dimension evaluation template (绩效/学习/融入/态度/潜力)
- Confirmation to full-time employee

Design notes:
- All public APIs return dict (JSON-friendly)
- Pure logic; persistence handled by callers via Supabase RPC / REST
- Slug score structure: {performance, learning, integration, attitude, potential}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone, date
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("recruittech.service.probation")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 标准试用期 6 个月
DEFAULT_PROBATION_DAYS = 180
REMINDER_LEAD_DAYS = 3

# 5 个评估维度
DIMENSIONS = ["performance", "learning", "integration", "attitude", "potential"]
DIMENSION_LABELS_CN = {
    "performance": "绩效",
    "learning": "学习能力",
    "integration": "团队融入",
    "attitude": "工作态度",
    "potential": "发展潜力",
}


class ProbationStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PASSED = "passed"
    FAILED = "failed"
    EXTENDED = "extended"


class TaskType(str, Enum):
    ORIENTATION = "orientation"
    CHECKIN_30 = "checkin_30"
    REVIEW_30 = "review_30"
    REVIEW_90 = "review_90"
    REVIEW_180 = "review_180"
    REMINDER = "reminder"


# 入职当天需要创建的任务模板
ONBOARDING_TASK_TEMPLATE = [
    {
        "type": TaskType.ORIENTATION.value,
        "title": "入职引导",
        "description": "完成入职引导: 公司介绍 / 团队介绍 / 工位 / 账号",
        "offset_days": 0,
    },
    {
        "type": TaskType.CHECKIN_30.value,
        "title": "30 天关怀",
        "description": "经理与新员工 1-on-1, 了解适应情况",
        "offset_days": 30,
    },
    {
        "type": TaskType.REVIEW_30.value,
        "title": "D+30 评估",
        "description": "30 天试用期评估 (5 维度)",
        "offset_days": 30,
    },
    {
        "type": TaskType.REVIEW_90.value,
        "title": "D+90 评估",
        "description": "90 天试用期评估 (5 维度)",
        "offset_days": 90,
    },
    {
        "type": TaskType.REVIEW_180.value,
        "title": "D+180 转正评估",
        "description": "180 天转正评估, 决定是否转正",
        "offset_days": 180,
    },
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProbationTask:
    employee_id: str
    org_id: str
    type: str
    title: str
    description: str
    due_at: str  # ISO 8601
    completed_at: Optional[str] = None
    review_id: Optional[str] = None
    reminded_at: Optional[str] = None
    id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ProbationReview:
    employee_id: str
    manager_id: str
    org_id: str
    review_stage: str  # 30 / 90 / 180 / final
    review_date: str
    scores: dict[str, int]
    comments: Optional[str] = None
    status: str = ProbationStatus.PENDING.value
    confirmed_at: Optional[str] = None
    confirmation_notes: Optional[str] = None
    extension_days: int = 0
    id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def average_score(self) -> float:
        """返回 5 维度平均分."""
        if not self.scores:
            return 0.0
        valid = [v for v in self.scores.values() if isinstance(v, (int, float))]
        return sum(valid) / len(valid) if valid else 0.0

    def is_pass(self) -> bool:
        """默认通过阈值: 平均 >= 3.5 且每维度 >= 2."""
        if not self.scores:
            return False
        avg = self.average_score()
        return avg >= 3.5 and all(
            v >= 2 for v in self.scores.values() if isinstance(v, (int, float))
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ProbationService:
    """试用期跟踪 service (singleton)."""

    _instance: Optional["ProbationService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # 1. 入职: 创建自动任务
    # ------------------------------------------------------------------

    def create_onboarding_tasks(
        self,
        employee_id: str,
        org_id: str,
        hire_date: datetime,
    ) -> list[dict]:
        """入职当天调用: 生成所有自动任务.

        Args:
            employee_id: 新员工 ID
            org_id: 组织 ID
            hire_date: 入职日期

        Returns:
            list of task dicts (含 due_at / type / title / description)
        """
        tasks = []
        for tmpl in ONBOARDING_TASK_TEMPLATE:
            due = hire_date + timedelta(days=tmpl["offset_days"])
            task = ProbationTask(
                employee_id=employee_id,
                org_id=org_id,
                type=tmpl["type"],
                title=tmpl["title"],
                description=tmpl["description"],
                due_at=due.isoformat(),
            )
            tasks.append(task.to_dict())
        logger.info(
            "probation.onboarding_tasks_created employee=%s tasks=%d",
            employee_id,
            len(tasks),
        )
        return tasks

    # ------------------------------------------------------------------
    # 2. 提醒: 提前 N 天
    # ------------------------------------------------------------------

    def tasks_needing_reminder(
        self,
        open_tasks: list[dict],
        lead_days: int = REMINDER_LEAD_DAYS,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        """返回需要提醒的任务 (距截止 < lead_days 且尚未提醒)."""
        now = now or datetime.now(timezone.utc)
        result = []
        for t in open_tasks:
            if t.get("reminded_at") or t.get("completed_at"):
                continue
            due = _parse_dt(t.get("due_at"))
            if due is None:
                continue
            delta = (due - now).days
            if 0 <= delta <= lead_days:
                result.append(t)
        return result

    # ------------------------------------------------------------------
    # 3. 评估提交
    # ------------------------------------------------------------------

    def submit_review(
        self,
        employee_id: str,
        manager_id: str,
        org_id: str,
        review_stage: str,
        scores: dict[str, int],
        comments: Optional[str] = None,
        review_date: Optional[date] = None,
    ) -> dict:
        """提交评估,自动判定通过/失败."""
        review_date = review_date or datetime.now(timezone.utc).date()
        # 校验 5 维度
        missing = [d for d in DIMENSIONS if d not in scores]
        if missing:
            raise ValueError(f"missing dimensions: {missing}")
        invalid = [k for k, v in scores.items() if not (1 <= v <= 5)]
        if invalid:
            raise ValueError(f"scores out of range (1-5): {invalid}")

        review = ProbationReview(
            employee_id=employee_id,
            manager_id=manager_id,
            org_id=org_id,
            review_stage=review_stage,
            review_date=review_date.isoformat(),
            scores=scores,
            comments=comments,
            status=ProbationStatus.SUBMITTED.value,
        )
        # 自动判定
        review.status = (
            ProbationStatus.PASSED.value
            if review.is_pass()
            else ProbationStatus.FAILED.value
        )
        logger.info(
            "probation.review_submitted employee=%s stage=%s avg=%.2f status=%s",
            employee_id,
            review_stage,
            review.average_score(),
            review.status,
        )
        return review.to_dict()

    # ------------------------------------------------------------------
    # 4. 转正
    # ------------------------------------------------------------------

    def complete_probation(
        self,
        review_id: str,
        confirmation_notes: Optional[str] = None,
    ) -> dict:
        """标记转正完成."""
        return {
            "review_id": review_id,
            "status": ProbationStatus.PASSED.value,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "confirmation_notes": confirmation_notes or "",
        }

    def extend_probation(
        self,
        review_id: str,
        extension_days: int,
        reason: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> dict:
        """延长试用期."""
        if not (1 <= extension_days <= 90):
            raise ValueError("extension_days must be 1-90")
        return {
            "review_id": review_id,
            "extension_days": extension_days,
            "reason": reason or "",
            "approved_by": approved_by,
            "status": ProbationStatus.EXTENDED.value,
        }

    # ------------------------------------------------------------------
    # 5. 视图聚合
    # ------------------------------------------------------------------

    def summarize_employee(
        self,
        employee_id: str,
        reviews: list[dict],
        tasks: list[dict],
    ) -> dict:
        """员工视图: 当前进度 + 下一个截止任务 + 最近评估."""
        now = datetime.now(timezone.utc)
        # 当前状态
        latest_review = max(reviews, key=lambda r: r.get("review_date", ""), default=None)
        # 下一个待办
        next_task = None
        for t in sorted(tasks, key=lambda t: t.get("due_at", "")):
            if not t.get("completed_at"):
                next_task = t
                break
        return {
            "employee_id": employee_id,
            "latest_review": latest_review,
            "next_task": next_task,
            "task_summary": _task_summary(tasks),
            "is_confirmed": any(
                r.get("status") == ProbationStatus.PASSED.value
                and r.get("review_stage") in ("180", "final")
                for r in reviews
            ),
            "as_of": now.isoformat(),
        }

    def summarize_team(
        self,
        org_id: str,
        employees: list[dict],
    ) -> dict:
        """团队视图: 列出所有试用期员工."""
        stats = {
            "total": len(employees),
            "on_track": 0,
            "at_risk": 0,
            "pending_review": 0,
            "confirmed": 0,
        }
        items = []
        for emp in employees:
            tags = emp.get("tags", [])
            last_score = emp.get("latest_score")
            if "confirmed" in tags:
                stats["confirmed"] += 1
            elif "at_risk" in tags:
                stats["at_risk"] += 1
            elif "pending_review" in tags:
                stats["pending_review"] += 1
            else:
                stats["on_track"] += 1
            items.append(emp)
        return {
            "org_id": org_id,
            "stats": stats,
            "employees": items,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _task_summary(tasks: list[dict]) -> dict:
    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("completed_at"))
    pending = total - completed
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "completion_rate": round(completed / total, 3) if total else 0.0,
    }


def get_probation_service() -> ProbationService:
    """DI 入口."""
    return ProbationService()
