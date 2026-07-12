"""Assessment Provider 抽象基类.

T1306 — 接入北森 / 光辉国际 / HackerRank / Codility.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import AssessmentResult, Invitation


class AssessmentProvider(ABC):
    """测评供应商抽象."""

    provider_name: str = "abstract"

    @abstractmethod
    async def send_invitation(
        self,
        candidate_id: str,
        assessment_id: str,
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        expires_in_hours: int = 72,
        metadata: dict[str, str] | None = None,
    ) -> "Invitation":
        """发送测评邀请,返回 invite_url."""

    @abstractmethod
    async def get_results(self, invitation_id: str) -> "AssessmentResult":
        """拉取测评结果.

        候选人未完成时 status='pending';已提交但未出报告 status='submitted';
        已出报告 status='scored' 并附带 overall_score.
        """