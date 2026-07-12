"""Calendar 双向同步服务 (T1305).

支持:
  - Google Calendar (service account 或 OAuth2 user credentials)
  - Microsoft Outlook Calendar (MS Graph API)

未配置凭证 / 网络错误时降级为 no-op + 记录 last_error,
由人工补偿;决不抛错阻断视频面试主链路.

环境变量:
  GOOGLE_CALENDAR_ENABLED=1
  GOOGLE_CALENDAR_CREDENTIALS_JSON   # Service account JSON 或 OAuth2 refresh token JSON
  GOOGLE_CALENDAR_CALENDAR_ID        # 缺省 primary

  OUTLOOK_CALENDAR_ENABLED=1
  OUTLOOK_CALENDAR_TENANT_ID
  OUTLOOK_CALENDAR_CLIENT_ID
  OUTLOOK_CALENDAR_CLIENT_SECRET
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CalendarEvent:
    """日历事件 payload(供应商无关)."""

    event_id: str | None
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    conference_url: str | None = None
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CalendarSyncResult:
    ok: bool
    provider: str
    event_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CalendarSyncService:
    """统一的 calendar 同步门面."""

    def __init__(self) -> None:
        self.google_enabled = (
            os.getenv("GOOGLE_CALENDAR_ENABLED", "").lower() in ("1", "true", "yes")
        )
        self.outlook_enabled = (
            os.getenv("OUTLOOK_CALENDAR_ENABLED", "").lower() in ("1", "true", "yes")
        )

    # ------------------------------------------------------------------
    # 入站: 推事件到供应商
    # ------------------------------------------------------------------
    async def create_event(
        self,
        provider: str,
        *,
        access_token: str | None,
        event: CalendarEvent,
        calendar_id: str | None = None,
    ) -> CalendarSyncResult:
        if provider == "google":
            return await self._google_create(
                access_token=access_token, event=event, calendar_id=calendar_id,
            )
        if provider == "outlook":
            return await self._outlook_create(
                access_token=access_token, event=event, calendar_id=calendar_id,
            )
        return CalendarSyncResult(
            ok=False, provider=provider, error=f"unsupported provider {provider}"
        )

    async def delete_event(
        self,
        provider: str,
        *,
        access_token: str | None,
        event_id: str,
        calendar_id: str | None = None,
    ) -> CalendarSyncResult:
        if provider == "google":
            return await self._google_delete(
                access_token=access_token, event_id=event_id, calendar_id=calendar_id,
            )
        if provider == "outlook":
            return await self._outlook_delete(
                access_token=access_token, event_id=event_id,
            )
        return CalendarSyncResult(
            ok=False, provider=provider, error=f"unsupported provider {provider}"
        )

    # ------------------------------------------------------------------
    # 出站: 拉事件从供应商(回写到本系统)
    # ------------------------------------------------------------------
    async def fetch_events(
        self,
        provider: str,
        *,
        access_token: str | None,
        since: datetime,
        until: datetime,
        calendar_id: str | None = None,
    ) -> list[CalendarEvent]:
        if provider == "google":
            return await self._google_fetch(
                access_token=access_token,
                since=since,
                until=until,
                calendar_id=calendar_id,
            )
        if provider == "outlook":
            return await self._outlook_fetch(
                access_token=access_token,
                since=since,
                until=until,
            )
        return []

    # ------------------------------------------------------------------
    # Google
    # ------------------------------------------------------------------
    async def _google_create(
        self,
        *,
        access_token: str | None,
        event: CalendarEvent,
        calendar_id: str | None,
    ) -> CalendarSyncResult:
        if not self.google_enabled:
            return CalendarSyncResult(
                ok=False, provider="google",
                error="GOOGLE_CALENDAR_ENABLED not set",
            )
        if not access_token:
            return CalendarSyncResult(
                ok=False, provider="google", error="missing access_token",
            )
        cal = calendar_id or "primary"
        body = {
            "summary": event.title,
            "description": event.description,
            "start": {
                "dateTime": event.start_time.astimezone(timezone.utc)
                .isoformat().replace("+00:00", "Z"),
            },
            "end": {
                "dateTime": event.end_time.astimezone(timezone.utc)
                .isoformat().replace("+00:00", "Z"),
            },
            "conferenceData": (
                {
                    "entryPoints": [
                        {"entryPointType": "video", "uri": event.conference_url}
                    ],
                }
                if event.conference_url else None
            ),
            "attendees": [{"email": a} for a in event.attendees],
        }
        body = {k: v for k, v in body.items() if v is not None}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events",
                    params={"conferenceDataVersion": 1},
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=body,
                )
        except httpx.HTTPError as exc:
            return CalendarSyncResult(
                ok=False, provider="google", error=f"network: {exc}"
            )
        if resp.status_code >= 400:
            return CalendarSyncResult(
                ok=False, provider="google",
                error=f"http {resp.status_code}: {resp.text[:200]}",
                raw={"status": resp.status_code},
            )
        data = resp.json()
        return CalendarSyncResult(
            ok=True, provider="google", event_id=data.get("id"), raw=data,
        )

    async def _google_delete(
        self, *, access_token: str | None, event_id: str, calendar_id: str | None,
    ) -> CalendarSyncResult:
        if not (self.google_enabled and access_token):
            return CalendarSyncResult(ok=False, provider="google", error="disabled")
        cal = calendar_id or "primary"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            return CalendarSyncResult(
                ok=False, provider="google", error=f"network: {exc}"
            )
        ok = resp.status_code in (200, 204, 404)
        return CalendarSyncResult(
            ok=ok, provider="google", error=None if ok else f"http {resp.status_code}"
        )

    async def _google_fetch(
        self, *, access_token: str | None, since: datetime, until: datetime, calendar_id: str | None,
    ) -> list[CalendarEvent]:
        if not (self.google_enabled and access_token):
            return []
        cal = calendar_id or "primary"
        params = {
            "timeMin": since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": until.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
        except httpx.HTTPError as exc:
            logger.warning("calendar_sync.google_fetch.network err=%s", exc)
            return []
        if resp.status_code >= 400:
            logger.warning(
                "calendar_sync.google_fetch.http status=%s body=%s",
                resp.status_code, resp.text[:200],
            )
            return []
        data = resp.json()
        out: list[CalendarEvent] = []
        for item in data.get("items") or []:
            start_dt = _parse_iso(item.get("start", {}).get("dateTime"))
            end_dt = _parse_iso(item.get("end", {}).get("dateTime"))
            conference_url = None
            for ep in (
                (item.get("conferenceData") or {}).get("entryPoints") or []
            ):
                if ep.get("entryPointType") == "video":
                    conference_url = ep.get("uri")
                    break
            out.append(
                CalendarEvent(
                    event_id=item.get("id"),
                    title=item.get("summary") or "",
                    description=item.get("description") or "",
                    start_time=start_dt or datetime.now(timezone.utc),
                    end_time=end_dt or datetime.now(timezone.utc),
                    location=item.get("location"),
                    attendees=[
                        a.get("email") for a in (item.get("attendees") or [])
                        if a.get("email")
                    ],
                    conference_url=conference_url,
                    provider="google",
                    raw=item,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Outlook (MS Graph)
    # ------------------------------------------------------------------
    async def _outlook_create(
        self, *, access_token: str | None, event: CalendarEvent, calendar_id: str | None,
    ) -> CalendarSyncResult:
        if not self.outlook_enabled:
            return CalendarSyncResult(
                ok=False, provider="outlook",
                error="OUTLOOK_CALENDAR_ENABLED not set",
            )
        if not access_token:
            return CalendarSyncResult(
                ok=False, provider="outlook", error="missing access_token",
            )
        url = (
            f"https://graph.microsoft.com/v1.0/users/{calendar_id}/events"
            if calendar_id
            else "https://graph.microsoft.com/v1.0/me/events"
        )
        body = {
            "subject": event.title,
            "body": {"contentType": "Text", "content": event.description},
            "start": {
                "dateTime": event.start_time.astimezone(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "end": {
                "dateTime": event.end_time.astimezone(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "location": (
                {"displayName": event.location} if event.location else None
            ),
            "attendees": [
                {
                    "emailAddress": {"address": a},
                    "type": "required",
                }
                for a in event.attendees
            ],
        }
        body = {k: v for k, v in body.items() if v is not None}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            return CalendarSyncResult(
                ok=False, provider="outlook", error=f"network: {exc}"
            )
        if resp.status_code >= 400:
            return CalendarSyncResult(
                ok=False, provider="outlook",
                error=f"http {resp.status_code}: {resp.text[:200]}",
                raw={"status": resp.status_code},
            )
        data = resp.json()
        return CalendarSyncResult(
            ok=True, provider="outlook", event_id=data.get("id"), raw=data,
        )

    async def _outlook_delete(
        self, *, access_token: str | None, event_id: str,
    ) -> CalendarSyncResult:
        if not (self.outlook_enabled and access_token):
            return CalendarSyncResult(ok=False, provider="outlook", error="disabled")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            return CalendarSyncResult(
                ok=False, provider="outlook", error=f"network: {exc}"
            )
        ok = resp.status_code in (200, 204, 404)
        return CalendarSyncResult(
            ok=ok, provider="outlook", error=None if ok else f"http {resp.status_code}"
        )

    async def _outlook_fetch(
        self, *, access_token: str | None, since: datetime, until: datetime,
    ) -> list[CalendarEvent]:
        if not (self.outlook_enabled and access_token):
            return []
        url = (
            "https://graph.microsoft.com/v1.0/me/calendarView/"
            f"startDateTime={since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&endDateTime={until.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("calendar_sync.outlook_fetch.network err=%s", exc)
            return []
        if resp.status_code >= 400:
            logger.warning(
                "calendar_sync.outlook_fetch.http status=%s body=%s",
                resp.status_code, resp.text[:200],
            )
            return []
        data = resp.json()
        out: list[CalendarEvent] = []
        for item in data.get("value") or []:
            start_dt = _parse_iso(item.get("start", {}).get("dateTime"))
            end_dt = _parse_iso(item.get("end", {}).get("dateTime"))
            out.append(
                CalendarEvent(
                    event_id=item.get("id"),
                    title=item.get("subject") or "",
                    description=(item.get("body") or {}).get("content") or "",
                    start_time=start_dt or datetime.now(timezone.utc),
                    end_time=end_dt or datetime.now(timezone.utc),
                    location=(item.get("location") or {}).get("displayName"),
                    attendees=[
                        (a.get("emailAddress") or {}).get("address")
                        for a in (item.get("attendees") or [])
                        if (a.get("emailAddress") or {}).get("address")
                    ],
                    provider="outlook",
                    raw=item,
                )
            )
        return out


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


__all__ = [
    "CalendarEvent",
    "CalendarSyncResult",
    "CalendarSyncService",
]
