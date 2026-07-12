"""BackgroundCheck Provider 抽象基类.

T1307 — 接入 Checkr / iCIMS / HireRight / 中华背调.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Check, CheckStatus, CheckType


class BackgroundCheckProvider(ABC):
    """背景调查供应商抽象."""

    provider_name: str = "abstract"

    @abstractmethod
    async def initiate_check(
        self,
        candidate_id: str,
        check_types: list["CheckType"],
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "Check":
        """发起背调任务,返回 check_id 用于后续跟踪."""

    @abstractmethod
    async def get_status(self, check_id: str) -> "CheckStatus":
        """查询背调任务状态 + findings + report_url."""