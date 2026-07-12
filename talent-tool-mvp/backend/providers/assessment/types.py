"""Assessment Provider 统一数据类型.

外部测评平台 (北森 / 光辉国际 / HackerRank / Codility) 都使用这一组结构.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Invitation:
    """测评邀请."""

    invitation_id: str
    candidate_id: str
    assessment_id: str
    status: str = "pending"  # pending / started / submitted / expired / canceled
    invite_url: str | None = None
    expires_at: datetime | None = None
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    provider: str = "mock"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Score:
    """单维度分数."""

    name: str
    value: float
    max: float = 100.0
    band: str | None = None  # low / mid / high / top


@dataclass(slots=True)
class AssessmentResult:
    """测评结果."""

    invitation_id: str
    candidate_id: str
    assessment_id: str
    status: str  # pending / submitted / scored / expired
    overall_score: float | None = None
    percentile: float | None = None
    passed: bool | None = None
    scores: list[Score] = field(default_factory=list)
    report_url: str | None = None
    completed_at: datetime | None = None
    provider: str = "mock"
    raw: dict[str, Any] = field(default_factory=dict)