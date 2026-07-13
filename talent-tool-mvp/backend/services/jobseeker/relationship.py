"""v8.1 T3601 — Relationship State Machine.

需求 1.1: 知心朋友 — 情感化 + 主动关心

把"我跟用户的关系"显式建模为状态机,所有阶段切换都写
``relationship_events`` 表 (append-only 审计),以便:

* 个人化欢迎语 / 语气切换 / 头像表情
* 主动 push 的触发判断 (哪个阶段适合什么节奏)
* 分析用户旅程 (流失节点 / 高转化节点)

设计原则:

* 阶段只能向前推进一格 (单步状态机),保证状态机简单可解释.
  例外: 用户回到 ACTIVE_JOB_SEEKER (从 ON_BREAK / NEGOTIATING 回流).
* 每次切换都写一行 relationship_events,前端做时间线渲染.
* 所有外部副作用 (push / email) 在 ``RelationshipService.apply_event``
  之后调用 — 这个方法只是状态机 + 事件落库,不直接发推送.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("recruittech.services.jobseeker.relationship")


# ---------------------------------------------------------------------------
# 枚举 / 常量
# ---------------------------------------------------------------------------
class RelationshipStage(str, Enum):
    """关系阶段 — 从入职到入职后全程跟踪."""

    NEW_USER = "new_user"  # 刚注册,未上传简历
    ACTIVE_JOB_SEEKER = "active_job_seeker"  # 正在找工作,高频互动
    ON_BREAK = "on_break"  # 暂停求职 (休假/生病/准备考试)
    NEGOTIATING = "negotiating"  # 至少 1 个 offer 在谈判中
    HIRED = "hired"  # 已入职,关系进入 offer-后 阶段


# EventType — 触发状态切换的事件
EVENT_JOURNAL_LOGGED = "journal_logged"
EVENT_RESUME_UPLOADED = "resume_uploaded"
EVENT_INTERVIEW_SCHEDULED = "interview_scheduled"
EVENT_OFFER_RECEIVED = "offer_received"
EVENT_OFFER_ACCEPTED = "offer_accepted"
EVENT_HIRED = "hired"
EVENT_GO_SILENT = "go_silent"  # 7+ 天没互动
EVENT_RETURNED = "returned"  # 重新激活
EVENT_EXPLICIT_BREAK = "explicit_break"  # 用户主动说暂停


# 阶段切换规则 — (from_stage, event_type) -> to_stage
# 不在表中的组合不切换 (返回原 stage)
_TRANSITIONS: Dict[Tuple[str, str], str] = {
    # NEW_USER
    (RelationshipStage.NEW_USER.value, EVENT_RESUME_UPLOADED): RelationshipStage.ACTIVE_JOB_SEEKER.value,
    (RelationshipStage.NEW_USER.value, EVENT_JOURNAL_LOGGED): RelationshipStage.ACTIVE_JOB_SEEKER.value,
    # ACTIVE_JOB_SEEKER
    (RelationshipStage.ACTIVE_JOB_SEEKER.value, EVENT_INTERVIEW_SCHEDULED): RelationshipStage.ACTIVE_JOB_SEEKER.value,  # 同一阶段 = 留档
    (RelationshipStage.ACTIVE_JOB_SEEKER.value, EVENT_OFFER_RECEIVED): RelationshipStage.NEGOTIATING.value,
    (RelationshipStage.ACTIVE_JOB_SEEKER.value, EVENT_OFFER_ACCEPTED): RelationshipStage.HIRED.value,
    (RelationshipStage.ACTIVE_JOB_SEEKER.value, EVENT_EXPLICIT_BREAK): RelationshipStage.ON_BREAK.value,
    (RelationshipStage.ACTIVE_JOB_SEEKER.value, EVENT_GO_SILENT): RelationshipStage.ON_BREAK.value,
    # ON_BREAK
    (RelationshipStage.ON_BREAK.value, EVENT_RETURNED): RelationshipStage.ACTIVE_JOB_SEEKER.value,
    (RelationshipStage.ON_BREAK.value, EVENT_RESUME_UPLOADED): RelationshipStage.ACTIVE_JOB_SEEKER.value,
    # NEGOTIATING
    (RelationshipStage.NEGOTIATING.value, EVENT_OFFER_ACCEPTED): RelationshipStage.HIRED.value,
    (RelationshipStage.NEGOTIATING.value, EVENT_OFFER_RECEIVED): RelationshipStage.NEGOTIATING.value,  # 多 offer
    (RelationshipStage.NEGOTIATING.value, EVENT_EXPLICIT_BREAK): RelationshipStage.ON_BREAK.value,
    # HIRED (终态)
    (RelationshipStage.HIRED.value, EVENT_RETURNED): RelationshipStage.ACTIVE_JOB_SEEKER.value,  # 离职回流
}


# 阶段 -> 推荐语气 (前端 ChatBubble 用)
STAGE_TONE: Dict[str, Dict[str, str]] = {
    RelationshipStage.NEW_USER.value: {
        "tone": "friendly",
        "avatar": "wave",
        "greeting_template": "欢迎加入 {name}!我是你的求职顾问小 W,接下来我会陪你走完这段旅程。",
    },
    RelationshipStage.ACTIVE_JOB_SEEKER.value: {
        "tone": "casual",
        "avatar": "smile",
        "greeting_template": "嘿 {name},今天准备搞点什么?我看到 3 个新职位可能适合你。",
    },
    RelationshipStage.ON_BREAK.value: {
        "tone": "gentle",
        "avatar": "heart",
        "greeting_template": "{name},休息得怎么样?等你准备好了随时回来,我一直都在。",
    },
    RelationshipStage.NEGOTIATING.value: {
        "tone": "formal",
        "avatar": "briefcase",
        "greeting_template": "{name} 你好,offer 谈判期需要谨慎处理,我们可以一起拆解条款。",
    },
    RelationshipStage.HIRED.value: {
        "tone": "celebratory",
        "avatar": "tada",
        "greeting_template": "恭喜 {name}!🎉 入职顺利的话,3 个月后我再回访,帮你度过试用期。",
    },
}


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RelationshipEvent:
    """关系事件 (append-only 审计 + 前端时间线)."""

    id: str
    user_id: str
    event_type: str
    from_stage: str
    to_stage: str
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RelationshipState:
    """用户当前关系状态 (汇总)."""

    user_id: str
    stage: str = RelationshipStage.NEW_USER.value
    last_event_at: str = ""
    last_interaction_at: str = ""
    days_since_interaction: int = 0
    stage_entered_at: str = ""
    history_count: int = 0
    push_quota_today: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------
class RelationshipService:
    """状态机服务 — 单进程,内存索引 + 可选 Supabase."""

    def __init__(self) -> None:
        self._states: Dict[str, RelationshipState] = {}
        self._events: List[RelationshipEvent] = []
        self._lock = threading.RLock()
        # 每天推送计数 (date_str -> {user_id -> count})
        self._daily_push_count: Dict[str, Dict[str, int]] = {}

    # ----------------- 状态查询 -----------------
    def get_state(self, user_id: str) -> RelationshipState:
        with self._lock:
            if user_id not in self._states:
                self._states[user_id] = RelationshipState(user_id=user_id)
            return self._states[user_id]

    def get_stage(self, user_id: str) -> str:
        return self.get_state(user_id).stage

    def get_tone(self, user_id: str) -> Dict[str, str]:
        """返回当前 stage 对应的语气 / 头像 / 欢迎语模板."""
        stage = self.get_stage(user_id)
        return STAGE_TONE.get(stage, STAGE_TONE[RelationshipStage.NEW_USER.value])

    def get_greeting(self, user_id: str, *, name: str = "") -> str:
        tone = self.get_tone(user_id)
        template = tone.get("greeting_template", "你好 {name}!")
        return template.format(name=name or "同学")

    def list_events(self, user_id: str, *, limit: int = 50) -> List[RelationshipEvent]:
        with self._lock:
            return [e for e in self._events if e.user_id == user_id][-limit:]

    # ----------------- 状态切换 -----------------
    def update_stage(
        self,
        user_id: str,
        event_type: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """处理事件, 返回 (from_stage, to_stage)."""
        with self._lock:
            state = self.get_state(user_id)
            from_stage = state.stage
            to_stage = _TRANSITIONS.get(
                (from_stage, event_type), from_stage
            )
            now = datetime.now(timezone.utc).isoformat()
            if to_stage != from_stage:
                state.stage = to_stage
                state.stage_entered_at = now
            state.last_event_at = now
            state.history_count += 1
            context = context or {}

            ev = RelationshipEvent(
                id=_uuid(),
                user_id=user_id,
                event_type=event_type,
                from_stage=from_stage,
                to_stage=to_stage,
                context=context,
                created_at=now,
            )
            self._events.append(ev)
            # 触发 EventBus (best-effort)
            try:
                from eventbus import emit

                emit(
                    "relationship.stage_changed",
                    {
                        "user_id": user_id,
                        "from": from_stage,
                        "to": to_stage,
                        "event": event_type,
                        "context": context,
                    },
                    source="relationship.service",
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("eventbus emit failed: %s", e)

            # 持久化 (best-effort, 不阻塞主流程)
            self._persist_event(ev)
            return from_stage, to_stage

    # ----------------- 互动活跃度 -----------------
    def touch_interaction(self, user_id: str) -> None:
        """任何用户行为调用一下,刷新 last_interaction_at + 计算静默天数."""
        with self._lock:
            state = self.get_state(user_id)
            now = datetime.now(timezone.utc)
            state.last_interaction_at = now.isoformat()
            state.days_since_interaction = 0

    def tick_silence(self) -> int:
        """后台每小时调用一次,把每个用户的 days_since_interaction +1.

        返回刚跨过 30 天静默阈值 (进入 ON_BREAK 候选) 的 user 数.
        """
        crossed = 0
        with self._lock:
            now = datetime.now(timezone.utc)
            for uid, st in self._states.items():
                if not st.last_interaction_at:
                    continue
                try:
                    last = datetime.fromisoformat(st.last_interaction_at)
                except ValueError:
                    continue
                delta_days = (now - last).days
                old = st.days_since_interaction
                st.days_since_interaction = delta_days
                if delta_days >= 30 and old < 30 and st.stage == RelationshipStage.ACTIVE_JOB_SEEKER.value:
                    self.update_stage(uid, EVENT_GO_SILENT, context={"days": delta_days})
                    crossed += 1
        return crossed

    # ----------------- 推送配额 -----------------
    def can_push(self, user_id: str, *, max_per_day: int = 3) -> bool:
        """检查今天还能不能推 (默认 3 条/天)."""
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            count_map = self._daily_push_count.setdefault(today, {})
            return count_map.get(user_id, 0) < max_per_day

    def record_push(self, user_id: str, count: int = 1) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            count_map = self._daily_push_count.setdefault(today, {})
            count_map[user_id] = count_map.get(user_id, 0) + count
            state = self.get_state(user_id)
            state.push_quota_today = count_map[user_id]

    def in_quiet_hours(self, hour: int | None = None, *, quiet_start: int = 22, quiet_end: int = 8) -> bool:
        """检查当前是否在静默时段 (默认 22:00-08:00)."""
        h = hour if hour is not None else datetime.now(timezone.utc).hour
        if quiet_start > quiet_end:
            return h >= quiet_start or h < quiet_end
        return quiet_start <= h < quiet_end

    # ----------------- 主动关怀候选 -----------------
    def candidates_for_outreach(self, *, max_users: int = 100) -> List[Dict[str, Any]]:
        """返回适合主动 push 的用户列表 + 推荐原因.

        规则:
            1. ACTIVE 且 3+ 天没互动 → re-engage
            2. ON_BREAK 且 7+ 天没互动 → 节日/长假问候
            3. NEGOTIATING 且今天有 offer 截止 → urgent
        """
        out: List[Dict[str, Any]] = []
        with self._lock:
            for uid, st in self._states.items():
                reason = None
                if st.stage == RelationshipStage.ACTIVE_JOB_SEEKER.value and 3 <= st.days_since_interaction < 30:
                    reason = "re_engage_3d"
                elif st.stage == RelationshipStage.ON_BREAK.value and st.days_since_interaction >= 7:
                    reason = "long_break_checkin"
                elif st.stage == RelationshipStage.NEGOTIATING.value and st.days_since_interaction >= 1:
                    reason = "offer_followup"
                if reason:
                    out.append(
                        {
                            "user_id": uid,
                            "stage": st.stage,
                            "days_since_interaction": st.days_since_interaction,
                            "reason": reason,
                        }
                    )
                    if len(out) >= max_users:
                        break
        return out

    # ----------------- 持久化 (best-effort) -----------------
    def _persist_event(self, ev: RelationshipEvent) -> None:
        try:
            from api.deps import get_supabase_admin

            supabase = get_supabase_admin()
            supabase.table("relationship_events").insert(
                {
                    "id": ev.id,
                    "user_id": ev.user_id,
                    "event_type": ev.event_type,
                    "from_stage": ev.from_stage,
                    "to_stage": ev.to_stage,
                    "context": ev.context,
                    "created_at": ev.created_at,
                }
            ).execute()
        except Exception as e:  # noqa: BLE001
            logger.debug("supabase persist failed (likely dev mode): %s", e)

    # ----------------- 测试辅助 -----------------
    def reset(self) -> None:
        with self._lock:
            self._states.clear()
            self._events.clear()
            self._daily_push_count.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _uuid() -> str:
    try:
        from uuid import uuid4

        return str(uuid4())
    except ImportError:  # pragma: no cover
        import random

        return f"ev-{random.randint(1, 10**9)}"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_service: Optional[RelationshipService] = None
_service_lock = threading.Lock()


def get_relationship_service() -> RelationshipService:
    global _service
    with _service_lock:
        if _service is None:
            _service = RelationshipService()
        return _service


def reset_relationship_service() -> None:
    global _service
    with _service_lock:
        _service = None