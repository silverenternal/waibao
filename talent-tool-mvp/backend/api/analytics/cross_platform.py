"""T1904 — 跨端日活统一统计 (Cross-platform DAU/WAU/MAU).

v4.0 共 4 个客户端：
    - webapp   : 浏览器 Web (C 端求职者 / HR)
    - minip    : 微信小程序
    - feishu   : 飞书应用
    - dingtalk : 钉钉应用

本模块负责：
    1. 接收前端埋点 ``session_start`` 事件（来自 4 端 SDK），
       写入 ``user_session_events`` 表（同 supabase）。
    2. 聚合 DAU/WAU/MAU，按端拆分 + 跨端去重用户。
    3. 计算跨端活跃矩阵（用户×端），识别多端用户占比。

设计要点：
    - 去重主键为 ``user_id`` （未登录场景下用 ``anonymous_id``）。
    - 跨端活跃用户 = 在窗口期内出现在 ≥2 个端上的 user_id 集合。
    - 全部函数为 ``async``，supabase 缺省时使用 in-memory fallback（便于测试）。
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole

logger = logging.getLogger("recruittech.api.analytics.cross_platform")

router = APIRouter()

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# v4.0 的四端。保持 OrderedDict 让序列化结果可预测。
PLATFORMS: tuple[str, ...] = ("webapp", "minip", "feishu", "dingtalk")
PLATFORM_LABELS: dict[str, str] = {
    "webapp": "Web 浏览器",
    "minip": "微信小程序",
    "feishu": "飞书应用",
    "dingtalk": "钉钉应用",
}


def _normalize_platform(value: str | None) -> str:
    """归一化端标识，未知值映射为 ``webapp``。"""
    if not value:
        return "webapp"
    v = value.strip().lower()
    if v in PLATFORMS:
        return v
    # 兼容别名
    alias = {
        "web": "webapp",
        "h5": "webapp",
        "browser": "webapp",
        "wx": "minip",
        "wechat": "minip",
        "mini_program": "minip",
        "lark": "feishu",
        "dt": "dingtalk",
    }.get(v)
    return alias or "webapp"


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass
class SessionEvent:
    """单次 session_start 事件."""

    user_id: str
    platform: str
    occurred_at: datetime
    anonymous_id: str | None = None
    app_version: str | None = None
    device_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["occurred_at"] = self.occurred_at.astimezone(timezone.utc).isoformat()
        return d


@dataclass
class PlatformActive:
    """单端活跃计数."""

    platform: str
    dau: int = 0
    wau: int = 0
    mau: int = 0


@dataclass
class CrossPlatformReport:
    """跨端统计完整报告 — 给前端 dashboard 渲染使用."""

    period_start: date
    period_end: date
    by_platform: list[PlatformActive] = field(default_factory=list)
    # 跨端去重后的独立用户数
    unified_dau: int = 0
    unified_wau: int = 0
    unified_mau: int = 0
    # 多端用户
    multi_platform_users: int = 0  # 在窗口期内跨 ≥2 个端活跃过的 user 数
    multi_platform_share: float = 0.0  # multi / unified_mau
    # 端×端重合度（jaccard 索引，存用户集合）
    overlap_matrix: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "by_platform": [
                {
                    "platform": p.platform,
                    "label": PLATFORM_LABELS.get(p.platform, p.platform),
                    "dau": p.dau,
                    "wau": p.wau,
                    "mau": p.mau,
                }
                for p in self.by_platform
            ],
            "unified": {
                "dau": self.unified_dau,
                "wau": self.unified_wau,
                "mau": self.unified_mau,
            },
            "cross_platform": {
                "multi_platform_users": self.multi_platform_users,
                "multi_platform_share": round(self.multi_platform_share, 4),
            },
            "overlap": self.overlap_matrix,
        }


# ---------------------------------------------------------------------------
# Pydantic 入参 — 供 FastAPI 路由使用
# ---------------------------------------------------------------------------


class _SessionEventIn(BaseModel):
    user_id: str | None = None
    anonymous_id: str | None = None
    platform: str
    app_version: str | None = None
    device_id: str | None = None
    occurred_at: str | None = None  # ISO8601；缺省 = 服务端时间


class _SessionEventsBody(BaseModel):
    events: list[_SessionEventIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 存储抽象（in-memory backend，可由 supabase 替换）
# ---------------------------------------------------------------------------


class _SessionStore:
    """统一的 session 事件存储抽象。

    生产:  写 supabase ``user_session_events`` 表
    测试:  内存 List
    """

    def __init__(self, supabase=None):
        self.sb = supabase
        self._mem: list[SessionEvent] = []

    async def add(self, evt: SessionEvent) -> SessionEvent:
        if self.sb is not None:
            try:
                self.sb.table("user_session_events").insert(evt.to_dict()).execute()
            except Exception as exc:  # noqa: BLE001 — 表可能不存在，降级内存
                logger.warning("supabase insert failed: %s — fallback mem", exc)
                self._mem.append(evt)
        else:
            self._mem.append(evt)
        return evt

    async def add_batch(self, events: Iterable[SessionEvent]) -> int:
        ok = 0
        for e in events:
            await self.add(e)
            ok += 1
        return ok

    async def query(
        self,
        since: datetime,
        until: datetime,
    ) -> list[SessionEvent]:
        """返回 [since, until) 之间的事件."""
        if self.sb is not None:
            try:
                resp = (
                    self.sb.table("user_session_events")
                    .select("*")
                    .gte("occurred_at", since.isoformat())
                    .lt("occurred_at", until.isoformat())
                    .execute()
                )
                rows = resp.data or []
                out: list[SessionEvent] = []
                for r in rows:
                    ts = r.get("occurred_at")
                    if isinstance(ts, str):
                        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        ts_dt = datetime.now(timezone.utc)
                    out.append(
                        SessionEvent(
                            user_id=r.get("user_id") or "",
                            platform=_normalize_platform(r.get("platform")),
                            occurred_at=ts_dt,
                            anonymous_id=r.get("anonymous_id"),
                            app_version=r.get("app_version"),
                            device_id=r.get("device_id"),
                        )
                    )
                return out
            except Exception as exc:  # noqa: BLE001
                logger.warning("supabase query failed: %s — fallback mem", exc)
        # memory fallback
        return [
            e
            for e in self._mem
            if since <= e.occurred_at < until
        ]


def _get_store() -> _SessionStore:
    try:
        sb = get_supabase_admin()
        return _SessionStore(sb)
    except Exception:  # noqa: BLE001
        return _SessionStore(supabase=None)


# Monkey-patch hook for tests: tests can set ``_TEST_STORE = _SessionStore()`` to
# avoid hitting Supabase at all.
_TEST_STORE: _SessionStore | None = None


def _resolve_store() -> _SessionStore:
    if _TEST_STORE is not None:
        return _TEST_STORE
    return _get_store()


# ---------------------------------------------------------------------------
# 核心聚合逻辑
# ---------------------------------------------------------------------------


def _bucket(
    events: list[SessionEvent],
    start: datetime,
    end: datetime,
) -> set[str]:
    """窗口期内出现过的 user_id 集合（同 anonymous 也算同一用户）。"""
    users: set[str] = set()
    for e in events:
        if start <= e.occurred_at < end:
            key = e.user_id or e.anonymous_id or ""
            if key:
                users.add(key)
    return users


def _bucket_per_platform(
    events: list[SessionEvent],
    start: datetime,
    end: datetime,
) -> dict[str, set[str]]:
    """按端拆分 user 集合."""
    by_p: dict[str, set[str]] = defaultdict(set)
    for e in events:
        if start <= e.occurred_at < end:
            key = e.user_id or e.anonymous_id or ""
            if key:
                by_p[e.platform].add(key)
    return by_p


def _dau_for(events: list[SessionEvent], day: date) -> set[str]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return _bucket(events, start, end)


def _wau_for(events: list[SessionEvent], ref_day: date) -> set[str]:
    start = datetime.combine(ref_day - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(ref_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    return _bucket(events, start, end)


def _mau_for(events: list[SessionEvent], ref_day: date) -> set[str]:
    start = datetime.combine(ref_day - timedelta(days=29), datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(ref_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    return _bucket(events, start, end)


def compute_cross_platform_report(
    events: list[SessionEvent],
    ref_day: date | None = None,
) -> CrossPlatformReport:
    """聚合 DAU/WAU/MAU + 跨端去重 + 端×端重合矩阵."""
    ref_day = ref_day or datetime.now(timezone.utc).date()
    period_start = ref_day - timedelta(days=29)

    # 单端统计 (DAU/WAU/MAU)
    by_platform: list[PlatformActive] = []
    for p in PLATFORMS:
        platform_events = [e for e in events if e.platform == p]
        dau = len(_dau_for(platform_events, ref_day))
        wau = len(_wau_for(platform_events, ref_day))
        mau = len(_mau_for(platform_events, ref_day))
        by_platform.append(PlatformActive(platform=p, dau=dau, wau=wau, mau=mau))

    # 跨端去重 — 用统一 MAU 窗口过滤事件
    mau_start = datetime.combine(ref_day - timedelta(days=29), datetime.min.time(), tzinfo=timezone.utc)
    mau_end = datetime.combine(ref_day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    mau_window_events = [
        e for e in events if mau_start <= e.occurred_at < mau_end
    ]
    mau_per_platform = _bucket_per_platform(mau_window_events, mau_start, mau_end)
    # 同时计算 DAU/WAU 全局去重
    dau_users = _dau_for(events, ref_day)
    wau_users = _wau_for(events, ref_day)
    mau_users = _mau_for(events, ref_day)

    # 跨端用户 — 在 MAU 窗口内，出现在 ≥2 个端上的 user
    user_to_platforms: dict[str, set[str]] = defaultdict(set)
    for e in mau_window_events:
        key = e.user_id or e.anonymous_id or ""
        if key:
            user_to_platforms[key].add(e.platform)
    multi_users = {u for u, ps in user_to_platforms.items() if len(ps) >= 2}
    multi_share = (len(multi_users) / len(mau_users)) if mau_users else 0.0

    # 端×端重合（绝对值，jaccard 也可派生）
    overlap: dict[str, dict[str, int]] = {}
    for p1 in PLATFORMS:
        overlap[p1] = {}
        users_p1 = mau_per_platform.get(p1, set())
        for p2 in PLATFORMS:
            users_p2 = mau_per_platform.get(p2, set())
            overlap[p1][p2] = len(users_p1 & users_p2)

    return CrossPlatformReport(
        period_start=period_start,
        period_end=ref_day,
        by_platform=by_platform,
        unified_dau=len(dau_users),
        unified_wau=len(wau_users),
        unified_mau=len(mau_users),
        multi_platform_users=len(multi_users),
        multi_platform_share=multi_share,
        overlap_matrix=overlap,
    )


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@router.post("/sessions", summary="T1904 接收 4 端 session 埋点")
async def post_sessions(
    body: _SessionEventsBody,
    user: CurrentUser = Depends(get_current_user),
):
    """接收前端 SDK 上报的 session_start 事件。

    允许匿名 ``anonymous_id``，服务端会在内存表中保留。
    """
    store = _resolve_store()
    now = datetime.now(timezone.utc)
    written = 0
    for e in body.events:
        try:
            ts = (
                datetime.fromisoformat(e.occurred_at.replace("Z", "+00:00"))
                if e.occurred_at
                else now
            )
        except Exception:
            ts = now
        evt = SessionEvent(
            user_id=e.user_id or str(user.id) if user and getattr(user, "id", None) else (e.user_id or ""),
            platform=_normalize_platform(e.platform),
            occurred_at=ts,
            anonymous_id=e.anonymous_id or str(uuid.uuid4()),
            app_version=e.app_version,
            device_id=e.device_id,
        )
        await store.add(evt)
        written += 1
    return {"ok": written, "total": len(body.events)}


@router.get("/cross-platform/summary", summary="T1904 跨端日活报表")
async def get_cross_platform_summary(
    days: int = Query(default=1, ge=1, le=30, description="DAU 范围取最后 N 天（这里主要返回 ref_day 当天 + MAU 30 天汇总）"),
    ref_date: str | None = Query(default=None, description="参考日期 YYYY-MM-DD，默认今天"),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """返回 dashboard 所需的全量结构化数据.

    仅 admin 可访问，避免泄漏活跃用户规模。
    """
    store = _resolve_store()

    ref: date
    if ref_date:
        try:
            ref = date.fromisoformat(ref_date)
        except ValueError as exc:
            return {"error": f"ref_date 格式错误: {exc}"}
    else:
        ref = datetime.now(timezone.utc).date()

    # 拉窗口数据（MAU 30 天覆盖所有日活范围）
    window_end = datetime.combine(ref, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    window_start = window_end - timedelta(days=30)
    events = await store.query(window_start, window_end)
    report = compute_cross_platform_report(events, ref_day=ref)
    return report.to_dict()


@router.get("/cross-platform/dau", summary="T1904 DAU 按端拆分（最近 N 天）")
async def get_dau_series(
    days: int = Query(default=7, ge=1, le=30),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    store = _resolve_store()
    today = datetime.now(timezone.utc).date()
    window_start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    window_end = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    events = await store.query(window_start, window_end)

    series: list[dict[str, Any]] = []
    for offset in range(days):
        day = today - timedelta(days=days - 1 - offset)
        per_day: dict[str, int] = {}
        unified = 0
        all_users: set[str] = set()
        for p in PLATFORMS:
            users = _dau_for([e for e in events if e.platform == p], day)
            per_day[p] = len(users)
            all_users |= users
        unified = len(all_users)
        series.append({"date": day.isoformat(), "by_platform": per_day, "unified": unified})
    return {"days": days, "series": series}


# ---------------------------------------------------------------------------
# 内部工具 — 便于测试导入
# ---------------------------------------------------------------------------


__all__ = [
    "router",
    "PLATFORMS",
    "PLATFORM_LABELS",
    "SessionEvent",
    "PlatformActive",
    "CrossPlatformReport",
    "_SessionStore",
    "compute_cross_platform_report",
    "_normalize_platform",
    "_bucket",
    "_bucket_per_platform",
    "_dau_for",
    "_wau_for",
    "_mau_for",
]
