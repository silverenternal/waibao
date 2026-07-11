"""Notify Provider 抽象基类."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NotifyMessage:
    """统一通知消息."""

    subject: str | None = None
    body: str = ""
    html: str | None = None
    to: list[str] = field(default_factory=list)
    attachments: list[tuple[str, bytes, str]] | None = None  # (filename, content, mime)
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class NotifyResult:
    """统一通知结果."""

    success: bool
    channel: str
    message_id: str | None = None
    error: str | None = None
    raw: Any = None


class NotifyProvider(ABC):
    """发送通知."""

    channel: str = "abstract"

    @abstractmethod
    async def send(self, message: NotifyMessage) -> NotifyResult: ...
