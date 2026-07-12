"""T2304 智能通知偏好服务.

核心职责:
1. ``get_prefs`` / ``set_prefs`` / ``bulk_set`` —— CRUD 用户细粒度偏好.
2. **智能降噪**: 同 (user, category, channel) 在 5 分钟窗口内只发 1 次;
   通过 ``notification_log`` 表 + ``should_send`` 判断.
3. **静默时间**: 用户配置的 ``quiet_hours_start`` - ``quiet_hours_end`` 区间内
   拒绝发送 (支持跨午夜, 例如 22:00-08:00).
4. **频率**: realtime / hourly / daily / weekly —— 非 realtime 走 ``notification_digest``
   聚合后批量发送 (本模块仅暴露 ``is_due`` 判定, 实际聚合在 dispatcher/cron 中调用).
5. **日志写入**: ``record_send`` 把每次发送结果落库, 供 ``notification_suggester`` 7 天分析.

设计要点:
- 数据库表见 ``supabase/migrations/041_notification_prefs.sql``.
- 单元测试可注入 ``_client`` 替换 supabase client, 避免依赖真实数据库.
- 静默时间判定使用 Python ``datetime.time`` 而非 DB 查询, 降低 IO.
- 默认全部开启: 用户未配置时, 5 种类别 × 3 优先级 × 5 通道 = 75 行全开.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger("recruittech.services.platform.notification_prefs")


# ---------------------------------------------------------------------------
# 常量 / 枚举
# ---------------------------------------------------------------------------

VALID_CATEGORIES = ("matching", "ticket", "emotion", "system", "recruiting")
VALID_PRIORITIES = ("high", "medium", "low")
VALID_CHANNELS = ("smtp", "dingtalk", "feishu", "im", "web")
VALID_FREQUENCIES = ("realtime", "hourly", "daily", "weekly")

# 智能降噪窗口 (同 category+channel+user 5 分钟仅一次)
THROTTLE_WINDOW = timedelta(minutes=5)

# 默认静默时间 (用于没有配置时的兜底 — 留 None 表示不静默)
DEFAULT_QUIET_HOURS: tuple[time | None, time | None] = (time(22, 0), time(8, 0))


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NotificationPref:
    """用户单条偏好."""

    user_id: str
    category: str
    priority: str
    channel: str
    frequency: str = "realtime"
    quiet_hours_start: str | None = None  # "HH:MM"
    quiet_hours_end: str | None = None
    enabled: bool = True
    id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "NotificationPref":
        return cls(
            id=row.get("id"),
            user_id=str(row["user_id"]),
            category=row["category"],
            priority=row.get("priority", "medium"),
            channel=row["channel"],
            frequency=row.get("frequency", "realtime"),
            quiet_hours_start=row.get("quiet_hours_start"),
            quiet_hours_end=row.get("quiet_hours_end"),
            enabled=row.get("enabled", True),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "priority": self.priority,
            "channel": self.channel,
            "frequency": self.frequency,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class PrefDecision:
    """prefs 决策结果 (发送/降噪/静默)."""

    should_send: bool
    reason: str
    frequency: str = "realtime"
    quiet_hours_hit: bool = False
    throttled: bool = False


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _parse_hhmm(s: str | None) -> time | None:
    """解析 "HH:MM" 字符串; 失败返回 None."""
    if not s or not isinstance(s, str):
        return None
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h < 24 and 0 <= m < 60:
            return time(h, m)
    except (ValueError, TypeError):
        pass
    return None


def _in_quiet_hours(
    quiet_start: str | None,
    quiet_end: str | None,
    *,
    now_utc: datetime | None = None,
) -> bool:
    """判断当前 UTC 时间是否落在静默区间内.

    支持跨午夜 (例如 22:00-08:00): now in [start, 24:00) ∪ [00:00, end).
    """
    s = _parse_hhmm(quiet_start)
    e = _parse_hhmm(quiet_end)
    if s is None or e is None:
        return False

    now = (now_utc or datetime.now(timezone.utc)).time()

    if s <= e:
        # 同一天窗口, 例如 12:00-14:00
        return s <= now < e
    else:
        # 跨午夜: 22:00-08:00
        return now >= s or now < e


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NotificationPrefsService:
    """用户通知偏好服务 (单例)."""

    def __init__(self, *, client: Any | None = None) -> None:
        """构造时可注入 supabase client (测试用)."""
        self._client_override = client

    # ---- 客户端 ----

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        # 局部 import 避免启动期循环
        from api.deps import get_supabase_admin

        return get_supabase_admin()

    # ---- CRUD ----

    async def get_prefs(self, user_id: str) -> list[NotificationPref]:
        """查询用户的所有偏好; 用户无配置时返回空列表 (dispatcher 走默认全开)."""
        supabase = self._client()
        result = (
            supabase.table("notification_prefs")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        rows = result.data or []
        return [NotificationPref.from_row(r) for r in rows]

    async def get_pref(
        self,
        user_id: str,
        category: str,
        priority: str,
        channel: str,
    ) -> NotificationPref | None:
        """查询单条偏好 (category × priority × channel)."""
        supabase = self._client()
        result = (
            supabase.table("notification_prefs")
            .select("*")
            .eq("user_id", user_id)
            .eq("category", category)
            .eq("priority", priority)
            .eq("channel", channel)
            .maybe_single()
            .execute()
        )
        if result and getattr(result, "data", None):
            return NotificationPref.from_row(result.data)
        return None

    async def set_prefs(
        self,
        user_id: str,
        *,
        category: str,
        priority: str,
        channel: str,
        frequency: str = "realtime",
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
        enabled: bool = True,
    ) -> NotificationPref:
        """写入单条偏好 (upsert)."""
        if category not in VALID_CATEGORIES:
            raise ValueError(f"invalid category: {category}")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"invalid priority: {priority}")
        if channel not in VALID_CHANNELS:
            raise ValueError(f"invalid channel: {channel}")
        if frequency not in VALID_FREQUENCIES:
            raise ValueError(f"invalid frequency: {frequency}")

        record = {
            "user_id": user_id,
            "category": category,
            "priority": priority,
            "channel": channel,
            "frequency": frequency,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
            "enabled": enabled,
        }

        supabase = self._client()
        result = (
            supabase.table("notification_prefs")
            .upsert(record, on_conflict="user_id,category,priority,channel")
            .execute()
        )

        if not result.data:
            raise RuntimeError("upsert failed: no data returned")
        return NotificationPref.from_row(result.data[0])

    async def bulk_set(
        self,
        user_id: str,
        prefs: Iterable[dict[str, Any]],
    ) -> list[NotificationPref]:
        """批量写入 (用于前端一次提交整页配置)."""
        results: list[NotificationPref] = []
        for item in prefs:
            pref = await self.set_prefs(
                user_id=user_id,
                category=item["category"],
                priority=item["priority"],
                channel=item["channel"],
                frequency=item.get("frequency", "realtime"),
                quiet_hours_start=item.get("quiet_hours_start"),
                quiet_hours_end=item.get("quiet_hours_end"),
                enabled=item.get("enabled", True),
            )
            results.append(pref)
        return results

    async def delete_pref(
        self,
        user_id: str,
        category: str,
        priority: str,
        channel: str,
    ) -> bool:
        """删除单条偏好 (恢复默认)."""
        supabase = self._client()
        result = (
            supabase.table("notification_prefs")
            .delete()
            .eq("user_id", user_id)
            .eq("category", category)
            .eq("priority", priority)
            .eq("channel", channel)
            .execute()
        )
        return bool(result.data)

    # ---- 决策 ----

    async def evaluate(
        self,
        user_id: str,
        category: str,
        priority: str,
        channel: str,
        *,
        now_utc: datetime | None = None,
    ) -> PrefDecision:
        """核心决策: 是否发送 + 原因.

        判定顺序 (短路):
        1. 用户偏好中该 (cat, pri, ch) 关闭 -> 拒绝 (not enabled)
        2. 静默时间命中 -> 拒绝 (quiet hours)
        3. 5 分钟内同 (user, category, channel) 已发送 -> 拒绝 (throttled)
        4. 频率 = realtime -> 允许; 否则 -> 等待下次 digest 窗口
        """
        # 1. 偏好关闭
        pref = await self.get_pref(user_id, category, priority, channel)
        if pref is not None and not pref.enabled:
            return PrefDecision(should_send=False, reason="preference_disabled")

        # 2. 静默时间
        quiet_start = pref.quiet_hours_start if pref else None
        quiet_end = pref.quiet_hours_end if pref else None
        if _in_quiet_hours(quiet_start, quiet_end, now_utc=now_utc):
            return PrefDecision(
                should_send=False,
                reason="quiet_hours",
                quiet_hours_hit=True,
            )

        # 3. 5 分钟降噪
        throttled = await self._is_throttled(user_id, category, channel, now_utc=now_utc)
        if throttled:
            return PrefDecision(
                should_send=False,
                reason="throttled_5min",
                throttled=True,
            )

        # 4. 频率
        frequency = pref.frequency if pref else "realtime"
        if frequency == "realtime":
            return PrefDecision(should_send=True, reason="ok", frequency=frequency)
        return PrefDecision(
            should_send=False,
            reason=f"deferred_{frequency}",
            frequency=frequency,
        )

    async def _is_throttled(
        self,
        user_id: str,
        category: str,
        channel: str,
        *,
        now_utc: datetime | None = None,
    ) -> bool:
        """检查 5 分钟降噪窗口."""
        now = now_utc or datetime.now(timezone.utc)
        cutoff = (now - THROTTLE_WINDOW).isoformat()
        supabase = self._client()
        result = (
            supabase.table("notification_log")
            .select("id")
            .eq("user_id", user_id)
            .eq("category", category)
            .eq("channel", channel)
            .eq("throttled", False)
            .gte("sent_at", cutoff)
            .limit(1)
            .execute()
        )
        return bool(result.data)

    # ---- 日志 ----

    async def record_send(
        self,
        user_id: str,
        category: str,
        priority: str,
        channel: str,
        *,
        throttled: bool = False,
        quiet_hours_hit: bool = False,
    ) -> str:
        """记录一次发送结果 (用于降噪 + 分析). 返回 log id."""
        supabase = self._client()
        result = (
            supabase.table("notification_log")
            .insert({
                "user_id": user_id,
                "category": category,
                "priority": priority,
                "channel": channel,
                "throttled": throttled,
                "quiet_hours_hit": quiet_hours_hit,
            })
            .execute()
        )
        if result.data:
            return str(result.data[0]["id"])
        return ""

    # ---- 摘要 ----

    async def record_digest(
        self,
        user_id: str,
        period: str,
        content: dict[str, Any],
        window_start: datetime,
        window_end: datetime,
    ) -> str:
        """记录一次定期摘要 (hourly/daily/weekly)."""
        if period not in ("hourly", "daily", "weekly"):
            raise ValueError(f"invalid period: {period}")
        supabase = self._client()
        result = (
            supabase.table("notification_digest")
            .insert({
                "user_id": user_id,
                "period": period,
                "content": content,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
            })
            .execute()
        )
        if result.data:
            return str(result.data[0]["id"])
        return ""

    async def list_digests(
        self,
        user_id: str,
        *,
        period: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """读取历史摘要."""
        supabase = self._client()
        query = (
            supabase.table("notification_digest")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(limit)
        )
        if period:
            query = query.eq("period", period)
        result = query.execute()
        return result.data or []


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_service: NotificationPrefsService | None = None


def get_prefs_service() -> NotificationPrefsService:
    """获取全局 NotificationPrefsService (懒加载单例)."""
    global _service
    if _service is None:
        _service = NotificationPrefsService()
    return _service


def set_prefs_service(svc: NotificationPrefsService | None) -> None:
    """替换单例 (测试/运行时注入)."""
    global _service
    _service = svc


def reset_prefs_service() -> None:
    """清空单例."""
    set_prefs_service(None)


__all__ = [
    "DEFAULT_QUIET_HOURS",
    "NotificationPref",
    "NotificationPrefsService",
    "PrefDecision",
    "THROTTLE_WINDOW",
    "VALID_CATEGORIES",
    "VALID_CHANNELS",
    "VALID_FREQUENCIES",
    "VALID_PRIORITIES",
    "_in_quiet_hours",
    "_parse_hhmm",
    "get_prefs_service",
    "reset_prefs_service",
    "set_prefs_service",
]