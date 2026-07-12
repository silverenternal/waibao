"""VideoInterview 集成测试 (T1305)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class _TableRow:
    """极简 supabase 链式 stub."""

    def __init__(self, name: str, store: dict | None = None) -> None:
        self.name = name
        self.store = store if store is not None else {}
        self.filters: list[tuple[str, object]] = []
        self._op = "select"
        self._value: object | None = None
        self._order: tuple[str, bool] | None = None
        self._limit_n: int | None = None
        self._single = False

    def insert(self, value):
        self._op = "insert"
        self._value = value
        return self

    def update(self, value):
        self._op = "update"
        self._value = value
        return self

    def select(self, *_):
        self._op = "select"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows: list = []
        if self._op == "insert":
            v = self._value
            if isinstance(v, dict):
                import uuid as _u
                if not v.get("id"):
                    v = {**v, "id": str(_u.uuid4())}
            # 实际写入 store 让后续 select 能拿到
            if isinstance(v, dict) and v.get("id") is not None:
                self.store[v["id"]] = v
            rows = [v] if v is not None else []
        elif self._op == "select":
            data = list(self.store.values())
            for col, val in self.filters:
                data = [r for r in data if r.get(col) == val]
            if self._single:
                rows = data[0] if data else None
                return SimpleNamespace(data=rows)
            if self._order:
                col, desc = self._order
                data.sort(key=lambda r: r.get(col) or "", reverse=desc)
            if self._limit_n is not None:
                data = data[: self._limit_n]
            rows = data
        elif self._op == "update":
            rows = []
            for col, val in self.filters:
                for k, r in list(self.store.items()):
                    if r.get(col) == val:
                        self.store[k] = {**r, **(self._value or {})}
                        rows.append(self.store[k])
        return SimpleNamespace(data=rows)


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, dict] = {}
        for t in ("video_interviews", "video_webhooks", "uploads"):
            self.tables[t] = {}

    def table(self, name: str) -> _TableRow:
        return _TableRow(name, self.tables.setdefault(name, {}))


class _Resp:
    """httpx Response stub. text 默认为 JSON 字符串,确保 _request 拿到 body."""

    def __init__(self, status, body, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        return self._body


def _make_resp(status, body):
    """提供默认 text = body 的 JSON 字符串."""
    import json as _json
    return _Resp(status, body, _json.dumps(body))


@pytest.fixture()
def sb():
    return _FakeSupabase()


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_provider_full_flow():
    from providers.video_interview.mock import MockVideoInterviewProvider

    p = MockVideoInterviewProvider()
    meeting = await p.create_meeting(
        topic="Interview",
        start_time=datetime.now(timezone.utc),
        duration_min=30,
        participants=[
            SimpleNamespace(email="a@x.com", name="A", role="host", user_id="u1"),
            SimpleNamespace(
                email="cand@x.com", name="C", role="attendee", user_id="u2"
            ),
        ],
    )
    assert meeting.meeting_id.startswith("mtg_mock_")
    assert meeting.join_url.startswith("https://mock-video.local/j/")

    rec = await p.get_recording(meeting.meeting_id)
    assert rec.status == "processing"

    # 第二轮: 直接覆盖 record dict (slots 限制 metadata 不能并入)
    p._recordings[meeting.meeting_id] = _make_data_recording(
        meeting.meeting_id, 900
    )
    again = await p.get_recording(meeting.meeting_id)
    assert again.status == "available"
    assert again.duration_seconds == 900

    await p.cancel_meeting(meeting.meeting_id)


def _make_data_recording(meeting_id, seconds):
    """构造一个 available Recording (用于 mock provider 的内部 dict 写入)."""
    from providers.video_interview.types import Recording
    import secrets
    return Recording(
        recording_id=f"rec_mock_{secrets.token_hex(6)}",
        meeting_id=meeting_id,
        status="available",
        download_url=f"https://mock-video.local/rec/{meeting_id}.mp4",
        play_url=f"https://mock-video.local/play/{meeting_id}",
        duration_seconds=seconds,
    )


# ---------------------------------------------------------------------------
# Zoom provider
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_zoom_create_meeting_fallback(monkeypatch):
    from providers.video_interview import zoom as zoom_mod
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    provider = zoom_mod.ZoomProvider()
    assert provider._configured() is False
    # 业务层会捕获 UpstreamUnavailableError → 切 mock
    with pytest.raises(Exception):
        await provider.create_meeting(
            topic="t",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[
                SimpleNamespace(email="a@x.com", name="A", role="host"),
            ],
        )


@pytest.mark.asyncio
async def test_zoom_create_meeting_success(monkeypatch):
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cli")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec")

    from providers.video_interview import zoom as zoom_mod

    class _ZoomClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return _make_resp(200, {"access_token": "tok", "expires_in": 3600})

        async def request(self, method, url, **kwargs):
            return _make_resp(
                201,
                {
                    "id": 1234567890,
                    "join_url": "https://zoom.us/j/123",
                    "password": "p@ss",
                    "uuid": "abc-uuid",
                    "host_id": "hid",
                    "topic": "t",
                },
            )

    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", _ZoomClient)

    p = zoom_mod.ZoomProvider()
    out = await p.create_meeting(
        topic="Eng Screen",
        start_time=datetime.now(timezone.utc) + timedelta(hours=1),
        duration_min=45,
        participants=[
            SimpleNamespace(email="a@x.com", name="A", role="host"),
            SimpleNamespace(email="c@x.com", name="C", role="attendee"),
        ],
    )
    assert out.meeting_id == "1234567890"
    assert out.join_url == "https://zoom.us/j/123"
    assert out.provider == "zoom"


@pytest.mark.asyncio
async def test_zoom_get_recording_parses_files(monkeypatch):
    from providers.video_interview import zoom as zoom_mod

    class _ZoomClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return _make_resp(200, {"access_token": "tok", "expires_in": 3600})

        async def request(self, method, url, **kwargs):
            return _make_resp(
                200,
                {
                    "uuid": "rec-uuid",
                    "host_id": "h",
                    "account_id": "a",
                    "start_time": "2026-07-12T10:00:00Z",
                    "recording_files": [
                        {
                            "file_type": "MP4",
                            "download_url": "https://zoom.us/rec/mp4",
                            "play_url": "https://zoom.us/rec/play",
                            "duration": 1800000,
                        },
                    ],
                },
            )

    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "a")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "c")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "s")
    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", _ZoomClient)

    p = zoom_mod.ZoomProvider()
    rec = await p.get_recording("9999")
    assert rec.status == "available"
    assert rec.download_url == "https://zoom.us/rec/mp4"
    assert rec.duration_seconds == 1800


@pytest.mark.asyncio
async def test_zoom_get_recording_404(monkeypatch):
    from providers.video_interview import zoom as zoom_mod

    class _ZoomClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return _make_resp(200, {"access_token": "tok", "expires_in": 3600})

        async def request(self, method, url, **kwargs):
            # 模拟 Zoom 404
            return _Resp(404, None, text="")

    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "a")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "c")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "s")
    monkeypatch.setattr(zoom_mod.httpx, "AsyncClient", _ZoomClient)

    p = zoom_mod.ZoomProvider()
    rec = await p.get_recording("nope")
    assert rec.status == "processing"


# ---------------------------------------------------------------------------
# Tencent provider
# ---------------------------------------------------------------------------
class _TmClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kwargs):
        if url.endswith("/v1/oauth/token"):
            return _make_resp(
                200,
                {
                    "access_token": "tmtok",
                    "expires_in": 7200,
                    "error_code": 0,
                },
            )
        # /v1/meetings (POST via OAuth path; _request uses request() not post)
        return _make_resp(
            200,
            {
                "error_code": 0,
                "meeting_id": "TM-MEET-001",
                "meeting_number": "123456789",
                "join_url": "https://meeting.tencent.com/j/TM-001",
                "host_url": "https://meeting.tencent.com/h/TM-001",
                "password": "tm",
                "userid": "u1",
            },
        )

    async def request(self, method, url, **kwargs):
        if method == "DELETE":
            return _make_resp(200, {"error_code": 0})
        if "/meetings" in url:
            return _make_resp(
                200,
                {
                    "error_code": 0,
                    "meeting_id": "TM-MEET-001",
                    "meeting_number": "123456789",
                    "join_url": "https://meeting.tencent.com/j/TM-001",
                    "host_url": "https://meeting.tencent.com/h/TM-001",
                    "password": "tm",
                    "userid": "u1",
                },
            )
        # /v1/records
        return _make_resp(
            200,
            {
                "error_code": 0,
                "record_meeting": [
                    {
                        "record_id": "rec-tm-1",
                        "download_url": "https://meeting.tencent.com/rec/1.mp4",
                        "play_url": "https://meeting.tencent.com/rec/1",
                        "duration": 900,
                    },
                ],
            },
        )


@pytest.mark.asyncio
async def test_tencent_create_meeting(monkeypatch):
    from providers.video_interview import tencent_meeting as tm_mod

    monkeypatch.setenv("TENCENT_MEETING_APP_ID", "appid")
    monkeypatch.setenv("TENCENT_MEETING_APP_SECRET", "secret")
    monkeypatch.setattr(tm_mod.httpx, "AsyncClient", _TmClient)

    p = tm_mod.TencentMeetingProvider()
    out = await p.create_meeting(
        topic="Eng Interview",
        start_time=datetime.now(timezone.utc) + timedelta(hours=2),
        duration_min=30,
        participants=[
            SimpleNamespace(email="a@x.com", name="A", role="host"),
            SimpleNamespace(email="b@x.com", name="B", role="attendee"),
        ],
    )
    assert out.meeting_id == "TM-MEET-001"
    assert out.join_url.startswith("https://meeting.tencent.com/")
    assert out.provider == "tencent_meeting"


@pytest.mark.asyncio
async def test_tencent_get_recording(monkeypatch):
    from providers.video_interview import tencent_meeting as tm_mod

    monkeypatch.setenv("TENCENT_MEETING_APP_ID", "app")
    monkeypatch.setenv("TENCENT_MEETING_APP_SECRET", "sec")
    monkeypatch.setattr(tm_mod.httpx, "AsyncClient", _TmClient)
    p = tm_mod.TencentMeetingProvider()
    rec = await p.get_recording("TM-MEET-001")
    assert rec.status == "available"
    assert rec.duration_seconds == 900


@pytest.mark.asyncio
async def test_tencent_get_recording_empty(monkeypatch):
    """空数据 → processing 状态,不抛错."""
    from providers.video_interview import tencent_meeting as tm_mod

    class _EmptyClient(_TmClient):
        async def request(self, method, url, **kwargs):
            return _make_resp(404, {"error_code": 404, "error_msg": "missing"})

    monkeypatch.setenv("TENCENT_MEETING_APP_ID", "app")
    monkeypatch.setenv("TENCENT_MEETING_APP_SECRET", "sec")
    monkeypatch.setattr(tm_mod.httpx, "AsyncClient", _EmptyClient)
    p = tm_mod.TencentMeetingProvider()
    rec = await p.get_recording("nope")
    assert rec.status == "processing"


@pytest.mark.asyncio
async def test_tencent_unconfigured(monkeypatch):
    from providers.video_interview import tencent_meeting as tm_mod
    monkeypatch.delenv("TENCENT_MEETING_APP_ID", raising=False)
    monkeypatch.delenv("TENCENT_MEETING_APP_SECRET", raising=False)
    p = tm_mod.TencentMeetingProvider()
    assert p._configured() is False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
def _schedule(svc, preferred="mock"):
    """便捷构造:schedule 一个 mock interview."""
    from uuid import uuid4
    return svc.schedule_interview(
        ticket_id=None,
        match_id=None,
        candidate_id=uuid4(),
        employer_id=uuid4(),
        host_email="host@x.com",
        topic="Schedule Test",
        start_time=datetime.now(timezone.utc) + timedelta(hours=1),
        duration_min=30,
        participant_emails=["cand@x.com"],
        preferred_provider=preferred,
    )


@pytest.mark.asyncio
async def test_service_schedule_with_mock(sb):
    from services.video_interview_service import VideoInterviewService

    svc = VideoInterviewService(supabase=sb)
    row = await _schedule(svc)
    assert row["provider"] == "mock_video"
    assert row["status"] == "scheduled"


@pytest.mark.asyncio
async def test_service_real_provider_falls_back(sb, monkeypatch):
    """真实 provider 失败 → service 自动 fallback mock,不抛错."""
    from services.video_interview_service import VideoInterviewService
    from providers.video_interview import zoom as zoom_mod

    monkeypatch.setenv("VIDEO_PROVIDER", "zoom")
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "a")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "c")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "s")

    async def boom(*a, **k):
        raise zoom_mod.UpstreamUnavailableError("net boom", provider="zoom")

    monkeypatch.setattr(zoom_mod.ZoomProvider, "create_meeting", boom)

    from providers.video_interview.registry import reset_cache
    reset_cache()

    svc = VideoInterviewService(supabase=sb)
    row = await _schedule(svc, preferred="zoom")
    # fallback 到 mock_video
    assert row["provider"] == "mock_video"


@pytest.mark.asyncio
async def test_service_calendar_sync_disabled(sb):
    from services.video_interview_service import VideoInterviewService

    os.environ.pop("GOOGLE_CALENDAR_ENABLED", None)
    os.environ.pop("OUTLOOK_CALENDAR_ENABLED", None)

    svc = VideoInterviewService(supabase=sb)
    row = await svc.schedule_interview(
        ticket_id=None,
        match_id=None,
        candidate_id=__import__("uuid").uuid4(),
        employer_id=__import__("uuid").uuid4(),
        host_email="h@x.com",
        topic="Cal Test",
        start_time=datetime.now(timezone.utc) + timedelta(hours=1),
        duration_min=30,
        participant_emails=[],
        preferred_provider="mock",
        calendar_tokens={"google": "tok-xxx"},
    )
    assert row["provider"] == "mock_video"


@pytest.mark.asyncio
async def test_service_cancel(sb):
    from services.video_interview_service import VideoInterviewService
    from uuid import UUID

    svc = VideoInterviewService(supabase=sb)
    row = await _schedule(svc)
    out = await svc.cancel_interview(UUID(row["id"]))
    assert out["status"] == "canceled"


@pytest.mark.asyncio
async def test_service_webhook(sb):
    from services.video_interview_service import VideoInterviewService

    svc = VideoInterviewService(supabase=sb)
    row = await _schedule(svc)
    ok = await svc.handle_webhook(
        provider="mock",
        event_type="meeting.ended",
        meeting_id=row["meeting_id"],
        payload={"foo": "bar"},
    )
    assert ok is True
    res = sb.table("video_interviews").select("*").eq("id", row["id"]).execute()
    assert res.data[0]["status"] == "ended"


@pytest.mark.asyncio
async def test_service_recording_bridge(sb):
    """get_recording 桥接到 uploads 表."""
    from services.video_interview_service import VideoInterviewService
    from uuid import UUID

    svc = VideoInterviewService(supabase=sb)
    row = await _schedule(svc)

    # 把这个 meeting 的 recording 标记为 available (走 service 共用 mock)
    svc._mock._recordings[row["meeting_id"]] = _make_data_recording(
        row["meeting_id"], 1234
    )

    data = await svc.get_recording(UUID(row["id"]))
    assert data["status"] == "available"
    assert data["duration_seconds"] == 1234
    up = sb.table("uploads").select("*").execute()
    assert len(up.data) == 1
    assert up.data[0]["kind"] == "video_recording"


@pytest.mark.asyncio
async def test_service_webhook_unknown_meeting(sb):
    from services.video_interview_service import VideoInterviewService
    svc = VideoInterviewService(supabase=sb)
    ok = await svc.handle_webhook(
        provider="zoom",
        event_type="meeting.started",
        meeting_id="unknown-meeting",
        payload={},
    )
    assert ok is False


# ---------------------------------------------------------------------------
# Calendar sync
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_sync_disabled_google():
    from services.calendar_sync import CalendarSyncService, CalendarEvent

    os.environ.pop("GOOGLE_CALENDAR_ENABLED", None)
    svc = CalendarSyncService()
    res = await svc.create_event(
        "google",
        access_token="any",
        event=CalendarEvent(
            event_id=None, title="t", description="d",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(minutes=30),
        ),
    )
    assert res.ok is False
    assert "GOOGLE_CALENDAR_ENABLED" in (res.error or "")


@pytest.mark.asyncio
async def test_calendar_sync_outlook_create(monkeypatch):
    import services.employer.calendar_sync as cs

    monkeypatch.setenv("OUTLOOK_CALENDAR_ENABLED", "1")

    class _OClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            return _make_resp(201, {"id": "out-123"})

        async def get(self, url, **kw):
            return _make_resp(200, {"value": []})

        async def delete(self, url, **kw):
            return _Resp(204, {}, text="")

    monkeypatch.setattr(cs.httpx, "AsyncClient", _OClient)

    svc = cs.CalendarSyncService()
    res = await svc.create_event(
        "outlook",
        access_token="tok",
        event=cs.CalendarEvent(
            event_id=None, title="OT", description="",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(minutes=30),
        ),
    )
    assert res.ok is True
    assert res.event_id == "out-123"


@pytest.mark.asyncio
async def test_calendar_sync_unsupported_provider():
    from services.calendar_sync import CalendarSyncService, CalendarEvent
    svc = CalendarSyncService()
    res = await svc.create_event(
        "yahoo",
        access_token=None,
        event=CalendarEvent(
            event_id=None, title="", description="",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        ),
    )
    assert res.ok is False
    assert "unsupported" in (res.error or "")


# ---------------------------------------------------------------------------
# Registry & API router
# ---------------------------------------------------------------------------
def test_video_registry_mock_default(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER", raising=False)
    from providers.video_interview.registry import (
        get_video_interview_provider,
        reset_cache,
    )
    reset_cache()
    p = get_video_interview_provider()
    assert p.provider_name == "mock_video"


def test_video_registry_zoom_missing_creds(monkeypatch):
    from providers.video_interview.registry import (
        get_video_interview_provider,
        reset_cache,
    )
    monkeypatch.setenv("VIDEO_PROVIDER", "zoom")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    reset_cache()
    p = get_video_interview_provider()
    # 凭证缺失 → fallback mock
    assert p.provider_name == "mock_video"


def test_video_registry_tencent_missing_creds(monkeypatch):
    from providers.video_interview.registry import (
        get_video_interview_provider,
        reset_cache,
    )
    monkeypatch.setenv("VIDEO_PROVIDER", "tencent_meeting")
    monkeypatch.delenv("TENCENT_MEETING_APP_ID", raising=False)
    monkeypatch.delenv("TENCENT_MEETING_APP_SECRET", raising=False)
    reset_cache()
    p = get_video_interview_provider()
    assert p.provider_name == "mock_video"


def test_video_registry_real_zoom(monkeypatch):
    from providers.video_interview.registry import (
        get_video_interview_provider,
        reset_cache,
    )
    monkeypatch.setenv("VIDEO_PROVIDER", "zoom")
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "a")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "c")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "s")
    reset_cache()
    p = get_video_interview_provider()
    assert p.provider_name == "zoom"


def test_api_router_endpoints_present():
    from api.video_interview import router
    methods = sorted(
        f"{list(getattr(r, 'methods', set()))[0]} {r.path}"
        for r in router.routes
        if hasattr(r, "methods") and getattr(r, "methods", None)
    )
    assert any("POST /api/video-interviews" in m for m in methods)
    assert any(
        "DELETE /api/video-interviews/{video_interview_id}" in m
        for m in methods
    )
    assert any(
        "GET /api/video-interviews/{video_interview_id}/recording" in m
        for m in methods
    )
    assert any("GET /api/video-interviews" in m for m in methods)
    assert any(
        "POST /api/video-interviews/webhooks/{provider}" in m for m in methods
    )
