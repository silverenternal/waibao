"""MockBackgroundCheckProvider 单元测试."""
from __future__ import annotations

import pytest

from backend.providers.background_check import (
    BackgroundCheckProvider,
    Check,
    CheckStatus,
    CheckType,
)
from backend.providers.background_check.mock import MockBackgroundCheckProvider
from backend.providers.exceptions import InvalidRequestError


@pytest.fixture()
def provider() -> MockBackgroundCheckProvider:
    return MockBackgroundCheckProvider()


@pytest.mark.asyncio
async def test_initiate_check(provider: MockBackgroundCheckProvider) -> None:
    check = await provider.initiate_check(
        candidate_id="cand_001",
        check_types=[
            CheckType(code="criminal", required=True),
            CheckType(code="employment", required=True),
            CheckType(code="reference", required=False),
        ],
        candidate_email="c@example.com",
        candidate_name="Eve",
    )
    assert isinstance(check, Check)
    assert check.check_id.startswith("chk_mock_")
    assert check.status == "pending"
    assert set(check.check_types) == {"criminal", "employment", "reference"}


@pytest.mark.asyncio
async def test_initiate_check_validates(provider: MockBackgroundCheckProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.initiate_check(candidate_id="", check_types=[CheckType(code="criminal")])
    with pytest.raises(InvalidRequestError):
        await provider.initiate_check(
            candidate_id="cand_x", check_types=[CheckType(code="not_a_real_code")],
        )
    with pytest.raises(InvalidRequestError):
        await provider.initiate_check(candidate_id="cand_x", check_types=[])


@pytest.mark.asyncio
async def test_get_status_pending_then_clear(provider: MockBackgroundCheckProvider) -> None:
    check = await provider.initiate_check(
        candidate_id="cand_002",
        check_types=[CheckType(code="criminal")],
    )
    pending = await provider.get_status(check.check_id)
    assert isinstance(pending, CheckStatus)
    assert pending.status == "pending"
    assert pending.progress_pct == 0.0

    provider.seed_status(check.check_id, status="clear", progress_pct=100.0)
    cleared = await provider.get_status(check.check_id)
    assert cleared.status == "clear"
    assert cleared.report_url is not None


@pytest.mark.asyncio
async def test_get_status_unknown(provider: MockBackgroundCheckProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.get_status("chk_mock_does_not_exist")


def test_abc_subclass_compliance() -> None:
    assert isinstance(MockBackgroundCheckProvider(), BackgroundCheckProvider)