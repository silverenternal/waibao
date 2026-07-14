"""Collaboration Room (T608 / v10.0 T5002 split package).

The single 1115-line module was split in v10.0 T5002 into five cohesive
submodules while keeping the public surface 100 % backward compatible:

    room       — Room CRUD: create / get / list_my_rooms / update / archive
                 (+ unread-count batch helpers)
    thread     — messages, threads, search: post / edit / delete / list /
                 list_thread_replies / search_messages
    member     — membership lifecycle: invite / remove / leave / list
    reaction   — reactions + pin / unpin / list_pins
    mention    — @mention notifications: list_my_mentions / mark_mention_read

All logic lives in :mod:`._core`; the submodules re-export the relevant slice
of the API so every previously-importable name keeps working through both
``from services.integrations.collaboration_room import X`` and the v5.0 shim
``from services.collaboration_room import X``.
"""
from __future__ import annotations

# Re-export the full public surface so the package is identical to the
# pre-split flat module.  Private helpers are re-exported on purpose — the
# v5.0 __all__ exposed them and api/realtime.py imports ``_check_member``.
from ._core import (  # noqa: F401
    MAX_MESSAGE_LEN,
    MAX_NAME_LEN,
    MAX_REACTIONS_PER_MESSAGE,
    MESSAGE_TYPES,
    ROOM_MEMBER_ROLES,
    ROOM_TYPES,
    MessageNotFoundError,
    NotMemberError,
    PermissionDeniedError,
    Room,
    RoomError,
    RoomMember,
    RoomMessage,
    RoomReaction,
    add_reaction,
    archive_room,
    create_room,
    delete_message,
    edit_message,
    get_room,
    get_room_with_members,
    get_total_unread_count,
    get_unread_count,
    invite_member,
    leave_room,
    list_members,
    list_messages,
    list_my_mentions,
    list_my_rooms,
    list_pins,
    list_reactions,
    list_thread_replies,
    mark_mention_read,
    mark_read,
    pin_message,
    post_message,
    remove_member,
    search_messages,
    unpin_message,
    update_room,
)
from ._core import (  # noqa: F401
    _check_admin,
    _check_member,
    _count_unread_batch,
    _count_unread_for_room,
    _get_last_read_at,
    _now_iso,
    _parse_mentions,
)
from .member import *  # noqa: F401,F403
from .mention import *  # noqa: F401,F403
from .reaction import *  # noqa: F401,F403
from .room import *  # noqa: F401,F403
from .thread import *  # noqa: F401,F403

__all__ = [
    "ROOM_TYPES",
    "ROOM_MEMBER_ROLES",
    "MESSAGE_TYPES",
    "MAX_MESSAGE_LEN",
    "MAX_NAME_LEN",
    "MAX_REACTIONS_PER_MESSAGE",
    "RoomError",
    "NotMemberError",
    "MessageNotFoundError",
    "PermissionDeniedError",
    "Room",
    "RoomMember",
    "RoomMessage",
    "RoomReaction",
    "create_room",
    "get_room",
    "get_room_with_members",
    "list_my_rooms",
    "update_room",
    "archive_room",
    "invite_member",
    "remove_member",
    "leave_room",
    "list_members",
    "post_message",
    "edit_message",
    "delete_message",
    "list_messages",
    "list_thread_replies",
    "search_messages",
    "add_reaction",
    "list_reactions",
    "pin_message",
    "unpin_message",
    "list_pins",
    "mark_read",
    "get_unread_count",
    "get_total_unread_count",
    "list_my_mentions",
    "mark_mention_read",
    "_check_admin",
    "_check_member",
    "_count_unread_for_room",
    "_count_unread_batch",
    "_parse_mentions",
    "_now_iso",
    "_get_last_read_at",
]
