"""Collaboration Room — Reaction / Pin slice (v10.0 T5002 split).

Covers emoji reactions and pinned messages:
``add_reaction``, ``list_reactions``, ``pin_message``, ``unpin_message`` and
``list_pins``.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    MAX_REACTIONS_PER_MESSAGE,
    MessageNotFoundError,
    RoomError,
    RoomReaction,
    add_reaction,
    list_pins,
    list_reactions,
    pin_message,
    unpin_message,
)

__all__ = [
    "MAX_REACTIONS_PER_MESSAGE",
    "MessageNotFoundError",
    "RoomError",
    "RoomReaction",
    "add_reaction",
    "list_reactions",
    "pin_message",
    "unpin_message",
    "list_pins",
]
