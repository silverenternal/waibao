"""Probation Scheduler (T2404).

Celery beat tasks for probation:
- daily_check_tasks: 检测今天到期的任务, 标记需提醒的
- weekly_summary: 给 HR/经理发周报
- auto_complete_check: 评估超期则提醒

Pure logic — schedule the calls from Celery beat or FastAPI background.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from services.employer.probation_service import (
    ProbationService,
    get_probation_service,
)

logger = logging.getLogger("recruittech.scheduler.probation")


def daily_check_tasks(open_tasks: list[dict]) -> dict[str, Any]:
    """Daily beat: 找出今天到期的任务, 以及需提醒 (D-3) 的任务.

    Returns:
        {"due_today": [...], "needs_reminder": [...], "checked_at": "..."}
    """
    svc = get_probation_service()
    now = datetime.now(timezone.utc)
    needs_reminder = svc.tasks_needing_reminder(open_tasks, lead_days=3, now=now)

    due_today = []
    for t in open_tasks:
        if t.get("completed_at"):
            continue
        due_str = t.get("due_at", "")
        try:
            due = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if 0 <= (due.date() - now.date()).days <= 1:
            due_today.append(t)

    logger.info(
        "probation.daily_check due_today=%d needs_reminder=%d",
        len(due_today),
        len(needs_reminder),
    )
    return {
        "due_today": due_today,
        "needs_reminder": needs_reminder,
        "checked_at": now.isoformat(),
    }


def weekly_summary(reviews: list[dict], tasks: list[dict]) -> dict[str, Any]:
    """Weekly HR summary: 待评估数 / 通过率 / 通过率."""
    pending = [r for r in reviews if r.get("status") == "pending"]
    submitted = [r for r in reviews if r.get("status") in ("submitted", "passed", "failed")]
    passed = [r for r in reviews if r.get("status") == "passed"]
    pass_rate = round(len(passed) / len(submitted), 3) if submitted else 0.0

    return {
        "pending_reviews": len(pending),
        "submitted_reviews": len(submitted),
        "passed": len(passed),
        "failed": len(submitted) - len(passed),
        "pass_rate": pass_rate,
        "open_tasks": sum(1 for t in tasks if not t.get("completed_at")),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def auto_complete_check(reviews: list[dict]) -> list[str]:
    """检测 D+180 后仍未评估的, 返回需升级的 review ids."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=180)).date().isoformat()
    stale = [
        r["id"]
        for r in reviews
        if r.get("status") == "pending"
        and r.get("review_date", "") < threshold
    ]
    if stale:
        logger.warning(
            "probation.stale_reviews count=%d escalation_needed", len(stale)
        )
    return stale
