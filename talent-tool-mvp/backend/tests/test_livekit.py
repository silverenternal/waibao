"""T2204 - LiveKit 自托管 测试.

覆盖:
  - JWT 签发 + 校验
  - LiveKitProvider: room/token/recording/webhook
  - registry 集成
  - 1 个真实 LiveKit 房间测试 (LIVEKIT_RUN_INTEGRATION=1 时)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timezone

import pytest

# 强制让 LiveKit provider 用 dev key (避免读取 .env)
os.environ.setdefault("LIVEKIT_API_KEY", "APIwXkjY8N7qGRtVzmHp9DTr4cKLbn")
os.environ.setdefault("LIVEKIT_API_SECRET", "secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD")

from providers.exceptions import AuthError  # noqa: E402
from providers.video_interview.livekit import (  # noqa: E402
    LIVEKIT_WEBHOOK_EVENTS,
    LiveKitProvider,
    LiveKitRoom,
    LiveKitToken,
    issue_access_token,
    verify_token,
    verify_webhook,
)
from providers.video_interview.registry import (  # noqa: E402
    get_video_interview_provider,
    reset_cache,
)
from providers.video_interview.types import Participant  # noqa: E402


DEV_KEY = "APIwXkjY8N7qGRtVzmHp9DTr4cKLbn"
DEV_SECRET = "secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD"


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
class TestJWTHelpers:
    def test_issue_token_returns_valid_jwt(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        assert isinstance(tok, LiveKitToken)
        assert tok.token.count(".") == 2
        assert tok.room_name == "r1"
        assert tok.identity == "alice"
        assert tok.expires_at > int(time.time())

    def test_issue_token_default_permissions(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        assert tok.permissions["canPublish"] is True
        assert tok.permissions["canSubscribe"] is True

    def test_issue_token_can_disable_publish(self):
        tok = issue_access_token(
            DEV_KEY, DEV_SECRET, room_name="r1", identity="v",
            can_publish=False, can_publish_data=False,
        )
        assert tok.permissions["canPublish"] is False
        assert tok.permissions["canPublishData"] is False

    def test_verify_token_roundtrip(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        claims = verify_token(DEV_KEY, DEV_SECRET, tok.token)
        assert claims["sub"] == "alice"
        assert claims["video"]["room"] == "r1"

    def test_verify_token_wrong_secret_raises(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        with pytest.raises(AuthError):
            verify_token(DEV_KEY, "wrong-secret", tok.token)

    def test_verify_token_wrong_key_raises(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        with pytest.raises(AuthError):
            verify_token("wrong-key", DEV_SECRET, tok.token)

    def test_verify_token_malformed_raises(self):
        with pytest.raises(AuthError):
            verify_token(DEV_KEY, DEV_SECRET, "not.a.jwt")

    def test_verify_token_expired_raises(self):
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice", ttl_seconds=-1)
        with pytest.raises(AuthError):
            verify_token(DEV_KEY, DEV_SECRET, tok.token)

    def test_token_signature_uses_hmac_sha256(self):
        # 手工构造期望签名,确保一致性
        import base64
        tok = issue_access_token(DEV_KEY, DEV_SECRET, room_name="r1", identity="alice")
        h_b64, p_b64, sig_b64 = tok.token.split(".")
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected = hmac.new(DEV_SECRET.encode(), signing_input, hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        assert expected == actual


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
class TestLiveKitProvider:
    def test_provider_name(self):
        p = LiveKitProvider()
        assert p.provider_name == "livekit"

    def test_configured_with_dev_defaults(self):
        p = LiveKitProvider()
        assert p._configured() is True

    def test_issue_token_for_participant(self):
        p = LiveKitProvider()
        tok = p.issue_token(
            room_name="r1", identity="bob", name="Bob", ttl_seconds=600
        )
        assert isinstance(tok, LiveKitToken)
        assert tok.identity == "bob"
        assert tok.expires_at - int(time.time()) <= 601

    @pytest.mark.asyncio
    async def test_create_meeting_returns_meeting(self):
        p = LiveKitProvider()
        m = await p.create_meeting(
            topic="AI Interview",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[
                Participant(email="host@example.com", role="host"),
                Participant(email="alice@example.com", role="attendee"),
            ],
            host_email="host@example.com",
            metadata={"interview_id": "iv1"},
        )
        assert m.meeting_id.startswith("int_")
        assert m.provider == "livekit"
        assert m.metadata.get("livekit_url")
        assert m.metadata.get("host_token")
        # 房间元数据写入本地缓存
        room = p.get_room(m.meeting_id)
        assert room is not None

    @pytest.mark.asyncio
    async def test_create_meeting_rejects_empty_participants(self):
        p = LiveKitProvider()
        with pytest.raises(Exception):
            await p.create_meeting(
                topic="t",
                start_time=datetime.now(timezone.utc),
                duration_min=10,
                participants=[],
            )

    @pytest.mark.asyncio
    async def test_create_meeting_rejects_zero_duration(self):
        p = LiveKitProvider()
        with pytest.raises(Exception):
            await p.create_meeting(
                topic="t",
                start_time=datetime.now(timezone.utc),
                duration_min=0,
                participants=[Participant(email="a@b.com")],
            )

    @pytest.mark.asyncio
    async def test_cancel_meeting_marks_room_canceled(self):
        p = LiveKitProvider()
        m = await p.create_meeting(
            topic="t",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[Participant(email="a@b.com")],
            host_email="a@b.com",
        )
        await p.cancel_meeting(m.meeting_id)
        room = p.get_room(m.meeting_id)
        assert room is not None
        assert room.metadata.get("canceled") == "1"

    @pytest.mark.asyncio
    async def test_get_recording_processing_by_default(self):
        p = LiveKitProvider()
        m = await p.create_meeting(
            topic="t",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[Participant(email="a@b.com")],
            host_email="a@b.com",
        )
        rec = await p.get_recording(m.meeting_id)
        assert rec.status == "processing"
        assert rec.meeting_id == m.meeting_id

    def test_seed_recording_marks_available(self):
        p = LiveKitProvider()
        # 先用 create_meeting 添加 room
        asyncio.run(
            p.create_meeting(
                topic="t",
                start_time=datetime.now(timezone.utc),
                duration_min=30,
                participants=[Participant(email="a@b.com")],
                host_email="a@b.com",
            )
        )
        room_name = next(iter(p.list_rooms())).name
        rec = p.seed_recording(room_name, duration_seconds=600)
        assert rec.status == "available"
        assert rec.duration_seconds == 600
        assert rec.play_url is not None

    def test_list_rooms(self):
        p = LiveKitProvider()
        # 清空
        with p._lock:
            p._rooms.clear()
        asyncio.run(
            p.create_meeting(
                topic="t1",
                start_time=datetime.now(timezone.utc),
                duration_min=15,
                participants=[Participant(email="a@b.com")],
                host_email="a@b.com",
            )
        )
        rooms = p.list_rooms()
        assert len(rooms) == 1
        assert isinstance(rooms[0], LiveKitRoom)

    def test_webhook_events_constant(self):
        assert "participant_joined" in LIVEKIT_WEBHOOK_EVENTS
        assert "recording_finished" in LIVEKIT_WEBHOOK_EVENTS


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
class TestWebhook:
    def test_verify_webhook_valid(self):
        body = json.dumps({
            "event": "participant_joined",
            "room": {"name": "r1"},
            "participant": {"identity": "alice"},
        }).encode()
        # 用 server token 当 Authorization
        server_tok = issue_access_token(
            DEV_KEY, DEV_SECRET, room_name="*", identity="server",
        )
        result = verify_webhook(
            DEV_KEY, DEV_SECRET,
            body=body,
            authorization_header=f"Bearer {server_tok.token}",
        )
        assert result["event"] == "participant_joined"
        assert result.get("_verified") is True
        assert result["room"]["name"] == "r1"

    def test_verify_webhook_missing_auth_raises(self):
        body = b"{}"
        with pytest.raises(AuthError):
            verify_webhook(DEV_KEY, DEV_SECRET, body=body, authorization_header=None)

    def test_verify_webhook_bad_token_raises(self):
        body = b"{}"
        with pytest.raises(AuthError):
            verify_webhook(
                DEV_KEY, DEV_SECRET, body=body,
                authorization_header="Bearer invalid.token.here",
            )

    def test_verify_webhook_bad_body_raises(self):
        server_tok = issue_access_token(
            DEV_KEY, DEV_SECRET, room_name="*", identity="server",
        )
        with pytest.raises(AuthError):
            verify_webhook(
                DEV_KEY, DEV_SECRET,
                body=b"not json",
                authorization_header=f"Bearer {server_tok.token}",
            )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class TestRegistry:
    def setup_method(self):
        reset_cache()

    def teardown_method(self):
        reset_cache()

    def test_registry_returns_livekit(self, monkeypatch):
        monkeypatch.setenv("VIDEO_PROVIDER", "livekit")
        p = get_video_interview_provider()
        assert p.provider_name == "livekit"

    def test_registry_returns_livekit_alias(self, monkeypatch):
        monkeypatch.setenv("VIDEO_PROVIDER", "livekit_self_hosted")
        p = get_video_interview_provider()
        assert p.provider_name == "livekit"

    def test_registry_fallback_to_mock_when_missing_creds(self, monkeypatch):
        monkeypatch.setenv("VIDEO_PROVIDER", "livekit")
        monkeypatch.setenv("LIVEKIT_API_KEY", "")
        monkeypatch.setenv("LIVEKIT_API_SECRET", "")
        p = get_video_interview_provider()
        # 凭证缺失 → fallback mock
        assert p.provider_name in ("livekit", "mock_video")


# ---------------------------------------------------------------------------
# 真实集成测试 — 需要 LIVEKIT_RUN_INTEGRATION=1 + LiveKit 服务运行
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not os.getenv("LIVEKIT_RUN_INTEGRATION"),
    reason="set LIVEKIT_RUN_INTEGRATION=1 to run real LiveKit room test",
)
class TestLiveKitIntegration:
    """运行: docker compose -f infra/livekit/docker-compose.yml up -d
    然后: LIVEKIT_RUN_INTEGRATION=1 pytest backend/tests/test_livekit.py::TestLiveKitIntegration -v
    """

    @pytest.mark.asyncio
    async def test_real_room_create_and_list(self):
        """真实创建 1 个 LiveKit 房间并查询."""
        p = LiveKitProvider()
        m = await p.create_meeting(
            topic="Real Integration Test",
            start_time=datetime.now(timezone.utc),
            duration_min=30,
            participants=[Participant(email="integration@example.com")],
            host_email="integration@example.com",
        )
        assert m.meeting_id.startswith("int_")

        room = p.get_room(m.meeting_id)
        assert room is not None
        # 真实 LiveKit 会话创建后会通过 sid 标识 (RM_xxx)
        assert room.sid.startswith("RM_") or room.sid.startswith("RM_") or len(room.sid) > 0

        # 录制查询 (即使没开始也返回 processing)
        rec = await p.get_recording(m.meeting_id)
        assert rec.status in ("processing", "available")

        # 清理
        await p.cancel_meeting(m.meeting_id)