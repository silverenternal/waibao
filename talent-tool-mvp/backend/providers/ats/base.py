"""ATS Provider 抽象基类.

T1501 — 与 Greenhouse / Lever / Workday / iCIMS 双向同步候选人 + 职位.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Candidate, CandidateStatus, ExternalId, Job


class ATSProvider(ABC):
    """ATS 供应商抽象.

    推 (push) = 从本系统写入 ATS;
    拉 (pull) = 从 ATS 拉回本系统,通常配合 since 增量同步.
    """

    provider_name: str = "abstract"

    @abstractmethod
    async def push_candidate(self, candidate: "Candidate") -> "ExternalId":
        """创建或更新候选人;返回 ATS 内的 external_id."""

    @abstractmethod
    async def pull_candidates(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list["Candidate"]:
        """增量拉取候选人列表.

        since=None 时全量拉取;否则只拉取 since 之后变更的.
        """

    @abstractmethod
    async def push_job(self, job: "Job") -> "ExternalId":
        """创建或更新职位."""

    @abstractmethod
    async def pull_jobs(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list["Job"]:
        """增量拉取职位列表."""

    @abstractmethod
    async def update_status(
        self,
        external_id: str,
        status: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """更新候选人在 ATS 中的状态.

        status 取值: new / screening / interview / offer / hired / rejected
        """