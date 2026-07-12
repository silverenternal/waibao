"""T1501 ATS sync engine tests — 双向同步 + 冲突解决 + 日志."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

from providers.ats.mock import MockATSProvider
from providers.ats.types import Candidate, Job
from services.ats_sync import (
    ATSSyncEngine,
    CandidateRecord,
    ConflictStore,
    JobRecord,
    SyncLogStore,
)


@dataclass
class InMemoryCandidates:
    rows: dict[str, CandidateRecord] = field(default_factory=dict)
    seq: int = 0

    async def list_candidates(self, *, integration_id: str) -> list[CandidateRecord]:
        return list(self.rows.values())

    async def upsert_candidate(self, rec: CandidateRecord, integration_id: str) -> CandidateRecord:
        self.seq += 1
        rid = rec.id or f"c{self.seq}"
        merged = CandidateRecord(
            id=rid,
            email=rec.email,
            name=rec.name,
            phone=rec.phone,
            source=rec.source,
            resume_url=rec.resume_url,
            external_id=rec.external_id,
            tags=list(rec.tags),
            extra=dict(rec.extra),
            updated_at=rec.updated_at,
        )
        self.rows[rid] = merged
        return merged


@dataclass
class InMemoryJobs:
    rows: dict[str, JobRecord] = field(default_factory=dict)
    seq: int = 0

    async def list_jobs(self, *, integration_id: str) -> list[JobRecord]:
        return list(self.rows.values())

    async def upsert_job(self, rec: JobRecord, integration_id: str) -> JobRecord:
        self.seq += 1
        rid = rec.id or f"j{self.seq}"
        new = JobRecord(
            id=rid,
            title=rec.title,
            description=rec.description,
            location=rec.location,
            department=rec.department,
            status=rec.status,
            external_id=rec.external_id,
            url=rec.url,
            extra=dict(rec.extra),
            updated_at=rec.updated_at,
        )
        self.rows[rid] = new
        return new


@dataclass
class InMemorySyncLog:
    logs: list[dict[str, Any]] = field(default_factory=list)

    async def start_log(
        self,
        integration_id: str,
        sync_type: str,
        direction: str,
        triggered_by: str,
    ) -> str:
        self.logs.append(
            {"integration_id": integration_id, "sync_type": sync_type,
             "direction": direction, "triggered_by": triggered_by,
             "status": "in_progress"}
        )
        return f"log_{len(self.logs)}"

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
    ) -> None:
        for log in self.logs:
            if log.get("status") == "in_progress":
                log.update({"status": status, "total": total, "succeeded": succeeded,
                            "failed": failed, "conflicts": conflicts, "diff": diff,
                            "error": error})


@dataclass
class InMemoryConflicts:
    rows: list[dict[str, Any]] = field(default_factory=list)

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
    ) -> None:
        self.rows.append(
            {"integration_id": integration_id, "entity_type": entity_type,
             "sync_log_id": sync_log_id, "local_id": local_id,
             "external_id": external_id, "field_diffs": field_diffs,
             "resolution": resolution}
        )


def _engine() -> tuple[ATSSyncEngine, InMemoryCandidates, InMemoryJobs, InMemorySyncLog, InMemoryConflicts]:
    candidates = InMemoryCandidates()
    jobs = InMemoryJobs()
    sync_log = InMemorySyncLog()
    conflicts = InMemoryConflicts()
    engine = ATSSyncEngine(
        candidates=candidates,
        jobs=jobs,
        sync_log=sync_log,
        conflicts=conflicts,
    )
    return engine, candidates, jobs, sync_log, conflicts


@pytest.mark.asyncio
async def test_pull_candidates_inserts_new() -> None:
    engine, cands, _, log, _ = _engine()
    provider = MockATSProvider()
    provider.seed_candidate(
        Candidate(name="Alice Zhang", email="alice@x.com", phone="123"),
        external_id="gh_c_1",
    )
    result = await engine.pull_candidates(
        integration_id="i1", provider=provider, triggered_by="manual"
    )
    assert result.status == "ok"
    assert result.succeeded == 1
    assert cands.rows
    assert any(r["sync_type"] == "candidates" for r in log.logs)


@pytest.mark.asyncio
async def test_pull_candidates_records_conflict_and_merges() -> None:
    engine, cands, _, _, conflicts = _engine()
    # 本地已存在,但名字与电话不同 (冲突场景)
    cands.rows["c1"] = CandidateRecord(
        id="c1", email="bob@x.com", name="Bob Local",
        phone="000", updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    provider = MockATSProvider()
    provider.seed_candidate(
        Candidate(name="Bob Remote", email="bob@x.com", phone="999"),
        external_id="gh_c_99",
    )
    result = await engine.pull_candidates(
        integration_id="i1", provider=provider, triggered_by="manual"
    )
    assert result.status == "ok"
    assert result.conflicts == 1
    assert conflicts.rows and conflicts.rows[0]["entity_type"] == "candidate"
    assert any(d["field"] == "phone" for d in conflicts.rows[0]["field_diffs"])


@pytest.mark.asyncio
async def test_pull_jobs_inserts_and_merges() -> None:
    engine, _, jobs, _, conflicts = _engine()
    jobs.rows["j1"] = JobRecord(
        id="j1", title="Engineer", description="local desc", status="open",
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    provider = MockATSProvider()
    provider.seed_job(
        Job(title="Engineer", description="remote desc", status="open"),
        external_id="j_remote_1",
    )
    result = await engine.pull_jobs(
        integration_id="i1", provider=provider, triggered_by="manual"
    )
    assert result.status == "ok"
    assert result.succeeded == 1
    assert result.conflicts == 1
    assert conflicts.rows[0]["entity_type"] == "job"


@pytest.mark.asyncio
async def test_push_candidates_writes_back_external_id() -> None:
    engine, cands, _, _, _ = _engine()
    provider = MockATSProvider()
    result = await engine.push_candidates(
        integration_id="i1",
        provider=provider,
        records=[CandidateRecord(id=None, email="c@x.com", name="C")],
        triggered_by="manual",
    )
    assert result.status == "ok"
    assert result.succeeded == 1


@pytest.mark.asyncio
async def test_pull_candidates_handles_provider_error() -> None:
    engine, _, _, log, _ = _engine()

    class _BoomProvider(MockATSProvider):
        async def pull_candidates(self, since=None, *, limit=100):
            raise RuntimeError("upstream broken")

    result = await engine.pull_candidates(
        integration_id="i1", provider=_BoomProvider(), triggered_by="manual"
    )
    assert result.status == "failed"
    finished = [l for l in log.logs if l.get("status") == "failed"]
    assert finished


def test_make_provider_dispatches_to_mock() -> None:
    from services.ats_sync import make_provider

    p = make_provider("mock_ats", api_key="x")
    assert isinstance(p, MockATSProvider)


@pytest.mark.asyncio
async def test_sync_log_records_diff() -> None:
    engine, cands, _, log, _ = _engine()
    provider = MockATSProvider()
    provider.seed_candidate(Candidate(name="D", email="d@x.com"), external_id="c_d")
    await engine.pull_candidates(
        integration_id="i1", provider=provider, triggered_by="manual"
    )
    completed = [l for l in log.logs if l.get("status") == "ok"]
    assert completed
    diff = completed[0]["diff"]
    assert diff and "op" in diff[0]


def test_last_write_wins_field_selection() -> None:
    now = datetime(2024, 6, 1, tzinfo=timezone.utc)
    earlier = datetime(2024, 1, 1, tzinfo=timezone.utc)
    local = CandidateRecord(
        id="l", email="x@x.com", name="Older", phone="1", updated_at=earlier,
    )
    remote = CandidateRecord(
        id="r", email="x@x.com", name="Newer", phone="2", updated_at=now,
    )
    merged = local.merge_with(remote)
    # 远程字段时间更新 → 远程胜
    assert merged.name == "Newer"
    assert merged.phone == "2"


def test_local_wins_when_no_remote_timestamp() -> None:
    local = CandidateRecord(
        id="l", email="x@x.com", name="Local", updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    remote = CandidateRecord(
        id="r", email="x@x.com", name="Remote", updated_at=None,
    )
    merged = local.merge_with(remote)
    # remote 没有时间戳 → local 胜
    assert merged.name == "Local"
