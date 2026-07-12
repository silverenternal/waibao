"""BackgroundCheck Provider 统一数据类型.

外部背调供应商 (Checkr / iCIMS / HireRight / 中华背调) 都使用这一组结构.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CheckType:
    """背调类型定义."""

    code: str  # criminal / employment / education / reference / credit
    name: str = ""
    required: bool = True


@dataclass(slots=True)
class Check:
    """背调任务."""

    check_id: str
    candidate_id: str
    status: str = "pending"  # pending / in_progress / clear / consider / suspended
    check_types: list[str] = field(default_factory=list)
    report_url: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    provider: str = "mock"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CheckStatus:
    """背调当前状态(单独 query 用)."""

    check_id: str
    candidate_id: str
    status: str  # pending / in_progress / clear / consider / suspended
    progress_pct: float = 0.0
    report_url: str | None = None
    findings: list["Finding"] = field(default_factory=list)
    updated_at: datetime | None = None
    provider: str = "mock"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Finding:
    """背调发现项."""

    code: str
    severity: str  # info / minor / major / critical
    description: str = ""
    category: str | None = None