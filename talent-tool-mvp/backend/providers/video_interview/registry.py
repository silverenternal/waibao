"""VideoInterview Provider 子注册中心 (T1305).

按 VIDEO_PROVIDER env 决定:zoom / tencent_meeting / mock.
失败 / 凭证缺失时 fallback 到 MockVideoInterviewProvider (业务可继续走流程).
"""
from __future__ import annotations

import os
from threading import Lock

from ..exceptions import InvalidRequestError, ProviderError
from .base import VideoInterviewProvider
from .mock import MockVideoInterviewProvider

_video: VideoInterviewProvider | None = None
_lock = Lock()


def get_video_interview_provider() -> VideoInterviewProvider:
    """按 VIDEO_PROVIDER env 返回 provider 实例,失败 fallback mock."""
    global _video
    if _video is not None:
        return _video
    with _lock:
        if _video is not None:
            return _video
        name = (os.getenv("VIDEO_PROVIDER") or "mock").lower()
        if name == "mock":
            _video = MockVideoInterviewProvider()
            return _video
        if name == "zoom":
            from .zoom import ZoomProvider
            try:
                _video = ZoomProvider()
                if not _video._configured():  # type: ignore[attr-defined]
                    raise InvalidRequestError(
                        "Zoom credentials missing",
                        details={"env": [
                            "ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID",
                            "ZOOM_CLIENT_SECRET",
                        ]},
                    )
            except ProviderError:
                _video = MockVideoInterviewProvider()
            return _video
        if name in ("tencent_meeting", "tencent-meeting", "tmeeting"):
            from .tencent_meeting import TencentMeetingProvider
            try:
                _video = TencentMeetingProvider()
                if not _video._configured():  # type: ignore[attr-defined]
                    raise InvalidRequestError(
                        "Tencent Meeting credentials missing",
                        details={"env": [
                            "TENCENT_MEETING_APP_ID",
                            "TENCENT_MEETING_APP_SECRET",
                        ]},
                    )
            except ProviderError:
                _video = MockVideoInterviewProvider()
            return _video
        raise InvalidRequestError(
            f"unknown VIDEO_PROVIDER={name}",
            details={"supported": ["zoom", "tencent_meeting", "mock"]},
        )


def reset_cache() -> None:
    global _video
    with _lock:
        _video = None


__all__ = ["get_video_interview_provider", "reset_cache"]
