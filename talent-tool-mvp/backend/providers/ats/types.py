"""ATS Provider 统一数据类型.

外部 ATS (Greenhouse / Lever / Workday / iCIMS) 都通过这一组 dataclass 暴露,
业务层在做"上传候选人 / 拉取职位"等操作时无需感知供应商差异.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ExternalId:
    """供应商系统内主键."""

    external_id: str
    external_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Candidate:
    """候选人 (简化字段, 详细简历另行处理)."""

    name: str
    email: str
    phone: str | None = None
    external_id: str | None = None  # 已存在时由 push 返回
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    resume_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Job:
    """职位."""

    title: str
    description: str
    location: str | None = None
    department: str | None = None
    employment_type: str | None = None  # full_time / part_time / contract
    external_id: str | None = None
    status: str = "open"  # open / closed / draft
    url: str | None = None
    opened_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateStatus:
    """候选人在 ATS 流程中的状态变更."""

    external_id: str
    status: str  # new / screening / interview / offer / hired / rejected
    stage: str | None = None
    updated_at: datetime | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)