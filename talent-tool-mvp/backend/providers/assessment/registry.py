"""Assessment Provider 子注册中心 (T1306).

按 ASSESSMENT_PROVIDER env 返回:beisen / mock.
凭证缺失 / 真实供应商错误时 fallback MockAssessmentProvider.
"""
from __future__ import annotations

import os
from threading import Lock

from ..exceptions import InvalidRequestError, ProviderError
from .base import AssessmentProvider
from .mock import MockAssessmentProvider

_assessment: AssessmentProvider | None = None
_lock = Lock()


def get_assessment_provider() -> AssessmentProvider:
    global _assessment
    if _assessment is not None:
        return _assessment
    with _lock:
        if _assessment is not None:
            return _assessment
        name = (os.getenv("ASSESSMENT_PROVIDER") or "mock").lower()
        if name == "mock":
            _assessment = MockAssessmentProvider()
            return _assessment
        if name == "beisen":
            from .beisen import BeisenProvider
            try:
                _assessment = BeisenProvider()
                if not _assessment._configured():  # type: ignore[attr-defined]
                    raise InvalidRequestError(
                        "Beisen credentials missing",
                        details={"env": [
                            "BEISEN_APP_ID", "BEISEN_APP_SECRET",
                        ]},
                    )
            except ProviderError:
                _assessment = MockAssessmentProvider()
            return _assessment
        raise InvalidRequestError(
            f"unknown ASSESSMENT_PROVIDER={name}",
            details={"supported": ["beisen", "mock"]},
        )


def reset_cache() -> None:
    global _assessment
    with _lock:
        _assessment = None


__all__ = ["get_assessment_provider", "reset_cache"]
