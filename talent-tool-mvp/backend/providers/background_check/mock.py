"""BackgroundCheck Provider Mock 实现."""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone

from ..base import RetryPolicy, with_resilience
from ..exceptions import InvalidRequestError
from .base import BackgroundCheckProvider
from .types import Check, CheckStatus, CheckType


_VALID_CHECK_CODES = {
    "criminal",
    "employment",
    "education",
    "reference",
    "credit",
    "identity",
    "motor_vehicle",
}


class MockBackgroundCheckProvider(BackgroundCheckProvider):
    """Mock 实现,内存保存背调任务 + 状态."""

    provider_name = "mock_bg_check"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._checks: dict[str, Check] = {}
        self._statuses: dict[str, CheckStatus] = {}

    @with_resilience(
        provider="bg_check_mock",
        method="initiate_check",
        retry=RetryPolicy(max_retries=2),
    )
    async def initiate_check(
        self,
        candidate_id: str,
        check_types: list[CheckType],
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Check:
        if not candidate_id:
            raise InvalidRequestError("candidate_id is required")
        if not check_types:
            raise InvalidRequestError("check_types must not be empty")
        invalid = [c.code for c in check_types if c.code not in _VALID_CHECK_CODES]
        if invalid:
            raise InvalidRequestError(
                f"invalid check_types {invalid}",
                details={"valid": sorted(_VALID_CHECK_CODES)},
            )
        check_id = f"chk_mock_{secrets.token_hex(6)}"
        now = datetime.now(timezone.utc)
        check = Check(
            check_id=check_id,
            candidate_id=candidate_id,
            status="pending",
            check_types=[c.code for c in check_types],
            created_at=now,
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "candidate_email": candidate_email or "",
                "candidate_name": candidate_name or "",
            },
        )
        with self._lock:
            self._checks[check_id] = check
        return check

    @with_resilience(
        provider="bg_check_mock",
        method="get_status",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_status(self, check_id: str) -> CheckStatus:
        with self._lock:
            if check_id not in self._checks:
                raise InvalidRequestError(
                    f"check {check_id} not found",
                    provider=self.provider_name,
                )
            cached = self._statuses.get(check_id)
        if cached is not None:
            return cached
        # 默认 pending 状态
        return CheckStatus(
            check_id=check_id,
            candidate_id="",
            status="pending",
            progress_pct=0.0,
            updated_at=datetime.now(timezone.utc),
            provider=self.provider_name,
        )

    # ----- 测试辅助 -----
    def seed_status(
        self,
        check_id: str,
        *,
        status: str = "clear",
        progress_pct: float = 100.0,
        with_report: bool = True,
    ) -> CheckStatus:
        cs = CheckStatus(
            check_id=check_id,
            candidate_id="",
            status=status,
            progress_pct=progress_pct,
            report_url=f"https://mock-bgcheck.local/reports/{check_id}" if with_report else None,
            updated_at=datetime.now(timezone.utc),
            provider=self.provider_name,
        )
        with self._lock:
            self._statuses[check_id] = cs
        return cs