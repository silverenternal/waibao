"""ATS Provider Mock 实现.

完全离线,内存保存候选人 + 职位.
支持:
- push_candidate: 写入并返回 external_id
- pull_candidates: 支持 since 增量
- push_job / pull_jobs: 同上
- update_status: 状态机校验
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from ..base import RetryPolicy, with_resilience
from ..exceptions import InvalidRequestError
from .base import ATSProvider
from .types import Candidate, CandidateStatus, ExternalId, Job


_VALID_STATUSES = {"new", "screening", "interview", "offer", "hired", "rejected"}


class MockATSProvider(ATSProvider):
    """Mock 实现,模拟双向同步."""

    provider_name = "mock_ats"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._candidates: dict[str, Candidate] = {}
        self._candidate_status: dict[str, CandidateStatus] = {}
        self._jobs: dict[str, Job] = {}
        self._cand_seq = 0
        self._job_seq = 0

    # ----- helpers -----
    def _next_candidate_id(self) -> str:
        with self._lock:
            self._cand_seq += 1
            return f"cand_mock_{self._cand_seq:08d}"

    def _next_job_id(self) -> str:
        with self._lock:
            self._job_seq += 1
            return f"job_mock_{self._job_seq:08d}"

    # ----- API -----
    @with_resilience(
        provider="ats_mock",
        method="push_candidate",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_candidate(self, candidate: Candidate) -> ExternalId:
        if not candidate.email:
            raise InvalidRequestError("candidate.email is required")
        with self._lock:
            # 按 email 去重
            existing_id = None
            for ext_id, c in self._candidates.items():
                if c.email == candidate.email:
                    existing_id = ext_id
                    break
            if existing_id is None:
                existing_id = candidate.external_id or self._next_candidate_id()
            self._candidates[existing_id] = candidate
        return ExternalId(
            external_id=existing_id,
            external_url=f"https://mock-ats.local/candidates/{existing_id}",
        )

    @with_resilience(
        provider="ats_mock",
        method="pull_candidates",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_candidates(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Candidate]:
        with self._lock:
            results: list[Candidate] = []
            for ext_id, cand in self._candidates.items():
                if cand.metadata.get("synced_at") is None:
                    results.append(cand)
                    continue
                synced_at = cand.metadata.get("synced_at")
                if isinstance(synced_at, datetime) and since and synced_at >= since:
                    results.append(cand)
            return results[:limit]

    @with_resilience(
        provider="ats_mock",
        method="push_job",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_job(self, job: Job) -> ExternalId:
        if not job.title:
            raise InvalidRequestError("job.title is required")
        with self._lock:
            ext_id = job.external_id or self._next_job_id()
            self._jobs[ext_id] = job
        return ExternalId(
            external_id=ext_id,
            external_url=f"https://mock-ats.local/jobs/{ext_id}",
        )

    @with_resilience(
        provider="ats_mock",
        method="pull_jobs",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_jobs(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())[:limit]

    @with_resilience(
        provider="ats_mock",
        method="update_status",
        retry=RetryPolicy(max_retries=1),
    )
    async def update_status(
        self,
        external_id: str,
        status: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise InvalidRequestError(
                f"invalid status {status!r}",
                details={"valid": sorted(_VALID_STATUSES)},
            )
        with self._lock:
            if external_id not in self._candidates:
                raise InvalidRequestError(
                    f"candidate {external_id} not found in mock ATS",
                )
            self._candidate_status[external_id] = CandidateStatus(
                external_id=external_id,
                status=status,
                updated_at=datetime.now(timezone.utc),
                metadata=metadata or {},
            )

    # ----- 测试辅助 -----
    def get_status(self, external_id: str) -> CandidateStatus | None:
        with self._lock:
            return self._candidate_status.get(external_id)

    def seed_candidate(self, candidate: Candidate, external_id: str) -> None:
        with self._lock:
            self._candidates[external_id] = candidate

    def seed_job(self, job: Job, external_id: str) -> None:
        with self._lock:
            self._jobs[external_id] = job