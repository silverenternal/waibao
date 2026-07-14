"""Collaboration Room — Room slice (v10.0 T5002 split).

Covers room lifecycle CRUD and the unread-count helpers:
``create_room``, ``get_room``, ``get_room_with_members``, ``list_my_rooms``,
``update_room``, ``archive_room`` and the private ``_count_unread_for_room``
/ ``_count_unread_batch`` batch counters.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    MAX_NAME_LEN,
    ROOM_TYPES,
    Room,
    RoomError,
    archive_room,
    create_room,
    get_room,
    get_room_with_members,
    list_my_rooms,
    update_room,
)
from ._core import (  # noqa: F401
    _count_unread_batch,
    _count_unread_for_room,
    _now_iso,
)

__all__ = [
    "MAX_NAME_LEN",
    "ROOM_TYPES",
    "Room",
    "RoomError",
    "create_room",
    "get_room",
    "get_room_with_members",
    "list_my_rooms",
    "update_room",
    "archive_room",
    "_count_unread_for_room",
    "_count_unread_batch",
    "_now_iso",
]
