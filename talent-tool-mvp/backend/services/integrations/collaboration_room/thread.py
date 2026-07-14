"""Collaboration Room — Thread / Message slice (v10.0 T5002 split).

Covers the message pipeline and threads:
``post_message``, ``edit_message``, ``delete_message``, ``list_messages``,
``list_thread_replies`` and ``search_messages``.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    MAX_MESSAGE_LEN,
    MESSAGE_TYPES,
    MessageNotFoundError,
    PermissionDeniedError,
    RoomError,
    RoomMessage,
    delete_message,
    edit_message,
    list_messages,
    list_thread_replies,
    post_message,
    search_messages,
)
from ._core import (  # noqa: F401
    _message_has_parent,
    _parse_mentions,
)

__all__ = [
    "MAX_MESSAGE_LEN",
    "MESSAGE_TYPES",
    "MessageNotFoundError",
    "PermissionDeniedError",
    "RoomError",
    "RoomMessage",
    "post_message",
    "edit_message",
    "delete_message",
    "list_messages",
    "list_thread_replies",
    "search_messages",
    "_parse_mentions",
    "_message_has_parent",
]
