"""Collaboration Room — Mention / Read-state slice (v10.0 T5002 split).

Covers ``@mention`` notifications and read/unread tracking:
``list_my_mentions``, ``mark_mention_read``, ``mark_read``,
``get_unread_count`` and ``get_total_unread_count``.  Logic lives in
:mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    get_total_unread_count,
    get_unread_count,
    list_my_mentions,
    mark_mention_read,
    mark_read,
)
from ._core import (  # noqa: F401
    _get_last_read_at,
)

__all__ = [
    "list_my_mentions",
    "mark_mention_read",
    "mark_read",
    "get_unread_count",
    "get_total_unread_count",
    "_get_last_read_at",
]
