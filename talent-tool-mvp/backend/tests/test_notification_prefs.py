"""T2304 — 智能通知偏好测试.

覆盖:
- ``notification_prefs``: CRUD / upsert / bulk / quiet hours 解析 / 决策 (降噪/静默/频率)
- ``notification_suggester``: 7 天分析 + 规则建议生成 + apply/dismiss
- ``dispatcher``: T2304 ``dispatch_with_prefs`` 集成 (静默/降噪/成功)

使用 in-memory supabase mock (与 test_config_service 模式一致).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# In-memory supabase backend
# ---------------------------------------------------------------------------


class _MemoryBackend:
    """Supabase in-memory 替身.

    支持 table().select/insert/update/delete/upsert + eq + gte + order + limit + maybe_single + execute.
    """

    def __init__(self) -> None:
        self.data: Dict[str, List[Dict[str, Any]]] = {
            "notification_prefs": [],
            "notification_log": [],
            "notification_digest": [],
            "smart_suggestions": [],
        }

    def table(self, name: str) -> "_Table":
        return _Table(self, name)


class _Table:
    def __init__(self, backend: _MemoryBackend, name: str) -> None:
        self.backend = backend
        self.name = name
        self._filters: List[Tuple[str, str, Any]] = []
        self._order: Optional[Tuple[str, bool]] = None
        self._limit: Optional[int] = None
        self._mode: str = "select"  # select / insert / update / delete / upsert
        self._payloads: List[Dict[str, Any]] = []
        self._maybe_single: bool = False
        self._conflict: Optional[str] = None

    # ---- mode selectors ----
    def select(self, _cols: str = "*") -> "_Table":
        self._mode = "select"
        return self

    def insert(self, rows: Any) -> "_Table":
        self._mode = "insert"
        if isinstance(rows, dict):
            self._payloads = [rows]
        else:
            self._payloads = list(rows)
        return self

    def upsert(self, rows: Any, on_conflict: Optional[str] = None) -> "_Table":
        self._mode = "upsert"
        self._conflict = on_conflict
        if isinstance(rows, dict):
            self._payloads = [rows]
        else:
            self._payloads = list(rows)
        return self

    def update(self, payload: Dict[str, Any]) -> "_Table":
        self._mode = "update"
        self._payloads = [payload]
        return self

    def delete(self) -> "_Table":
        self._mode = "delete"
        return self

    def eq(self, col: str, val: Any) -> "_Table":
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_Table":
        self._filters.append(("gte", col, val))
        return self

    def order(self, col: str, desc: bool = False) -> "_Table":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_Table":
        self._limit = n
        return self

    def maybe_single(self) -> "_Table":
        self._maybe_single = True
        return self

    # ---- execute ----
    def execute(self) -> "_Result":
        rows = list(self.backend.data[self.name])

        # Apply filters
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "gte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) >= val]

        if self._mode == "select":
            if self._order:
                col, desc = self._order
                rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=desc)
            if self._limit:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _Result(data=rows[0] if rows else None)
            return _Result(data=rows)

        if self._mode == "insert":
            for p in self._payloads:
                if "id" not in p:
                    p["id"] = str(uuid4())
                self.backend.data[self.name].append(p)
            return _Result(data=list(self._payloads))

        if self._mode == "update":
            updated = []
            for r in rows:
                for p in self._payloads:
                    r.update(p)
                updated.append(r)
            return _Result(data=updated)

        if self._mode == "delete":
            ids = {r.get("id") for r in rows}
            self.backend.data[self.name] = [
                r for r in self.backend.data[self.name] if r.get("id") not in ids
            ]
            return _Result(data=rows)

        if self._mode == "upsert":
            # 用 on_conflict 列去重
            if self._conflict:
                conflict_keys = [k.strip() for k in self._conflict.split(",")]
            else:
                conflict_keys = []
            out = []
            for p in self._payloads:
                # find existing match
                existing = None
                for r in self.backend.data[self.name]:
                    if all(r.get(k) == p.get(k) for k in conflict_keys):
                        existing = r
                        break
                if existing:
                    existing.update(p)
                    out.append(existing)
                else:
                    if "id" not in p:
                        p["id"] = str(uuid4())
                    self.backend.data[self.name].append(p)
                    out.append(p)
            return _Result(data=out)

        return _Result(data=[])


class _Result:
    def __init__(self, data: Any = None) -> None:
        self.data = data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    return _MemoryBackend()


@pytest.fixture
def prefs_service(backend):
    from services.platform.notification_prefs import (
        NotificationPrefsService,
        reset_prefs_service,
    )

    reset_prefs_service()
    svc = NotificationPrefsService(client=backend)
    return svc


@pytest.fixture
def suggester(backend, prefs_service):
    from services.platform.notification_suggester import (
        NotificationSuggester,
        reset_suggester,
    )

    reset_suggester()
    return NotificationSuggester(client=backend, prefs_service=prefs_service)


@pytest.fixture
def user_id():
    return str(uuid4())


# ===========================================================================
# 1. _parse_hhmm / _in_quiet_hours
# ===========================================================================


class TestHhmmParser:
    def test_valid_hhmm(self):
        from services.platform.notification_prefs import _parse_hhmm

        assert _parse_hhmm("08:00") == time(8, 0)
        assert _parse_hhmm("22:30") == time(22, 30)
        assert _parse_hhmm("00:00") == time(0, 0)
        assert _parse_hhmm("23:59") == time(23, 59)

    def test_invalid(self):
        from services.platform.notification_prefs import _parse_hhmm

        assert _parse_hhmm(None) is None
        assert _parse_hhmm("") is None
        assert _parse_hhmm("25:00") is None
        assert _parse_hhmm("12:60") is None
        assert _parse_hhmm("abc") is None
        assert _parse_hhmm("12") is None


class TestQuietHours:
    def test_within_quiet_hours_same_day(self):
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 13, 0, tzinfo=timezone.utc)
        # 12:00-14:00, now=13:00 -> inside
        assert _in_quiet_hours("12:00", "14:00", now_utc=now) is True

    def test_outside_quiet_hours_same_day(self):
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
        assert _in_quiet_hours("12:00", "14:00", now_utc=now) is False

    def test_cross_midnight_in_evening(self):
        """22:00-08:00, now=23:00 -> inside."""
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 23, 0, tzinfo=timezone.utc)
        assert _in_quiet_hours("22:00", "08:00", now_utc=now) is True

    def test_cross_midnight_in_morning(self):
        """22:00-08:00, now=06:00 -> inside."""
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc)
        assert _in_quiet_hours("22:00", "08:00", now_utc=now) is True

    def test_cross_midnight_outside(self):
        """22:00-08:00, now=12:00 -> outside."""
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        assert _in_quiet_hours("22:00", "08:00", now_utc=now) is False

    def test_no_quiet_hours(self):
        from services.platform.notification_prefs import _in_quiet_hours

        now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
        assert _in_quiet_hours(None, None, now_utc=now) is False
        assert _in_quiet_hours("22:00", None, now_utc=now) is False
        assert _in_quiet_hours(None, "08:00", now_utc=now) is False

    def test_boundary_inclusive_start_exclusive_end(self):
        """start 包含, end 排除."""
        from services.platform.notification_prefs import _in_quiet_hours

        # 12:00-14:00: 12:00 inside, 14:00 outside
        assert _in_quiet_hours("12:00", "14:00", now_utc=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)) is True
        assert _in_quiet_hours("12:00", "14:00", now_utc=datetime(2026, 7, 12, 14, 0, tzinfo=timezone.utc)) is False


# ===========================================================================
# 2. PrefsService CRUD
# ===========================================================================


class TestPrefsCrud:
    @pytest.mark.asyncio
    async def test_set_prefs_returns_pref(self, prefs_service, user_id):
        pref = await prefs_service.set_prefs(
            user_id,
            category="matching",
            priority="high",
            channel="web",
            frequency="realtime",
            enabled=True,
        )
        assert pref.category == "matching"
        assert pref.priority == "high"
        assert pref.channel == "web"
        assert pref.enabled is True
        assert pref.id is not None

    @pytest.mark.asyncio
    async def test_set_prefs_validates_category(self, prefs_service, user_id):
        with pytest.raises(ValueError):
            await prefs_service.set_prefs(
                user_id, category="invalid", priority="high", channel="web"
            )

    @pytest.mark.asyncio
    async def test_set_prefs_validates_priority(self, prefs_service, user_id):
        with pytest.raises(ValueError):
            await prefs_service.set_prefs(
                user_id, category="matching", priority="urgent", channel="web"
            )

    @pytest.mark.asyncio
    async def test_set_prefs_validates_channel(self, prefs_service, user_id):
        with pytest.raises(ValueError):
            await prefs_service.set_prefs(
                user_id, category="matching", priority="high", channel="telegram"
            )

    @pytest.mark.asyncio
    async def test_set_prefs_validates_frequency(self, prefs_service, user_id):
        with pytest.raises(ValueError):
            await prefs_service.set_prefs(
                user_id, category="matching", priority="high",
                channel="web", frequency="instant"
            )

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self, prefs_service, user_id):
        p1 = await prefs_service.set_prefs(
            user_id, category="ticket", priority="medium", channel="web", enabled=True
        )
        p2 = await prefs_service.set_prefs(
            user_id, category="ticket", priority="medium", channel="web", enabled=False
        )
        assert p1.id == p2.id  # 同一行被覆盖
        assert p2.enabled is False

    @pytest.mark.asyncio
    async def test_get_prefs_returns_all(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id, category="matching", priority="high", channel="web"
        )
        await prefs_service.set_prefs(
            user_id, category="matching", priority="low", channel="dingtalk"
        )
        await prefs_service.set_prefs(
            user_id, category="system", priority="medium", channel="smtp"
        )
        prefs = await prefs_service.get_prefs(user_id)
        assert len(prefs) == 3
        cats = {p.category for p in prefs}
        assert cats == {"matching", "system"}

    @pytest.mark.asyncio
    async def test_get_pref_returns_specific(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id, category="matching", priority="high", channel="web", enabled=False
        )
        pref = await prefs_service.get_pref(user_id, "matching", "high", "web")
        assert pref is not None
        assert pref.enabled is False

        # 不存在
        miss = await prefs_service.get_pref(user_id, "ticket", "high", "web")
        assert miss is None

    @pytest.mark.asyncio
    async def test_bulk_set(self, prefs_service, user_id):
        prefs = await prefs_service.bulk_set(
            user_id,
            [
                {"category": "matching", "priority": "high", "channel": "web", "enabled": True},
                {"category": "matching", "priority": "low", "channel": "dingtalk", "enabled": False},
                {"category": "ticket", "priority": "medium", "channel": "smtp", "frequency": "daily"},
            ],
        )
        assert len(prefs) == 3
        cats = {p.category for p in prefs}
        assert cats == {"matching", "ticket"}

    @pytest.mark.asyncio
    async def test_delete_pref(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id, category="matching", priority="high", channel="web"
        )
        ok = await prefs_service.delete_pref(user_id, "matching", "high", "web")
        assert ok is True
        prefs = await prefs_service.get_prefs(user_id)
        assert prefs == []


# ===========================================================================
# 3. PrefsService.evaluate (核心决策)
# ===========================================================================


class TestEvaluate:
    @pytest.mark.asyncio
    async def test_no_pref_means_allow(self, prefs_service, user_id):
        """用户未配置 -> 默认允许发送."""
        decision = await prefs_service.evaluate(
            user_id, "matching", "high", "web"
        )
        assert decision.should_send is True
        assert decision.reason == "ok"

    @pytest.mark.asyncio
    async def test_disabled_pref_blocks(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id, category="ticket", priority="high", channel="dingtalk", enabled=False
        )
        decision = await prefs_service.evaluate(
            user_id, "ticket", "high", "dingtalk"
        )
        assert decision.should_send is False
        assert decision.reason == "preference_disabled"

    @pytest.mark.asyncio
    async def test_quiet_hours_blocks(self, prefs_service, user_id):
        # 静默时间 12:00-14:00 UTC, 当前 13:00
        await prefs_service.set_prefs(
            user_id,
            category="matching",
            priority="high",
            channel="web",
            quiet_hours_start="12:00",
            quiet_hours_end="14:00",
            enabled=True,
        )
        now = datetime(2026, 7, 12, 13, 0, tzinfo=timezone.utc)
        decision = await prefs_service.evaluate(
            user_id, "matching", "high", "web", now_utc=now
        )
        assert decision.should_send is False
        assert decision.quiet_hours_hit is True
        assert decision.reason == "quiet_hours"

    @pytest.mark.asyncio
    async def test_quiet_hours_outside_allows(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id,
            category="matching", priority="high", channel="web",
            quiet_hours_start="22:00", quiet_hours_end="08:00",
            enabled=True,
        )
        # 中午 12:00 -> outside quiet
        now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        decision = await prefs_service.evaluate(
            user_id, "matching", "high", "web", now_utc=now
        )
        assert decision.should_send is True

    @pytest.mark.asyncio
    async def test_throttle_blocks_within_5min(self, prefs_service, user_id, backend):
        # 模拟 3 分钟前已发过同 (user, category, channel)
        backend.data["notification_log"].append({
            "id": str(uuid4()),
            "user_id": user_id,
            "category": "matching",
            "priority": "high",
            "channel": "web",
            "throttled": False,
            "quiet_hours_hit": False,
            "sent_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
        })
        decision = await prefs_service.evaluate(
            user_id, "matching", "high", "web"
        )
        assert decision.should_send is False
        assert decision.throttled is True
        assert decision.reason == "throttled_5min"

    @pytest.mark.asyncio
    async def test_throttle_allows_after_5min(self, prefs_service, user_id, backend):
        # 6 分钟前 -> 不算降噪
        backend.data["notification_log"].append({
            "id": str(uuid4()),
            "user_id": user_id,
            "category": "matching",
            "priority": "high",
            "channel": "web",
            "throttled": False,
            "quiet_hours_hit": False,
            "sent_at": (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(),
        })
        decision = await prefs_service.evaluate(
            user_id, "matching", "high", "web"
        )
        assert decision.should_send is True

    @pytest.mark.asyncio
    async def test_frequency_weekly_defers(self, prefs_service, user_id):
        await prefs_service.set_prefs(
            user_id, category="system", priority="medium", channel="web",
            frequency="weekly", enabled=True,
        )
        decision = await prefs_service.evaluate(
            user_id, "system", "medium", "web"
        )
        assert decision.should_send is False
        assert decision.reason == "deferred_weekly"
        assert decision.frequency == "weekly"

    @pytest.mark.asyncio
    async def test_priority_shortcut_blocks(self, prefs_service, user_id):
        """disabling high priority blocks high priority sends."""
        await prefs_service.set_prefs(
            user_id, category="ticket", priority="high", channel="smtp", enabled=False
        )
        # 但 medium priority 不受影响
        decision = await prefs_service.evaluate(
            user_id, "ticket", "medium", "smtp"
        )
        assert decision.should_send is True


# ===========================================================================
# 4. record_send / record_digest
# ===========================================================================


class TestRecords:
    @pytest.mark.asyncio
    async def test_record_send_creates_log(self, prefs_service, user_id, backend):
        log_id = await prefs_service.record_send(
            user_id, "matching", "high", "web",
            throttled=False, quiet_hours_hit=False,
        )
        assert log_id != ""
        assert len(backend.data["notification_log"]) == 1
        assert backend.data["notification_log"][0]["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_record_digest(self, prefs_service, user_id, backend):
        now = datetime.now(timezone.utc)
        did = await prefs_service.record_digest(
            user_id, "daily", {"items": 5}, now - timedelta(days=1), now
        )
        assert did != ""
        assert len(backend.data["notification_digest"]) == 1
        assert backend.data["notification_digest"][0]["period"] == "daily"

    @pytest.mark.asyncio
    async def test_record_digest_validates_period(self, prefs_service, user_id):
        with pytest.raises(ValueError):
            await prefs_service.record_digest(
                user_id, "instant", {}, datetime.now(timezone.utc), datetime.now(timezone.utc)
            )

    @pytest.mark.asyncio
    async def test_list_digests_filtered(self, prefs_service, user_id, backend):
        now = datetime.now(timezone.utc)
        await prefs_service.record_digest(user_id, "hourly", {"x": 1}, now, now)
        await prefs_service.record_digest(user_id, "daily", {"x": 2}, now, now)
        digests = await prefs_service.list_digests(user_id, period="hourly")
        assert len(digests) == 1
        assert digests[0]["period"] == "hourly"


# ===========================================================================
# 5. NotificationSuggester
# ===========================================================================


class TestSuggesterAnalyze:
    @pytest.mark.asyncio
    async def test_empty_stats(self, suggester, user_id):
        stats = await suggester.analyze_usage(user_id, days=7)
        assert stats.total == 0
        assert stats.by_category == {}
        assert stats.night_hits == 0

    @pytest.mark.asyncio
    async def test_aggregate_by_category_channel_priority(self, suggester, user_id, backend):
        now = datetime.now(timezone.utc)
        for i in range(5):
            backend.data["notification_log"].append({
                "id": str(uuid4()),
                "user_id": user_id,
                "category": "matching",
                "priority": "high",
                "channel": "web",
                "throttled": False,
                "quiet_hours_hit": False,
                "sent_at": (now - timedelta(hours=i)).isoformat(),
            })
        for i in range(3):
            backend.data["notification_log"].append({
                "id": str(uuid4()),
                "user_id": user_id,
                "category": "ticket",
                "priority": "medium",
                "channel": "dingtalk",
                "throttled": False,
                "quiet_hours_hit": True,
                "sent_at": (now - timedelta(hours=i)).isoformat(),
            })
        stats = await suggester.analyze_usage(user_id, days=7)
        assert stats.total == 8
        assert stats.by_category["matching"] == 5
        assert stats.by_category["ticket"] == 3
        assert stats.by_priority["high"] == 5
        assert stats.by_priority["medium"] == 3
        assert stats.by_channel["web"] == 5
        assert stats.night_hits == 3


class TestSuggesterRules:
    def test_rule_priority_reduce_above_threshold(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(
            user_id="u",
            by_priority={"high": 20},
            by_category={"ticket": 20},
        )
        out = suggester._rule_priority_reduce(stats)
        assert len(out) > 0
        assert any(s.type == "priority_reduce" for s in out)
        assert any("ticket" in s.description for s in out)

    def test_rule_priority_reduce_below_threshold(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(user_id="u", by_priority={"high": 5}, by_category={"ticket": 5})
        out = suggester._rule_priority_reduce(stats)
        assert out == []

    def test_rule_category_volume(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(user_id="u", by_category={"matching": 50})
        out = suggester._rule_category_volume(stats)
        assert any(s.type == "frequency_change" for s in out)
        assert out[0].suggestion["category"] == "matching"
        assert out[0].suggestion["frequency"] == "weekly"

    def test_rule_quiet_hours_extend(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(
            user_id="u",
            total=10,
            night_hits=8,  # 80%
        )
        out = suggester._rule_quiet_hours_extend(stats)
        assert any(s.type == "quiet_hours_extend" for s in out)
        assert out[0].suggestion["quiet_hours_end"] == "09:00"

    def test_rule_quiet_hours_extend_low_ratio(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(user_id="u", total=10, night_hits=2)
        out = suggester._rule_quiet_hours_extend(stats)
        assert out == []

    def test_rule_channel_idle(self, suggester):
        from services.platform.notification_suggester import UsageStats

        stats = UsageStats(user_id="u", by_channel={"web": 10})  # 没有 feishu
        out = suggester._rule_channel_idle(stats)
        # 至少会建议禁用未使用的 channel (smtp/dingtalk/feishu/im)
        types = {s.suggestion["channel"] for s in out if s.type == "channel_change"}
        assert "feishu" in types


class TestSuggesterEndToEnd:
    @pytest.mark.asyncio
    async def test_generate_suggestions_low_volume_empty(self, suggester, user_id):
        suggestions = await suggester.generate_suggestions(user_id, days=7)
        # 没有日志, 至少应该有 channel_idle 建议
        assert any(s.type == "channel_change" for s in suggestions)

    @pytest.mark.asyncio
    async def test_generate_suggestions_high_volume(self, suggester, user_id, backend):
        now = datetime.now(timezone.utc)
        # 50 条 matching 通知 (高频)
        for i in range(50):
            backend.data["notification_log"].append({
                "id": str(uuid4()),
                "user_id": user_id,
                "category": "matching",
                "priority": "medium",
                "channel": "web",
                "throttled": False,
                "quiet_hours_hit": False,
                "sent_at": (now - timedelta(hours=i % 24)).isoformat(),
            })
        suggestions = await suggester.generate_suggestions(user_id, days=7)
        assert any(s.type == "frequency_change" for s in suggestions)

    @pytest.mark.asyncio
    async def test_save_and_apply_priority_reduce(self, suggester, user_id, backend):
        from services.platform.notification_suggester import SmartSuggestion

        suggestions = [
            SmartSuggestion(
                type="priority_reduce",
                description="test",
                suggestion={"category": "ticket", "priority": "medium"},
                confidence=0.8,
            )
        ]
        ids = await suggester.save_suggestions(user_id, suggestions)
        assert len(ids) == 1

        # apply
        ok = await suggester.apply_suggestion(ids[0], user_id)
        assert ok is True

        # 验证 prefs 已写入 (high 关闭, medium 开启)
        high_pref = next(
            (r for r in backend.data["notification_prefs"]
             if r["category"] == "ticket" and r["priority"] == "high"),
            None,
        )
        med_pref = next(
            (r for r in backend.data["notification_prefs"]
             if r["category"] == "ticket" and r["priority"] == "medium"),
            None,
        )
        assert high_pref is not None and high_pref["enabled"] is False
        assert med_pref is not None and med_pref["enabled"] is True

        # suggestion 状态应为 applied
        sg = backend.data["smart_suggestions"][0]
        assert sg["status"] == "applied"

    @pytest.mark.asyncio
    async def test_apply_idempotent(self, suggester, user_id):
        from services.platform.notification_suggester import SmartSuggestion

        suggestions = [
            SmartSuggestion(
                type="priority_reduce",
                description="test",
                suggestion={"category": "ticket", "priority": "medium"},
                confidence=0.8,
            )
        ]
        ids = await suggester.save_suggestions(user_id, suggestions)
        ok1 = await suggester.apply_suggestion(ids[0], user_id)
        ok2 = await suggester.apply_suggestion(ids[0], user_id)
        assert ok1 is True
        assert ok2 is False  # 已 applied

    @pytest.mark.asyncio
    async def test_dismiss_suggestion(self, suggester, user_id):
        from services.platform.notification_suggester import SmartSuggestion

        suggestions = [
            SmartSuggestion(type="frequency_change", description="x",
                            suggestion={"category": "matching", "frequency": "weekly"})
        ]
        ids = await suggester.save_suggestions(user_id, suggestions)
        ok = await suggester.dismiss_suggestion(ids[0], user_id)
        assert ok is True

        sg = suggester._client().data["smart_suggestions"][0]
        assert sg["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_list_pending(self, suggester, user_id):
        from services.platform.notification_suggester import SmartSuggestion

        await suggester.save_suggestions(user_id, [
            SmartSuggestion(type="frequency_change", description="x",
                            suggestion={"category": "matching", "frequency": "weekly"})
        ])
        pending = await suggester.list_pending(user_id)
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"


# ===========================================================================
# 6. Dispatcher T2304 integration
# ===========================================================================


class _FakeProvider:
    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.calls: List[Dict[str, Any]] = []

    async def send(self, message: Any) -> Any:
        from providers.notify.base import NotifyResult

        self.calls.append({"subject": message.subject, "to": list(message.to)})
        return NotifyResult(success=True, channel=self.channel, message_id=f"id-{self.channel}")


class TestDispatcherWithPrefs:
    @pytest.mark.asyncio
    async def test_dispatch_with_prefs_skips_disabled(self, backend, prefs_service):
        from services.notify.dispatcher import NotifyDispatcher

        await prefs_service.set_prefs(
            "u1", category="ticket", priority="high", channel="dingtalk", enabled=False
        )

        log_calls: List[Dict[str, Any]] = []

        async def log_sender(**kwargs):
            log_calls.append(kwargs)

        async def decision_fn(user_id, cat, pri, ch):
            return await prefs_service.evaluate(user_id, cat, pri, ch)

        d = NotifyDispatcher(
            prefs_decision_fn=decision_fn,
            provider_factory=lambda ch: _FakeProvider(ch),
            log_sender=log_sender,
        )
        outcome = await d.dispatch_with_prefs(
            category="ticket", priority="high",
            channels=["dingtalk", "web"],
            user_id="u1", title="hi", content="body",
        )
        # dingtalk 被禁用, web 通过
        ch_results = {r.channel: r for r in outcome.results}
        assert ch_results["dingtalk"].skipped is True
        assert ch_results["dingtalk"].error == "preference_disabled"
        assert ch_results["web"].success is True
        # 写入了 2 条 log
        assert len(log_calls) == 2

    @pytest.mark.asyncio
    async def test_dispatch_with_prefs_throttle(self, backend, prefs_service):
        from services.notify.dispatcher import NotifyDispatcher

        # 5 分钟前已发过
        backend.data["notification_log"].append({
            "id": str(uuid4()),
            "user_id": "u2", "category": "matching", "priority": "high",
            "channel": "web", "throttled": False, "quiet_hours_hit": False,
            "sent_at": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
        })

        async def decision_fn(user_id, cat, pri, ch):
            return await prefs_service.evaluate(user_id, cat, pri, ch)

        d = NotifyDispatcher(
            prefs_decision_fn=decision_fn,
            provider_factory=lambda ch: _FakeProvider(ch),
        )
        outcome = await d.dispatch_with_prefs(
            category="matching", priority="high",
            channels=["web"],
            user_id="u2", title="hi", content="body",
        )
        assert outcome.results[0].skipped is True
        assert outcome.results[0].error == "throttled_5min"

    @pytest.mark.asyncio
    async def test_dispatch_with_prefs_quiet_hours(self, prefs_service):
        from services.notify.dispatcher import NotifyDispatcher

        await prefs_service.set_prefs(
            "u3", category="system", priority="medium", channel="web",
            quiet_hours_start="12:00", quiet_hours_end="14:00", enabled=True,
        )

        async def decision_fn(user_id, cat, pri, ch):
            return await prefs_service.evaluate(
                user_id, cat, pri, ch,
                now_utc=datetime(2026, 7, 12, 13, 0, tzinfo=timezone.utc),
            )

        d = NotifyDispatcher(
            prefs_decision_fn=decision_fn,
            provider_factory=lambda ch: _FakeProvider(ch),
        )
        outcome = await d.dispatch_with_prefs(
            category="system", priority="medium",
            channels=["web"],
            user_id="u3", title="hi", content="body",
        )
        assert outcome.results[0].skipped is True
        assert "quiet" in (outcome.results[0].error or "")

    @pytest.mark.asyncio
    async def test_dispatch_with_prefs_fallback_to_bool_lookup(self):
        """未注入 prefs_decision_fn 时, 降级到 preferences_lookup bool."""
        from services.notify.dispatcher import NotifyDispatcher

        async def bool_lookup(user_id, channel):
            return channel != "dingtalk"  # 钉钉关掉

        d = NotifyDispatcher(
            preferences_lookup=bool_lookup,
            provider_factory=lambda ch: _FakeProvider(ch),
        )
        outcome = await d.dispatch_with_prefs(
            category="ticket", priority="high",
            channels=["dingtalk", "web"],
            user_id="u", title="hi", content="body",
        )
        ch_results = {r.channel: r for r in outcome.results}
        assert ch_results["dingtalk"].skipped is True
        assert ch_results["dingtalk"].error == "preference_off"
        assert ch_results["web"].success is True