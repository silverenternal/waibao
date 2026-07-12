"""v6.0 T2103 — Feature gate helpers.

Single import location for any backend module that needs to check a
feature flag before executing a critical path. Centralising the import
makes it easy to swap implementations (e.g. add OpenFeature adapter)
without touching call sites.

Usage::

    from services.platform.feature_gate import gate

    @router.post("/ai-interview/start")
    async def start_ai_interview(req, user_id=Depends(...)):
        if not gate("ai_interview", user_id=user_id):
            raise HTTPException(404, "ai_interview not available")
        ...

    # Or as a decorator:

    @feature_gate("video_resume")
    async def upload_video_resume(...):
        ...
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from . import feature_flag as _ff

# Stable set of flag names used by v6.0 critical paths. New flags must be
# added here so linting catches typos in call sites.
FLAG_REALTIME_VOICE = "realtime_voice"
FLAG_AI_INTERVIEW = "ai_interview"
FLAG_VIDEO_RESUME = "video_resume"
FLAG_ABLATION_STUDY = "ablation_study"
FLAG_NEW_MATCHING_V3 = "new_matching_v3"

ALL_FLAGS = frozenset({
    FLAG_REALTIME_VOICE,
    FLAG_AI_INTERVIEW,
    FLAG_VIDEO_RESUME,
    FLAG_ABLATION_STUDY,
    FLAG_NEW_MATCHING_V3,
})


def gate(name: str, *, user_id: Optional[str] = None,
         org_id: Optional[str] = None) -> bool:
    """Thin pass-through so call sites read cleanly: ``if gate("foo"): ...``."""
    return _ff.is_enabled(name, user_id=user_id, org_id=org_id)


def feature_gate(name: str, *, user_id_arg: str = "user_id",
                 org_id_arg: str = "org_id") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that gates a FastAPI route handler on a flag.

    The handler must accept ``user_id`` (and optionally ``org_id``) — either
    as a kwarg or as a dependency. When the flag is off, raises 404 so the
    surface behaves as if the endpoint didn't exist.
    """
    from fastapi import HTTPException  # local import — FastAPI optional

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            uid = kwargs.get(user_id_arg)
            oid = kwargs.get(org_id_arg)
            if not _ff.is_enabled(name, user_id=uid, org_id=oid):
                raise HTTPException(404, f"feature {name!r} is not enabled")
            return await fn(*args, **kwargs)

        return _wrapped

    return _decorator


def is_known_flag(name: str) -> bool:
    return name in ALL_FLAGS


__all__ = [
    "gate",
    "feature_gate",
    "is_known_flag",
    "ALL_FLAGS",
    "FLAG_REALTIME_VOICE",
    "FLAG_AI_INTERVIEW",
    "FLAG_VIDEO_RESUME",
    "FLAG_ABLATION_STUDY",
    "FLAG_NEW_MATCHING_V3",
]