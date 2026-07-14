"""Collaboration Room — Member slice (v10.0 T5002 split).

Covers the membership lifecycle:
``invite_member``, ``remove_member``, ``leave_room`` and ``list_members``.
Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    ROOM_MEMBER_ROLES,
    NotMemberError,
    PermissionDeniedError,
    RoomError,
    RoomMember,
    invite_member,
    leave_room,
    list_members,
    remove_member,
)
from ._core import (  # noqa: F401
    _check_admin,
    _check_member,
)

__all__ = [
    "ROOM_MEMBER_ROLES",
    "NotMemberError",
    "PermissionDeniedError",
    "RoomError",
    "RoomMember",
    "invite_member",
    "remove_member",
    "leave_room",
    "list_members",
    "_check_admin",
    "_check_member",
]
