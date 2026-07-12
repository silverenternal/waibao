"""VideoInterview 业务服务 (T1305).

职责:
  - 选择 video provider (zoom / tencent_meeting / mock)
  - 创建会议 + 持久化到 video_interviews 表
  - 异步触发日历同步 (Google / Outlook,失败不阻断)
  - 处理 webhook (meeting.started / ended / recording_ready)
  - 把 video_recording 桥接到 v3.0 /api/uploads (录制文件上传)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from providers.video_interview.registry import get_video_interview_provider
from providers.video_interview.types import Meeting, Participant, Recording
from services.calendar_sync import CalendarEvent, CalendarSyncService

logger = logging.getLogger(__name__)


class VideoInterviewService:
    """业务层封装: 创建/取消/录制查询/日历同步."""

    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase
        self.calendar = CalendarSyncService()
        # mock provider 复用单例,保证 schedule/cancel/get_recording 共享存储
        from providers.video_interview.mock import MockVideoInterviewProvider
        self._mock = MockVideoInterviewProvider()

    # ------------------------------------------------------------------
    # provider 选择
    # ------------------------------------------------------------------
    def _provider(self, preferred: str | None = None) -> Any:
        """根据 preferred 切到对应 provider.

        preferred 为 None 时按 env 走.registry 会缓存,这里短时 reset.
        业务可指定 preferred (e.g. "tencent_meeting" when candidate 在 CN).
        """
        import os
        from providers.video_interview.registry import reset_cache
        if preferred:
            os.environ["VIDEO_PROVIDER"] = preferred
            reset_cache()
        else:
            # 不强制 reset 避免其他租户的缓存频繁失效;只在没有缓存时
            # 让 registry 自由选择
            pass
        return get_video_interview_provider()

    def _provider_by_name(self, name: str | None) -> Any:
        """直接根据历史 row 中的 provider 字段取实例.

        row["provider"] 是 MockVideoInterviewProvider.provider_name
        或 ZoomProvider.provider_name 等的取值,如:
            - mock_video / zoom / tencent_meeting
        这里按映射直接构造,避免触发 registry 的 env reset.
        mock 复用 service 自身的 _mock 单例,保证共享存储.
        """
        mapping = {
            "zoom": self._import_zoom,
            "tencent_meeting": self._import_tencent,
            "mock_video": self._import_mock,
        }
        factory = mapping.get(name or "")
        if factory is None:
            return self._mock
        try:
            return factory()
        except Exception:
            return self._mock

    def _import_zoom(self):
        from providers.video_interview.zoom import ZoomProvider
        return ZoomProvider()

    def _import_tencent(self):
        from providers.video_interview.tencent_meeting import (
            TencentMeetingProvider,
        )
        return TencentMeetingProvider()

    def _import_mock(self):
        return self._mock

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    async def schedule_interview(
        self,
        *,
        ticket_id: UUID | None,
        match_id: UUID | None,
        candidate_id: UUID,
        employer_id: UUID,
        host_email: str,
        topic: str,
        start_time: datetime,
        duration_min: int,
        participant_emails: list[str],
        preferred_provider: str | None = None,
        calendar_tokens: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        # 1) provider 调真实 / mock API
        provider = self._provider(preferred_provider)
        participants = [
            Participant(
                email=host_email,
                name="Host",
                role="host",
                user_id=str(employer_id),
            )
        ]
        for email in participant_emails:
            role = "attendee"
            participants.append(
                Participant(email=email, role=role)
            )

        try:
            meeting: Meeting = await provider.create_meeting(
                topic=topic,
                start_time=start_time,
                duration_min=duration_min,
                participants=participants,
                host_email=host_email,
                metadata={
                    "ticket_id": str(ticket_id) if ticket_id else "",
                    "match_id": str(match_id) if match_id else "",
                    "employer_id": str(employer_id),
                },
            )
        except Exception as exc:
            # 真实供应商失败 → fallback 到 mock (保证业务不阻断)
            logger.warning(
                "video_interview.create_meeting.fallback provider=%s err=%s",
                getattr(provider, "provider_name", "?"), exc,
            )
            provider = self._mock
            meeting = await provider.create_meeting(
                topic=topic,
                start_time=start_time,
                duration_min=duration_min,
                participants=participants,
                host_email=host_email,
                metadata={
                    "ticket_id": str(ticket_id) if ticket_id else "",
                    "match_id": str(match_id) if match_id else "",
                    "employer_id": str(employer_id),
                },
            )

        # 2) 写库
        record = {
            "ticket_id": str(ticket_id) if ticket_id else None,
            "match_id": str(match_id) if match_id else None,
            "candidate_id": str(candidate_id),
            "employer_id": str(employer_id),
            "host_email": host_email,
            "topic": topic,
            "provider": meeting.provider,
            "meeting_id": meeting.meeting_id,
            "join_url": meeting.join_url,
            "host_url": meeting.host_url,
            "password": meeting.password,
            "start_time": start_time.astimezone(timezone.utc).isoformat(),
            "duration_min": duration_min,
            "status": "scheduled",
            "metadata": meeting.metadata,
        }
        res = self.supabase.table("video_interviews").insert(record).execute()
        if not res.data:
            raise RuntimeError("failed to insert video_interviews row")
        row = res.data[0]
        video_interview_id = row["id"]

        # 3) 异步日历同步 (失败不影响主流程)
        if calendar_tokens:
            end_time = start_time + (
                __import__("datetime").timedelta(minutes=duration_min)
            )
            event = CalendarEvent(
                event_id=None,
                title=topic,
                description=(
                    f"Video interview for ticket {ticket_id}\n"
                    f"Join: {meeting.join_url}"
                ),
                start_time=start_time,
                end_time=end_time,
                location=meeting.join_url,
                attendees=[host_email] + participant_emails,
                conference_url=meeting.join_url,
                provider=meeting.provider,
            )
            for prov_name, token in calendar_tokens.items():
                try:
                    rs = await self.calendar.create_event(
                        prov_name,
                        access_token=token,
                        event=event,
                    )
                    if rs.ok and rs.event_id:
                        synced = row.get("calendar_synced_to") or []
                        if prov_name not in synced:
                            synced.append(prov_name)
                        self.supabase.table("video_interviews").update(
                            {
                                "calendar_event_id": rs.event_id,
                                "calendar_synced_to": synced,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        ).eq("id", video_interview_id).execute()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "calendar_sync.failed provider=%s err=%s", prov_name, exc,
                    )

        return row

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------
    async def cancel_interview(self, video_interview_id: UUID) -> dict[str, Any]:
        r = (
            self.supabase.table("video_interviews")
            .select("*")
            .eq("id", str(video_interview_id))
            .single()
            .execute()
        )
        row = r.data
        if not row:
            raise LookupError(f"video_interview {video_interview_id} not found")
        # row["provider"] 是实际使用的 provider name (mock_video/zoom/tencent_meeting),
        # 不需要重新切 vendor,直接拿对应的实例即可.
        provider = self._provider_by_name(row.get("provider"))
        try:
            await provider.cancel_meeting(row["meeting_id"])
        except Exception as exc:
            logger.warning(
                "video_interview.cancel.provider err=%s", exc,
            )
            # mock fallback 用 service 共享单例
            try:
                await self._mock.cancel_meeting(row["meeting_id"])
            except Exception:
                pass

        self.supabase.table("video_interviews").update(
            {
                "status": "canceled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", str(video_interview_id)).execute()

        # 同步删除日历
        synced = row.get("calendar_synced_to") or []
        for prov_name in synced:
            try:
                cal_event_id = row.get("calendar_event_id")
                if cal_event_id:
                    token = (row.get("metadata") or {}).get(
                        f"calendar_token_{prov_name}"
                    )
                    if token:
                        await self.calendar.delete_event(
                            prov_name,
                            access_token=token,
                            event_id=cal_event_id,
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "calendar_delete.failed provider=%s err=%s", prov_name, exc,
                )
        return {"status": "canceled"}

    # ------------------------------------------------------------------
    # recording
    # ------------------------------------------------------------------
    async def get_recording(
        self, video_interview_id: UUID
    ) -> dict[str, Any]:
        r = (
            self.supabase.table("video_interviews")
            .select("*")
            .eq("id", str(video_interview_id))
            .single()
            .execute()
        )
        row = r.data
        if not row:
            raise LookupError(f"video_interview {video_interview_id} not found")
        provider = self._provider_by_name(row.get("provider"))
        try:
            rec: Recording = await provider.get_recording(row["meeting_id"])
        except Exception:
            rec = await self._mock.get_recording(row["meeting_id"])
        # 落库 + 触发上传(v3.0 /api/uploads 桥接)
        uploads_url: str | None = None
        if rec.download_url:
            try:
                uploads_url = await self._bridge_recording_to_uploads(
                    video_interview_id=row["id"],
                    download_url=rec.download_url,
                    provider=row.get("provider"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "recording_bridge.failed err=%s", exc,
                )
        update = {
            "recording_id": rec.recording_id,
            "recording_url": rec.play_url or rec.download_url,
            "transcript_url": rec.transcript_url,
            "status": "ended" if row.get("status") == "ended" else row.get("status"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if uploads_url:
            update["metadata"] = {
                **(row.get("metadata") or {}),
                "uploads_url": uploads_url,
            }
        self.supabase.table("video_interviews").update(
            update
        ).eq("id", row["id"]).execute()
        return {
            "video_interview_id": row["id"],
            "recording_id": rec.recording_id,
            "status": rec.status,
            "play_url": rec.play_url,
            "download_url": rec.download_url,
            "duration_seconds": rec.duration_seconds,
            "uploads_url": uploads_url,
            "provider": row.get("provider"),
        }

    async def _bridge_recording_to_uploads(
        self,
        *,
        video_interview_id: str,
        download_url: str,
        provider: str,
    ) -> str | None:
        """把供应商录制的下载链接登记到本系统的 uploads,
        便于前端通过 /api/uploads/<id> 直接获取.
        真实实现通常后台拉文件转存; 此处记录元数据即可.
        """
        meta = {
            "kind": "video_recording",
            "video_interview_id": video_interview_id,
            "source_provider": provider,
            "source_url": download_url,
        }
        r = self.supabase.table("uploads").insert(
            {
                "url": download_url,
                "kind": "video_recording",
                "metadata": meta,
                "status": "pending",
            }
        ).execute()
        if r.data:
            return r.data[0].get("public_url") or download_url
        return None

    # ------------------------------------------------------------------
    # webhook 入站
    # ------------------------------------------------------------------
    async def handle_webhook(
        self,
        *,
        provider: str,
        event_type: str,
        meeting_id: str,
        payload: dict[str, Any],
    ) -> bool:
        v = (
            self.supabase.table("video_interviews")
            .select("*")
            .eq("meeting_id", meeting_id)
            .execute()
        )
        video_interview_id = None
        # provider 字符串可能为 "zoom" / "tencent_meeting" / "mock_video"
        # 与传入 "mock" / "zoom" / "tencent_meeting" 不一致 → 兼容:
        provider_aliases = {
            "zoom": {"zoom"},
            "tencent_meeting": {"tencent_meeting", "tmeeting"},
            "mock_video": {"mock", "mock_video"},
        }
        for row in (v.data or []):
            row_provider = row.get("provider") or ""
            aliases = provider_aliases.get(row_provider, {row_provider})
            aliases |= provider_aliases.get(provider, {provider})
            if provider in aliases or row_provider in aliases:
                video_interview_id = row["id"]
                break
        self.supabase.table("video_webhooks").insert(
            {
                "provider": provider,
                "event_type": event_type,
                "meeting_id": meeting_id,
                "video_interview_id": video_interview_id,
                "payload": payload,
                "processed": True,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        if not video_interview_id:
            return False

        update: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if event_type in ("meeting.started", "start", "meeting_started"):
            update["status"] = "started"
        elif event_type in ("meeting.ended", "end", "meeting_ended"):
            update["status"] = "ended"
        elif event_type in ("recording.completed", "recording_ready"):
            rec_id = (
                payload.get("recording_id")
                or payload.get("uuid")
                or ""
            )
            update["recording_id"] = str(rec_id)
            update["recording_url"] = (
                payload.get("play_url") or payload.get("download_url")
            )
        self.supabase.table("video_interviews").update(
            update
        ).eq("id", video_interview_id).execute()
        return True


__all__ = ["VideoInterviewService"]
