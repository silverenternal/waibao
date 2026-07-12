"""MockAssessmentProvider 单元测试."""
from __future__ import annotations

import pytest

from backend.providers.assessment import (
    AssessmentProvider,
    AssessmentResult,
    Invitation,
)
from backend.providers.assessment.mock import MockAssessmentProvider
from backend.providers.exceptions import InvalidRequestError


@pytest.fixture()
def provider() -> MockAssessmentProvider:
    return MockAssessmentProvider()


@pytest.mark.asyncio
async def test_send_invitation(provider: MockAssessmentProvider) -> None:
    inv = await provider.send_invitation(
        candidate_id="cand_001",
        assessment_id="assess_logical_v3",
        candidate_email="c@example.com",
        candidate_name="Charlie",
        expires_in_hours=48,
    )
    assert isinstance(inv, Invitation)
    assert inv.status == "pending"
    assert inv.invite_url is not None
    assert inv.expires_at is not None


@pytest.mark.asyncio
async def test_send_invitation_validates(provider: MockAssessmentProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.send_invitation(candidate_id="", assessment_id="assess_x")
    with pytest.raises(InvalidRequestError):
        await provider.send_invitation(candidate_id="cand_x", assessment_id="")


@pytest.mark.asyncio
async def test_get_results_pending_then_scored(provider: MockAssessmentProvider) -> None:
    inv = await provider.send_invitation(
        candidate_id="cand_002",
        assessment_id="assess_v1",
    )
    pending = await provider.get_results(inv.invitation_id)
    assert isinstance(pending, AssessmentResult)
    assert pending.status == "pending"
    assert pending.overall_score is None

    provider.seed_result(inv.invitation_id, overall_score=91.0, percentile=88.0)
    scored = await provider.get_results(inv.invitation_id)
    assert scored.status == "scored"
    assert scored.overall_score == 91.0
    assert scored.passed is True


@pytest.mark.asyncio
async def test_get_results_unknown(provider: MockAssessmentProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.get_results("inv_mock_does_not_exist")


def test_abc_subclass_compliance() -> None:
    assert isinstance(MockAssessmentProvider(), AssessmentProvider)