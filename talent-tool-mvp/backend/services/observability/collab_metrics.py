"""T1808 — Collaboration Room 指标采集.

跟踪:
  - 活跃房间数 (按 type / org 维度)
  - 消息吞吐 (msg/min)
  - 未读数中位数 / P95
  - mention 触发率
  - 反应 (reaction) 速率
  - 房间成员平均数
  - Latency: list_messages / post_message / mark_read

数据源: in-memory 累计 + 滑动窗口 (60s / 5min / 1h).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Bucket:
    """滑动窗口计数器."""

    window_seconds: int
    timestamps: deque[float] = field(default_factory=deque)

    def add(self, ts: float | None = None) -> None:
        now = ts if ts is not None else time.time()
        self.timestamps.append(now)
        cutoff = now - self.window_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def rate_per_second(self) -> float:
        if not self.timestamps:
            return 0.0
        return len(self.timestamps) / self.window_seconds


@dataclass(slots=True)
class _LatencyRecorder:
    """单 op 的延迟分布."""

    samples: deque[float] = field(default_factory=lambda: deque(maxlen=10000))

    def observe(self, ms: float) -> None:
        self.samples.append(ms)

    def summary(self) -> dict[str, float]:
        if not self.samples:
            return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
        sorted_samples = sorted(self.samples)
        n = len(sorted_samples)
        p50 = sorted_samples[int(n * 0.5)]
        p95 = sorted_samples[min(int(n * 0.95), n - 1)]
        p99 = sorted_samples[min(int(n * 0.99), n - 1)]
        mean = sum(sorted_samples) / n
        return {
            "n": n,
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "mean": round(mean, 2),
            "max": round(max(sorted_samples), 2),
        }


class CollabMetrics:
    """协同房间全局指标采集器."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 房间级: org_id / type / archived
        self._active_rooms: set[str] = set()
        self._rooms_by_org: dict[str, set[str]] = defaultdict(set)
        self._rooms_by_type: dict[str, set[str]] = defaultdict(set)
        self._room_members: dict[str, int] = {}
        # 计数
        self._messages_posted = _Bucket(window_seconds=60)
        self._messages_posted_5m = _Bucket(window_seconds=300)
        self._messages_posted_1h = _Bucket(window_seconds=3600)
        self._mentions_total = 0
        self._reactions_total = 0
        self._reads_total = 0
        # 未读 (每次 mark_read 收集 last_unread_count)
        self._unread_samples: deque[int] = deque(maxlen=10000)
        # 延迟
        self._latency_post_message = _LatencyRecorder()
        self._latency_list_messages = _LatencyRecorder()
        self._latency_mark_read = _LatencyRecorder()
        self._latency_search_messages = _LatencyRecorder()
        # 错误
        self._errors_total = 0

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def room_created(self, room_id: str, org_id: str | None, type_: str) -> None:
        with self._lock:
            self._active_rooms.add(room_id)
            if org_id:
                self._rooms_by_org[org_id].add(room_id)
            self._rooms_by_type[type_].add(room_id)
            self._room_members[room_id] = 1

    def room_archived(self, room_id: str) -> None:
        with self._lock:
            self._active_rooms.discard(room_id)
            for s in self._rooms_by_org.values():
                s.discard(room_id)
            for s in self._rooms_by_type.values():
                s.discard(room_id)
            self._room_members.pop(room_id, None)

    def member_added(self, room_id: str) -> None:
        with self._lock:
            self._room_members[room_id] = self._room_members.get(room_id, 0) + 1

    def member_removed(self, room_id: str) -> None:
        with self._lock:
            cur = self._room_members.get(room_id, 0)
            if cur > 0:
                self._room_members[room_id] = cur - 1

    def message_posted(self, *, mentions: int, latency_ms: float) -> None:
        with self._lock:
            now = time.time()
            self._messages_posted.add(now)
            self._messages_posted_5m.add(now)
            self._messages_posted_1h.add(now)
            self._mentions_total += mentions
            self._latency_post_message.observe(latency_ms)

    def reaction_added(self) -> None:
        with self._lock:
            self._reactions_total += 1

    def mark_read(self, *, unread_count_at_call: int, latency_ms: float) -> None:
        with self._lock:
            self._reads_total += 1
            self._unread_samples.append(unread_count_at_call)
            self._latency_mark_read.observe(latency_ms)

    def list_messages_called(self, *, latency_ms: float) -> None:
        with self._lock:
            self._latency_list_messages.observe(latency_ms)

    def search_messages_called(self, *, latency_ms: float) -> None:
        with self._lock:
            self._latency_search_messages.observe(latency_ms)

    def error(self) -> None:
        with self._lock:
            self._errors_total += 1

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------
    def _percentile(self, samples: deque[int], q: float) -> int:
        if not samples:
            return 0
        sorted_s = sorted(samples)
        idx = min(int(len(sorted_s) * q), len(sorted_s) - 1)
        return int(sorted_s[idx])

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_rooms": len(self._active_rooms),
                "rooms_by_type": {k: len(v) for k, v in self._rooms_by_type.items()},
                "rooms_by_org": {k: len(v) for k, v in self._rooms_by_org.items()},
                "avg_members_per_room": (
                    round(sum(self._room_members.values()) / max(len(self._active_rooms), 1), 2)
                ),
                "messages_per_min": round(self._messages_posted.rate_per_second() * 60, 2),
                "messages_per_5min": round(self._messages_posted_5m.rate_per_second() * 300, 2),
                "messages_per_hour": round(self._messages_posted_1h.rate_per_second() * 3600, 2),
                "mentions_total": self._mentions_total,
                "reactions_total": self._reactions_total,
                "reads_total": self._reads_total,
                "unread": {
                    "samples": len(self._unread_samples),
                    "p50": self._percentile(self._unread_samples, 0.50),
                    "p95": self._percentile(self._unread_samples, 0.95),
                    "p99": self._percentile(self._unread_samples, 0.99),
                    "max": max(self._unread_samples) if self._unread_samples else 0,
                },
                "latency_ms": {
                    "post_message": self._latency_post_message.summary(),
                    "list_messages": self._latency_list_messages.summary(),
                    "mark_read": self._latency_mark_read.summary(),
                    "search_messages": self._latency_search_messages.summary(),
                },
                "errors_total": self._errors_total,
                "sampled_at": datetime.now(timezone.utc).isoformat(),
            }

    def reset(self) -> None:
        with self._lock:
            self._active_rooms.clear()
            self._rooms_by_org.clear()
            self._rooms_by_type.clear()
            self._room_members.clear()
            self._messages_posted = _Bucket(window_seconds=60)
            self._messages_posted_5m = _Bucket(window_seconds=300)
            self._messages_posted_1h = _Bucket(window_seconds=3600)
            self._mentions_total = 0
            self._reactions_total = 0
            self._reads_total = 0
            self._unread_samples.clear()
            self._latency_post_message = _LatencyRecorder()
            self._latency_list_messages = _LatencyRecorder()
            self._latency_mark_read = _LatencyRecorder()
            self._latency_search_messages = _LatencyRecorder()
            self._errors_total = 0


