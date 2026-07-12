"""MockATSProvider 单元测试."""
from __future__ import annotations

import pytest

from backend.providers.ats import (
    ATSProvider,
    Candidate,
    ExternalId,
    Job,
)
from backend.providers.ats.mock import MockATSProvider
from backend.providers.exceptions import InvalidRequestError


@pytest.fixture()
def provider() -> MockATSProvider:
    return MockATSProvider()


@pytest.mark.asyncio
async def test_abc_can_be_implemented() -> None:
    """接口必须能被实现 — 即 isinstance 检查通过."""
    p = MockATSProvider()
    assert isinstance(p, ATSProvider)


@pytest.mark.asyncio
async def test_push_candidate_creates_and_dedupes(provider: MockATSProvider) -> None:
    cand = Candidate(name="Alice", email="alice@example.com")
    first = await provider.push_candidate(cand)
    assert isinstance(first, ExternalId)
    assert first.external_id.startswith("cand_mock_")

    # 同 email 重复 push 应复用同一 external_id
    again = await provider.push_candidate(Candidate(name="Alice 2", email="alice@example.com"))
    assert again.external_id == first.external_id


@pytest.mark.asyncio
async def test_pull_candidates_returns_seeded(provider: MockATSProvider) -> None:
    provider.seed_candidate(
        Candidate(name="Bob", email="bob@example.com"),
        external_id="cand_mock_00000001",
    )
    provider.seed_candidate(
        Candidate(name="Carol", email="carol@example.com"),
        external_id="cand_mock_00000002",
    )
    results = await provider.pull_candidates()
    assert len(results) >= 2
    emails = {c.email for c in results}
    assert "bob@example.com" in emails
    assert "carol@example.com" in emails


@pytest.mark.asyncio
async def test_push_and_pull_jobs(provider: MockATSProvider) -> None:
    job = Job(title="Senior Engineer", description="Build cool stuff")
    ext = await provider.push_job(job)
    assert ext.external_id.startswith("job_mock_")

    jobs = await provider.pull_jobs()
    assert any(j.title == "Senior Engineer" for j in jobs)


@pytest.mark.asyncio
async def test_update_status_validates(provider: MockATSProvider) -> None:
    provider.seed_candidate(
        Candidate(name="Dan", email="dan@example.com"),
        external_id="cand_mock_00000010",
    )
    await provider.update_status("cand_mock_00000010", "interview")
    status = provider.get_status("cand_mock_00000010")
    assert status is not None
    assert status.status == "interview"

    with pytest.raises(InvalidRequestError):
        await provider.update_status("cand_mock_00000010", "invalid-status")


@pytest.mark.asyncio
async def test_update_status_requires_existing(provider: MockATSProvider) -> None:
    with pytest.raises(InvalidRequestError):
        await provider.update_status("cand_mock_does_not_exist", "interview")