"""Assessment Provider Mock 实现."""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone

from ..base import RetryPolicy, with_resilience
from ..exceptions import InvalidRequestError
from .base import AssessmentProvider
from .types import AssessmentResult, Invitation, Score


class MockAssessmentProvider(AssessmentProvider):
    """Mock 实现,内存保存邀请 + 结果."""

    provider_name = "mock_assessment"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._invitations: dict[str, Invitation] = {}
        self._results: dict[str, AssessmentResult] = {}

    @with_resilience(
        provider="assessment_mock",
        method="send_invitation",
        retry=RetryPolicy(max_retries=2),
    )
    async def send_invitation(
        self,
        candidate_id: str,
        assessment_id: str,
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        expires_in_hours: int = 72,
        metadata: dict[str, str] | None = None,
    ) -> Invitation:
        if not candidate_id or not assessment_id:
            raise InvalidRequestError(
                "candidate_id and assessment_id are required",
                provider=self.provider_name,
            )
        inv_id = f"inv_mock_{secrets.token_hex(6)}"
        now = datetime.now(timezone.utc)
        invite_url = f"https://mock-assessment.local/take/{inv_id}"
        invitation = Invitation(
            invitation_id=inv_id,
            candidate_id=candidate_id,
            assessment_id=assessment_id,
            status="pending",
            invite_url=invite_url,
            expires_at=now + timedelta(hours=expires_in_hours),
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "candidate_email": candidate_email or "",
                "candidate_name": candidate_name or "",
            },
        )
        with self._lock:
            self._invitations[inv_id] = invitation
        return invitation

    @with_resilience(
        provider="assessment_mock",
        method="get_results",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_results(self, invitation_id: str) -> AssessmentResult:
        with self._lock:
            cached = self._results.get(invitation_id)
            if cached is not None:
                return cached
            inv = self._invitations.get(invitation_id)
        if inv is None:
            raise InvalidRequestError(
                f"invitation {invitation_id} not found",
                provider=self.provider_name,
            )
        # 默认返回 pending (候选人未开始 / 未提交)
        return AssessmentResult(
            invitation_id=invitation_id,
            candidate_id=inv.candidate_id,
            assessment_id=inv.assessment_id,
            status="pending",
            provider=self.provider_name,
        )

    # ----- 测试辅助 -----
    def seed_result(
        self,
        invitation_id: str,
        *,
        overall_score: float = 82.5,
        percentile: float = 75.0,
        passed: bool = True,
    ) -> AssessmentResult:
        result = AssessmentResult(
            invitation_id=invitation_id,
            candidate_id="cand_seed",
            assessment_id="assess_seed",
            status="scored",
            overall_score=overall_score,
            percentile=percentile,
            passed=passed,
            scores=[
                Score(name="logical", value=overall_score, band="high"),
                Score(name="coding", value=overall_score - 5, band="mid"),
            ],
            report_url=f"https://mock-assessment.local/reports/{invitation_id}",
            completed_at=datetime.now(timezone.utc),
            provider=self.provider_name,
        )
        with self._lock:
            self._results[invitation_id] = result
        return result