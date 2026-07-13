"""v8.1 T3603 — Proactive Push Scheduler.

需求 1.3: 智能体主动 push.

设计:

* 每小时扫一次全量活跃用户,根据 4 个触发规则生成 push 候选
  - 3 天没互动 (re-engage)
  - 5 个新职位 (new_jobs_digest)
  - 面试前一天 (interview_reminder)
  - 长假结束 (festival_return)
* 调度本身是异步任务,实际推送委托给 ``ProactiveOutreachService``
  (T3601),保持单一推送路径,避免重复通道调用.
* 调度结果落到 ``proactive_push_log`` (append-only),便于看板上追踪.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.platform.proactive_scheduler")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class PushCandidate:
    user_id: str
    trigger: str  # re_engage_3d / new_jobs / interview_tomorrow / long_break / festival_return
    payload: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PushLog:
    id: str
    user_id: str
    trigger: str
    status: str  # dispatched / skipped_quota / skipped_quiet / failed
    reason: str = ""
    channels: List[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 触发规则
# ---------------------------------------------------------------------------
TRIGGER_RULES = {
    "re_engage_3d": {
        "min_silence_days": 3,
        "max_silence_days": 30,
        "priority": "low",
    },
    "long_break": {
        "min_silence_days": 30,
        "priority": "low",
    },
    "new_jobs": {
        "min_jobs": 5,
        "priority": "low",
    },
    "interview_tomorrow": {
        "lead_hours": 24,
        "priority": "high",
    },
    "festival_return": {
        "priority": "low",
    },
}


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------
class ProactiveSchedulerService:
    """主动 push 调度器 — 每小时跑一次."""

    def __init__(self) -> None:
        self._logs: List[PushLog] = []
        self._lock = threading.RLock()
        # 调度注册表
        self._registered_users: Dict[str, Dict[str, Any]] = {}
        self._last_run_at: str = ""

    # ----------------- 用户注册 -----------------
    def register_user(
        self,
        user_id: str,
        *,
        stage: str = "active_job_seeker",
        last_interaction_at: Optional[str] = None,
        new_jobs_count: int = 0,
        upcoming_interview_at: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> None:
        """注册 / 更新一个用户的状态,供 scheduler 扫描."""
        with self._lock:
            self._registered_users[user_id] = {
                "stage": stage,
                "last_interaction_at": last_interaction_at or datetime.now(timezone.utc).isoformat(),
                "new_jobs_count": int(new_jobs_count),
                "upcoming_interview_at": upcoming_interview_at,
                "preferences": preferences or {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    # ----------------- 触发评估 -----------------
    def evaluate_user(self, user_id: str) -> List[PushCandidate]:
        """为单个用户评估所有触发规则."""
        with self._lock:
            user = self._registered_users.get(user_id)
        if not user:
            return []

        out: List[PushCandidate] = []
        now = datetime.now(timezone.utc)

        # 1. re_engage_3d
        last_str = user.get("last_interaction_at")
        if last_str:
            try:
                last = datetime.fromisoformat(last_str)
            except ValueError:
                last = now
            silence_days = (now - last).days
            if 3 <= silence_days <= 30:
                out.append(PushCandidate(
                    user_id=user_id,
                    trigger="re_engage_3d",
                    reason=f"静默 {silence_days} 天",
                    payload={"days": silence_days},
                ))
            elif silence_days > 30:
                out.append(PushCandidate(
                    user_id=user_id,
                    trigger="long_break",
                    reason=f"长休 {silence_days} 天",
                    payload={"days": silence_days},
                ))

        # 2. new_jobs
        if user.get("new_jobs_count", 0) >= 5:
            out.append(PushCandidate(
                user_id=user_id,
                trigger="new_jobs",
                reason=f"本周新增 {user['new_jobs_count']} 个职位",
                payload={"count": user["new_jobs_count"]},
            ))

        # 3. interview_tomorrow
        iv_at = user.get("upcoming_interview_at")
        if iv_at:
            try:
                iv = datetime.fromisoformat(iv_at)
            except ValueError:
                iv = None
            if iv is not None:
                delta = iv - now
                if timedelta(hours=0) < delta <= timedelta(hours=24):
                    out.append(PushCandidate(
                        user_id=user_id,
                        trigger="interview_tomorrow",
                        reason=f"面试还有 {delta.total_seconds() // 3600:.0f} 小时",
                        payload={"interview_at": iv_at},
                    ))

        return out

    # ----------------- 批量调度 -----------------
    async def run_once(self, *, max_users: int = 500) -> List[PushLog]:
        """跑一轮扫描 — 返回 PushLog 列表."""
        with self._lock:
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            user_ids = list(self._registered_users.keys())[:max_users]

        logs: List[PushLog] = []
        for uid in user_ids:
            candidates = self.evaluate_user(uid)
            for cand in candidates:
                log = await self._dispatch(uid, cand)
                logs.append(log)
        with self._lock:
            self._logs.extend(logs)
            # 只保留最近 1000 条
            self._logs = self._logs[-1000:]
        return logs

    # ----------------- 实际推送 -----------------
    async def _dispatch(self, user_id: str, cand: PushCandidate) -> PushLog:
        """委托给 proactive_outreach.T3601 做实际推送."""
        try:
            from services.jobseeker.proactive_outreach import (
                get_outreach_service,
            )
            outreach = get_outreach_service()
            msg = await outreach.reach_out(
                user_id=user_id,
                reason=cand.trigger,
                name="同学",
                **cand.payload,
            )
            status = "dispatched" if msg.metadata.get("skipped") is None else (
                "skipped_quiet" if msg.metadata["skipped"] == "quiet_hours" else "skipped_quota"
            )
            return PushLog(
                id=msg.metadata.get("push_id", f"plog-{datetime.now(timezone.utc).timestamp()}"),
                user_id=user_id,
                trigger=cand.trigger,
                status=status,
                reason=cand.reason,
                channels=msg.channels,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("dispatch failed: %s", e)
            return PushLog(
                id=f"plog-err-{datetime.now(timezone.utc).timestamp()}",
                user_id=user_id,
                trigger=cand.trigger,
                status="failed",
                reason=str(e),
                channels=[],
            )

    # ----------------- 查询 -----------------
    def get_logs(self, *, user_id: Optional[str] = None, limit: int = 100) -> List[PushLog]:
        with self._lock:
            logs = self._logs
            if user_id:
                logs = [l for l in logs if l.user_id == user_id]
            return logs[-limit:]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._logs)
            by_status: Dict[str, int] = {}
            by_trigger: Dict[str, int] = {}
            for l in self._logs:
                by_status[l.status] = by_status.get(l.status, 0) + 1
                by_trigger[l.trigger] = by_trigger.get(l.trigger, 0) + 1
            return {
                "total": total,
                "by_status": by_status,
                "by_trigger": by_trigger,
                "last_run_at": self._last_run_at,
                "registered_users": len(self._registered_users),
            }

    # ----------------- 后台定时 (可选) -----------------
    async def run_forever(self, *, interval_minutes: int = 60) -> None:
        """无限循环: 每 interval_minutes 跑一次."""
        while True:
            await self.run_once()
            await asyncio.sleep(interval_minutes * 60)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[ProactiveSchedulerService] = None
_singleton_lock = threading.Lock()


def get_proactive_scheduler() -> ProactiveSchedulerService:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = ProactiveSchedulerService()
        return _singleton


def reset_proactive_scheduler() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None