_GLOBAL = CollabMetrics()


def get_collab_metrics() -> CollabMetrics:
    return _GLOBAL


def report() -> dict[str, Any]:
    return _GLOBAL.report()


# ---------------------------------------------------------------------------
# Context manager / decorator: 自动记录 latency
# ---------------------------------------------------------------------------
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def track_post_message(*, mentions: int) -> Iterator[None]:
    """post_message 的延迟跟踪 context manager.

    用法:
        with track_post_message(mentions=len(mentions)) as t:
            ... do work ...
    """
    start = time.perf_counter()
    try:
        yield
    except Exception:
        _GLOBAL.error()
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        _GLOBAL.message_posted(mentions=mentions, latency_ms=latency_ms)


@contextmanager
def track_list_messages() -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    except Exception:
        _GLOBAL.error()
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        _GLOBAL.list_messages_called(latency_ms=latency_ms)


@contextmanager
def track_mark_read(unread_count: int) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    except Exception:
        _GLOBAL.error()
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        _GLOBAL.mark_read(unread_count_at_call=unread_count, latency_ms=latency_ms)


@contextmanager
def track_search_messages() -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    except Exception:
        _GLOBAL.error()
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        _GLOBAL.search_messages_called(latency_ms=latency_ms)


__all__ = [
    "CollabMetrics",
    "get_collab_metrics",
    "report",
    "track_post_message",
    "track_list_messages",
    "track_mark_read",
    "track_search_messages",
]


if __name__ == "__main__":
    import json
    m = CollabMetrics()
    for i in range(100):
        m.room_created(f"r-{i}", f"org-{i % 5}", "group" if i % 2 == 0 else "direct")
        m.member_added(f"r-{i}")
        if i % 3 == 0:
            m.member_added(f"r-{i}")
    for i in range(500):
        m.message_posted(mentions=i % 3, latency_ms=10 + (i % 50))
    for i in range(200):
        m.reaction_added()
    for i in range(150):
        m.mark_read(unread_count_at_call=i % 10, latency_ms=5 + (i % 20))
    print(json.dumps(m.report(), indent=2))