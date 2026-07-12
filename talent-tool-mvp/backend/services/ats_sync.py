"""T1501 — ATS 双向同步引擎.

职责:
1. 给定 ats_integrations 行, 构造对应 Provider
2. 拉取 (pull) 远端 candidates/jobs 并写入 crm.candidates (upsert by email)
3. 推送 (push) 本地变更到远端 (基于 last_pulled_at / last_synced_at)
4. 冲突解决: last-write-wins + 字段级合并 (相同时长使用本地)
5. 把 diff 详细写到 ats_sync_log, 冲突写 ats_conflicts

本服务无外部 DB 客户端依赖 — 使用传入的 store 抽象 (dataclass 风格),
便于单测。生产运行由 api/ats_integrations.py + scheduler 注入 supabase store.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from providers.ats.base import ATSProvider
from providers.ats.registry import build as build_provider
from providers.ats.types import Candidate, Job

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- data shapes
@dataclass(slots=True)
class CandidateRecord:
    """本地候选人行."""

    id: str | None
    email: str
    name: str = ""
    phone: str | None = None
    source: str | None = None
    resume_url: str | None = None
    external_id: str | None = None
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    def merge_with(self, remote: "CandidateRecord") -> "CandidateRecord":
        """last-write-wins + 字段级合并. 同字段最新时间胜出, 时间缺失时本地胜出."""
        l_time = self.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        r_time = remote.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        newer_wins = r_time > l_time
        # 合并非冲突字段
        merged_tags = sorted(set(self.tags) | set(remote.tags))
        return CandidateRecord(
            id=self.id,
            email=self.email,
            name=(remote.name if newer_wins else self.name) or self.name,
            phone=remote.phone if newer_wins else (self.phone or remote.phone),
            source=remote.source if newer_wins and remote.source else self.source,
            resume_url=remote.resume_url if newer_wins and remote.resume_url else self.resume_url,
            external_id=remote.external_id or self.external_id,
            tags=merged_tags,
            extra={**self.extra, **remote.extra},
            updated_at=max(self.updated_at, remote.updated_at) if (self.updated_at and remote.updated_at) else (remote.updated_at or self.updated_at),
        )


@dataclass(slots=True)
class JobRecord:
    id: str | None
    title: str
    description: str = ""
    location: str | None = None
    department: str | None = None
    status: str = "open"
    external_id: str | None = None
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass(slots=True)
class SyncRunResult:
    sync_log_id: str
    status: str
    total: int
    succeeded: int
    failed: int
    conflicts: int
    diff: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------- store protocol
class CandidateStore(Protocol):
    async def list_candidates(
        self, *, integration_id: str
    ) -> list[CandidateRecord]: ...
    async def upsert_candidate(
        self, record: CandidateRecord, integration_id: str
    ) -> CandidateRecord: ...


class JobStore(Protocol):
    async def list_jobs(
        self, *, integration_id: str
    ) -> list[JobRecord]: ...
    async def upsert_job(
        self, record: JobRecord, integration_id: str
    ) -> JobRecord: ...


class SyncLogStore(Protocol):
    async def start_log(
        self, integration_id: str, sync_type: str, direction: str, triggered_by: str
    ) -> str: ...
    async def finish_log(
        self,
        log_id: str,
        *,
        status: str,
        total: int,
        succeeded: int,
        failed: int,
        conflicts: int,
        diff: list[dict[str, Any]],
        error: str | None = None,
    ) -> None: ...


class ConflictStore(Protocol):
    async def record(
        self,
        integration_id: str,
        *,
        entity_type: str,
        sync_log_id: str,
        local_id: str | None,
        external_id: str,
        field_diffs: list[dict[str, Any]],
        resolution: str,
    ) -> None: ...


# ---------------------------------------------------------------- provider factory
def make_provider(provider_name: str, *, api_key: str, base_url: str | None = None) -> ATSProvider:
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return build_provider(provider_name, **kwargs)


# ---------------------------------------------------------------- engine
class ATSSyncEngine:
    """同步引擎 — 单实例方法都接受 store 以保持 stateless."""

    DEFAULT_CONFLICT_BATCH = 50

    def __init__(
        self,
        *,
        candidates: CandidateStore | None = None,
        jobs: JobStore | None = None,
        sync_log: SyncLogStore | None = None,
        conflicts: ConflictStore | None = None,
    ) -> None:
        self.candidates = candidates
        self.jobs = jobs
        self.sync_log = sync_log
        self.conflicts = conflicts

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _diff_records(
        *,
        entity_type: str,
        local: dict[str, Any],
        remote: dict[str, Any],
        keys_to_compare: Iterable[str],
    ) -> list[dict[str, Any]]:
        diffs: list[dict[str, Any]] = []
        for key in keys_to_compare:
            if local.get(key) != remote.get(key):
                diffs.append(
                    {
                        "field": key,
                        "local": local.get(key),
                        "remote": remote.get(key),
                    }
                )
        return diffs

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # ---------------------------------------------------------------- candidates
    async def pull_candidates(
        self,
        *,
        integration_id: str,
        provider: ATSProvider,
        triggered_by: str = "scheduler",
        since: datetime | None = None,
    ) -> SyncRunResult:
        assert self.candidates is not None and self.sync_log is not None
        log_id = await self.sync_log.start_log(
            integration_id, "candidates", "pull", triggered_by
        )
        diff: list[dict[str, Any]] = []
        succeeded = failed = conflicts = 0
        try:
            remote_items = await provider.pull_candidates(since=since)
            for cand in remote_items:
                remote_rec = CandidateRecord(
                    id=None,
                    email=cand.email,
                    name=cand.name,
                    phone=cand.phone,
                    source=cand.source,
                    resume_url=cand.resume_url,
                    external_id=cand.external_id,
                    tags=list(cand.tags or []),
                    extra=cand.metadata or {},
                    updated_at=self._now(),
                )
                # 找出本地匹配 (按 email 优先,external_id 次之)
                local_list = await self.candidates.list_candidates(
                    integration_id=integration_id
                )
                local_match = next(
                    (c for c in local_list if c.email == cand.email or (c.external_id and c.external_id == cand.external_id)),
                    None,
                )
                if local_match is None:
                    upserted = await self.candidates.upsert_candidate(
                        remote_rec, integration_id=integration_id
                    )
                    diff.append(
                        {"op": "create", "email": remote_rec.email, "external_id": remote_rec.external_id}
                    )
                    succeeded += 1
                else:
                    field_diffs = self._diff_records(
                        entity_type="candidate",
                        local={
                            "name": local_match.name,
                            "phone": local_match.phone,
                            "resume_url": local_match.resume_url,
                            "source": local_match.source,
                        },
                        remote={
                            "name": remote_rec.name,
                            "phone": remote_rec.phone,
                            "resume_url": remote_rec.resume_url,
                            "source": remote_rec.source,
                        },
                        keys_to_compare=("name", "phone", "resume_url", "source"),
                    )
                    if field_diffs:
                        merged = local_match.merge_with(remote_rec)
                        await self.candidates.upsert_candidate(
                            merged, integration_id=integration_id
                        )
                        conflicts += 1
                        if self.conflicts is not None:
                            await self.conflicts.record(
                                integration_id,
                                entity_type="candidate",
                                sync_log_id=log_id,
                                local_id=local_match.id,
                                external_id=remote_rec.external_id or "",
                                field_diffs=field_diffs,
                                resolution="auto_merged",
                            )
                        diff.append(
                            {
                                "op": "merge",
                                "email": remote_rec.email,
                                "external_id": remote_rec.external_id,
                                "field_diffs": field_diffs,
                            }
                        )
                    succeeded += 1
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception("ats_sync.pull_candidates_failed integration_id=%s", integration_id)
            status = "failed"
            await self.sync_log.finish_log(
                log_id,
                status=status,
                total=len(diff),
                succeeded=succeeded,
                failed=failed + 1,
                conflicts=conflicts,
                diff=diff,
                error=str(exc),
            )
            return SyncRunResult(
                sync_log_id=log_id,
                status=status,
                total=0,
                succeeded=0,
                failed=1,
                conflicts=0,
                error=str(exc),
            )

        await self.sync_log.finish_log(
            log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )
        return SyncRunResult(
            sync_log_id=log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )

    async def push_candidates(
        self,
        *,
        integration_id: str,
        provider: ATSProvider,
        records: list[CandidateRecord],
        triggered_by: str = "scheduler",
    ) -> SyncRunResult:
        assert self.sync_log is not None
        log_id = await self.sync_log.start_log(
            integration_id, "candidates", "push", triggered_by
        )
        diff: list[dict[str, Any]] = []
        succeeded = failed = conflicts = 0
        try:
            for rec in records:
                cand = Candidate(
                    name=rec.name,
                    email=rec.email,
                    phone=rec.phone,
                    external_id=rec.external_id,
                    source=rec.source,
                    resume_url=rec.resume_url,
                    tags=rec.tags,
                )
                result = await provider.push_candidate(cand)
                rec.external_id = result.external_id
                if self.candidates is not None:
                    await self.candidates.upsert_candidate(rec, integration_id=integration_id)
                diff.append({"op": "push", "email": rec.email, "external_id": result.external_id})
                succeeded += 1
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception("ats_sync.push_candidates_failed")
            status = "failed"
            failed += 1

        await self.sync_log.finish_log(
            log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )
        return SyncRunResult(
            sync_log_id=log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )

    # ---------------------------------------------------------------- jobs
    async def pull_jobs(
        self,
        *,
        integration_id: str,
        provider: ATSProvider,
        triggered_by: str = "scheduler",
        since: datetime | None = None,
    ) -> SyncRunResult:
        assert self.jobs is not None and self.sync_log is not None
        log_id = await self.sync_log.start_log(
            integration_id, "jobs", "pull", triggered_by
        )
        diff: list[dict[str, Any]] = []
        succeeded = failed = conflicts = 0
        try:
            remote_jobs = await provider.pull_jobs(since=since)
            for j in remote_jobs:
                remote_rec = JobRecord(
                    id=None,
                    title=j.title,
                    description=j.description or "",
                    location=j.location,
                    department=j.department,
                    status=j.status or "open",
                    external_id=j.external_id,
                    url=j.url,
                    extra=j.metadata or {},
                    updated_at=self._now(),
                )
                local_list = await self.jobs.list_jobs(integration_id=integration_id)
                local_match = next(
                    (x for x in local_list if x.external_id == j.external_id or (x.title == j.title and x.department == j.department)),
                    None,
                )
                if local_match is None:
                    await self.jobs.upsert_job(remote_rec, integration_id=integration_id)
                    diff.append({"op": "create", "title": j.title, "external_id": j.external_id})
                else:
                    field_diffs = self._diff_records(
                        entity_type="job",
                        local={
                            "title": local_match.title,
                            "description": local_match.description,
                            "location": local_match.location,
                            "status": local_match.status,
                        },
                        remote={
                            "title": remote_rec.title,
                            "description": remote_rec.description,
                            "location": remote_rec.location,
                            "status": remote_rec.status,
                        },
                        keys_to_compare=("title", "description", "location", "status"),
                    )
                    if field_diffs and self.conflicts is not None:
                        conflicts += 1
                        await self.conflicts.record(
                            integration_id,
                            entity_type="job",
                            sync_log_id=log_id,
                            local_id=local_match.id,
                            external_id=remote_rec.external_id or "",
                            field_diffs=field_diffs,
                            resolution="auto_merged",
                        )
                        diff.append(
                            {
                                "op": "merge",
                                "title": j.title,
                                "external_id": j.external_id,
                                "field_diffs": field_diffs,
                            }
                        )
                succeeded += 1
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            failed += 1
            await self.sync_log.finish_log(
                log_id,
                status=status,
                total=succeeded + failed,
                succeeded=succeeded,
                failed=failed,
                conflicts=conflicts,
                diff=diff,
                error=str(exc),
            )
            return SyncRunResult(
                sync_log_id=log_id, status=status, total=0,
                succeeded=0, failed=1, conflicts=0, error=str(exc),
            )

        await self.sync_log.finish_log(
            log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )
        return SyncRunResult(
            sync_log_id=log_id,
            status=status,
            total=succeeded + failed,
            succeeded=succeeded,
            failed=failed,
            conflicts=conflicts,
            diff=diff,
        )


__all__ = [
    "ATSSyncEngine",
    "CandidateRecord",
    "JobRecord",
    "SyncRunResult",
    "CandidateStore",
    "JobStore",
    "SyncLogStore",
    "ConflictStore",
    "make_provider",
]
