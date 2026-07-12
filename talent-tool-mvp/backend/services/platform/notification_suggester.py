"""T2304 智能通知建议生成器.

职责:
1. ``analyze_usage`` —— 读取最近 7 天 ``notification_log``, 统计:
   - 每个 category 的发送总量
   - 每个 (category, priority) 的发送量
   - 每个 channel 的发送量
   - 用户读取率 (placeholder, 通过 web 通道标记)

2. ``generate_suggestions`` —— 基于统计 + LLM 生成优化建议, 例如:
   - 工单类别 24/7 高频 -> 建议把 priority 降为 medium
   - 系统告警在深夜触发但未读 -> 建议把 quiet_hours 延长到 09:00
   - 邮件 channel 长期 0 打开 -> 建议禁用该 channel
   - 匹配通知每天 50+ 条 -> 建议改 weekly digest

3. ``apply_suggestion`` —— 把状态置为 applied, 同时调用 prefs service
   修改对应 ``notification_prefs`` 行.

LLM 调用策略:
- 默认无 LLM 调用: 基于规则 (硬编码阈值) 即可给出建议, 离线可跑.
- 若环境提供 ``NotificationSuggesterLLM`` 协议实现 (例如 LLM_BUDGET 模块),
  自动升级为 LLM 推荐 (例: '工单优先级建议降为 medium').

依赖:
- ``notification_prefs`` —— 写入新建议前查 prefs, 避免重复建议.
- ``notification_log`` —— 数据源.
- ``smart_suggestions`` —— 输出表.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Protocol

logger = logging.getLogger("recruittech.services.platform.notification_suggester")


# ---------------------------------------------------------------------------
# 阈值 (基于规则的建议用)
# ---------------------------------------------------------------------------

# category 7 天发送量超过此值 -> 建议降级 (digest 或 lower priority)
CATEGORY_VOLUME_THRESHOLD = 30
# priority=high 7 天发送量超过此值 -> 建议 medium
HIGH_VOLUME_THRESHOLD = 15
# 深夜命中率高 (>=50% 且总量 >=5) -> 建议延长静默
NIGHT_HIT_RATIO_THRESHOLD = 0.5
NIGHT_MIN_TOTAL = 5
# channel 0 触发 -> 建议禁用
CHANNEL_IDLE_DAYS = 7


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class UsageStats:
    """7 天使用统计."""

    user_id: str
    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    by_channel: dict[str, int] = field(default_factory=dict)
    by_priority: dict[str, int] = field(default_factory=dict)
    night_hits: int = 0  # quiet_hours_hit=True 的次数
    throttled_count: int = 0  # 被降噪掉的次数
    window_start: str = ""
    window_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "total": self.total,
            "by_category": dict(self.by_category),
            "by_channel": dict(self.by_channel),
            "by_priority": dict(self.by_priority),
            "night_hits": self.night_hits,
            "throttled_count": self.throttled_count,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }


@dataclass(slots=True)
class SmartSuggestion:
    """一条建议."""

    type: str  # priority_reduce / category_disable / channel_change / frequency_change / quiet_hours_extend
    description: str
    suggestion: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "suggestion": dict(self.suggestion),
            "confidence": self.confidence,
        }


# LLM 协议 (可选注入)
class NotificationSuggesterLLM(Protocol):
    async def recommend(
        self, stats: UsageStats, candidate_suggestions: list[SmartSuggestion]
    ) -> list[SmartSuggestion]: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NotificationSuggester:
    """智能通知建议生成器."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        prefs_service: Any | None = None,
        llm: NotificationSuggesterLLM | None = None,
    ) -> None:
        self._client_override = client
        self._prefs_override = prefs_service
        self._llm = llm

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        from api.deps import get_supabase_admin

        return get_supabase_admin()

    def _prefs(self) -> Any:
        if self._prefs_override is not None:
            return self._prefs_override
        from .notification_prefs import get_prefs_service

        return get_prefs_service()

    # ---- 分析 ----

    async def analyze_usage(
        self,
        user_id: str,
        *,
        days: int = 7,
        now_utc: datetime | None = None,
    ) -> UsageStats:
        """7 天使用统计."""
        now = now_utc or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        supabase = self._client()
        result = (
            supabase.table("notification_log")
            .select("category,channel,priority,throttled,quiet_hours_hit")
            .eq("user_id", user_id)
            .gte("sent_at", cutoff.isoformat())
            .execute()
        )

        stats = UsageStats(
            user_id=user_id,
            window_start=cutoff.isoformat(),
            window_end=now.isoformat(),
        )
        for row in (result.data or []):
            stats.total += 1
            cat = row.get("category") or "unknown"
            ch = row.get("channel") or "unknown"
            pri = row.get("priority") or "medium"
            stats.by_category[cat] = stats.by_category.get(cat, 0) + 1
            stats.by_channel[ch] = stats.by_channel.get(ch, 0) + 1
            stats.by_priority[pri] = stats.by_priority.get(pri, 0) + 1
            if row.get("quiet_hours_hit"):
                stats.night_hits += 1
            if row.get("throttled"):
                stats.throttled_count += 1
        return stats

    # ---- 建议生成 ----

    async def generate_suggestions(
        self,
        user_id: str,
        *,
        days: int = 7,
        now_utc: datetime | None = None,
    ) -> list[SmartSuggestion]:
        """主入口: 7 天分析 → 候选建议 → 可选 LLM 优化 → 去重.

        返回的建议不直接写库 (由调用方决定 ``save`` 或 preview).
        """
        stats = await self.analyze_usage(user_id, days=days, now_utc=now_utc)

        candidates: list[SmartSuggestion] = []
        candidates.extend(self._rule_priority_reduce(stats))
        candidates.extend(self._rule_category_volume(stats))
        candidates.extend(self._rule_quiet_hours_extend(stats))
        candidates.extend(self._rule_channel_idle(stats))

        # 可选 LLM 增强 (例如重新排序 / 改写文案 / 补充额外建议)
        if self._llm is not None and stats.total > 0:
            try:
                enhanced = await self._llm.recommend(stats, candidates)
                if enhanced:
                    candidates = enhanced
            except Exception as exc:  # pragma: no cover
                logger.warning("LLM recommend failed, falling back to rules: %s", exc)

        # 去重: 同 type + 相同 suggestion 主键的合并
        deduped = self._dedupe(candidates)
        return deduped

    # ---- 规则 ----

    def _rule_priority_reduce(self, stats: UsageStats) -> list[SmartSuggestion]:
        """high priority 7 天内超 HIGH_VOLUME_THRESHOLD -> 建议降为 medium."""
        out: list[SmartSuggestion] = []
        high = stats.by_priority.get("high", 0)
        if high >= HIGH_VOLUME_THRESHOLD:
            # 找出最频繁的 high category
            high_cats = sorted(stats.by_category.items(), key=lambda kv: kv[1], reverse=True)
            for cat, cnt in high_cats[:3]:
                if cnt >= HIGH_VOLUME_THRESHOLD // 3:
                    out.append(
                        SmartSuggestion(
                            type="priority_reduce",
                            description=(
                                f"「{cat}」类别 7 天内有 {cnt} 条高优先级通知, "
                                "建议把 priority 降为 medium 以减少干扰."
                            ),
                            suggestion={
                                "category": cat,
                                "priority": "medium",
                            },
                            confidence=0.8,
                        )
                    )
        return out

    def _rule_category_volume(self, stats: UsageStats) -> list[SmartSuggestion]:
        """category 7 天总量超过 CATEGORY_VOLUME_THRESHOLD -> 建议改 weekly digest."""
        out: list[SmartSuggestion] = []
        for cat, cnt in stats.by_category.items():
            if cnt >= CATEGORY_VOLUME_THRESHOLD:
                out.append(
                    SmartSuggestion(
                        type="frequency_change",
                        description=(
                            f"「{cat}」类别 7 天发送 {cnt} 条, 频繁打扰, "
                            "建议改为 weekly digest 摘要查看."
                        ),
                        suggestion={
                            "category": cat,
                            "frequency": "weekly",
                        },
                        confidence=0.75,
                    )
                )
        return out

    def _rule_quiet_hours_extend(self, stats: UsageStats) -> list[SmartSuggestion]:
        """深夜命中率高 -> 建议延长静默时间 (例: 22:00 -> 09:00)."""
        out: list[SmartSuggestion] = []
        if stats.total >= NIGHT_MIN_TOTAL and stats.night_hits >= NIGHT_MIN_TOTAL:
            ratio = stats.night_hits / max(stats.total, 1)
            if ratio >= NIGHT_HIT_RATIO_THRESHOLD:
                out.append(
                    SmartSuggestion(
                        type="quiet_hours_extend",
                        description=(
                            f"7 天内 {stats.night_hits}/{stats.total} ({ratio:.0%}) "
                            "通知命中静默时间, 建议把结束时间从 08:00 延长到 09:00."
                        ),
                        suggestion={
                            "quiet_hours_end": "09:00",
                        },
                        confidence=0.7,
                    )
                )
        return out

    def _rule_channel_idle(self, stats: UsageStats) -> list[SmartSuggestion]:
        """某 channel 7 天内无任何发送 -> 建议禁用 (节省成本)."""
        out: list[SmartSuggestion] = []
        from .notification_prefs import VALID_CHANNELS

        active = set(stats.by_channel.keys())
        for ch in VALID_CHANNELS:
            if ch not in active:
                out.append(
                    SmartSuggestion(
                        type="channel_change",
                        description=(
                            f"「{ch}」通道 7 天内 0 次发送, 你可能不需要该通道, "
                            "建议关闭以减少噪音."
                        ),
                        suggestion={
                            "channel": ch,
                            "enabled": False,
                        },
                        confidence=0.6,
                    )
                )
        return out

    def _dedupe(self, items: Iterable[SmartSuggestion]) -> list[SmartSuggestion]:
        seen: set[tuple[str, str]] = set()
        out: list[SmartSuggestion] = []
        for s in items:
            key = (s.type, str(sorted(s.suggestion.items())))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    # ---- 持久化 ----

    async def save_suggestions(
        self,
        user_id: str,
        suggestions: list[SmartSuggestion],
        *,
        based_on: UsageStats | None = None,
    ) -> list[str]:
        """写入 ``smart_suggestions`` 表. 返回写入的 id 列表."""
        if not suggestions:
            return []
        supabase = self._client()
        rows = [
            {
                "user_id": user_id,
                "type": s.type,
                "description": s.description,
                "suggestion": s.suggestion,
                "confidence": s.confidence,
                "status": "pending",
                "based_on": based_on.to_dict() if based_on else {},
            }
            for s in suggestions
        ]
        result = supabase.table("smart_suggestions").insert(rows).execute()
        if result.data:
            return [str(r["id"]) for r in result.data]
        return []

    async def list_pending(self, user_id: str) -> list[dict[str, Any]]:
        """读取用户未处理的建议."""
        supabase = self._client()
        result = (
            supabase.table("smart_suggestions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def apply_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        """应用建议: 标记 applied + 修改对应 notification_prefs 行.

        仅支持以下类型:
        - priority_reduce: 修改 (category, priority=high) 行为 medium
        - frequency_change: 修改 category 默认频率
        - channel_change: 修改 channel 默认 enabled
        - quiet_hours_extend: 修改默认静默结束时间
        """
        supabase = self._client()
        result = (
            supabase.table("smart_suggestions")
            .select("*")
            .eq("id", suggestion_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result or not getattr(result, "data", None):
            return False
        row = result.data
        if row.get("status") != "pending":
            logger.info("suggestion %s already %s", suggestion_id, row.get("status"))
            return False

        sug = row.get("suggestion") or {}
        stype = row["type"]

        prefs = self._prefs()
        if stype == "priority_reduce":
            cat = sug.get("category")
            target_pri = sug.get("priority", "medium")
            if cat and target_pri in ("medium", "low"):
                # 关掉所有 high, 打开 target_pri (用默认 channel=web)
                await prefs.set_prefs(
                    user_id,
                    category=cat,
                    priority="high",
                    channel="web",
                    enabled=False,
                )
                await prefs.set_prefs(
                    user_id,
                    category=cat,
                    priority=target_pri,
                    channel="web",
                    enabled=True,
                )

        elif stype == "frequency_change":
            cat = sug.get("category")
            freq = sug.get("frequency", "weekly")
            if cat and freq in ("realtime", "hourly", "daily", "weekly"):
                await prefs.set_prefs(
                    user_id,
                    category=cat,
                    priority="medium",
                    channel="web",
                    frequency=freq,
                    enabled=True,
                )

        elif stype == "channel_change":
            ch = sug.get("channel")
            enabled = bool(sug.get("enabled", False))
            if ch:
                # 关闭该 channel 在所有 (category, priority) 上的默认
                for cat in ("matching", "ticket", "emotion", "system", "recruiting"):
                    await prefs.set_prefs(
                        user_id,
                        category=cat,
                        priority="medium",
                        channel=ch,
                        enabled=enabled,
                    )

        elif stype == "quiet_hours_extend":
            # 直接更新所有行
            (
                supabase.table("notification_prefs")
                .update({"quiet_hours_end": sug.get("quiet_hours_end", "09:00")})
                .eq("user_id", user_id)
                .execute()
            )

        # 标记 applied
        (
            supabase.table("smart_suggestions")
            .update({
                "status": "applied",
                "applied_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", suggestion_id)
            .execute()
        )
        return True

    async def dismiss_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        """用户忽略建议."""
        supabase = self._client()
        result = (
            supabase.table("smart_suggestions")
            .update({
                "status": "dismissed",
                "dismissed_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", suggestion_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------

_suggester: NotificationSuggester | None = None


def get_suggester() -> NotificationSuggester:
    """全局 suggester 单例."""
    global _suggester
    if _suggester is None:
        _suggester = NotificationSuggester()
    return _suggester


def set_suggester(svc: NotificationSuggester | None) -> None:
    global _suggester
    _suggester = svc


def reset_suggester() -> None:
    set_suggester(None)


__all__ = [
    "NotificationSuggester",
    "NotificationSuggesterLLM",
    "SmartSuggestion",
    "UsageStats",
    "get_suggester",
    "reset_suggester",
    "set_suggester",
]