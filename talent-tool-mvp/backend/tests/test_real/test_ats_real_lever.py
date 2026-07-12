"""T1806 — Lever 真实 API 同步测试.

模拟 Lever 风格的 candidates/postings JSON 响应, 验证 sync engine 端到端.
Lever 用 next-cursor 分页 + contact.emails[] 结构.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from providers.ats.lever import LeverProvider
from providers.ats.oauth2 import OAuth2TokenManager
from providers.exceptions import AuthError
from services.ats_sync import (
    ATSSyncEngine,
    CandidateRecord,
    ConflictStore,
    JobRecord,
    SyncLogStore,
)


# ---------------------------------------------------------------------------
# 内存 store
# ---------------------------------------------------------------------------
@dataclass
class InMemoryCandidates:
    rows: dict[str, CandidateRecord] = field(default_factory=dict)
    upsert_log: list[CandidateRecord] = field(default_factory=list)

    async def list_candidates(self, *, integration_id: str) -> list[CandidateRecord]:
        return list(self.rows.values())

    async def upsert_candidate(
        self, record: CandidateRecord, integration_id: str
    ) -> CandidateRecord:
        record.id = record.id or record.email
        self.rows[record.id] = record
        self.upsert_log.append(record)
        return record


@dataclass
class InMemoryJobs:
    rows: dict[str, JobRecord] = field(default_factory=dict)

    async def list_jobs(self, *, integration_id: str) -> list[JobRecord]:
        return list(self.rows.values())

    async def upsert_job(
        self, record: JobRecord, integration_id: str
    ) -> JobRecord:
        record.id = record.id or record.external_id or record.title
        self.rows[record.id] = record
        return record


@dataclass
class InMemorySyncLog:
    starts: list[dict[str, Any]] = field(default_factory=list)
    finishes: list[dict[str, Any]] = field(default_factory=list)

    async def start_log(
        self, integration_id: str, sync_type: str, direction: str, triggered_by: str
    ) -> str:
        log_id = f"log-{len(self.starts) + 1}"
        self.starts.append({"id": log_id, "integration_id": integration_id, "sync_type": sync_type})
        return log_id

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
        self.finishes.append({"id": log_id, "status": status, "total": total})


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
        self.rows.append({"entity_type": entity_type, "resolution": resolution})


# ---------------------------------------------------------------------------
# Mock Lever transport
# ---------------------------------------------------------------------------
def _lever_candidate(cid: str, name: str, email: str, **kw: Any) -> dict[str, Any]:
    first, last = name.split(" ", 1)
    return {
        "id": cid,
        "first_name": first,
        "last_name": last,
        "contact": {
            "emails": [email],
            "phoneNumbers": [{"value": kw.get("phone", "555-0200")}],
        },
        "sources": kw.get("source", "LinkedIn"),
        "resume": kw.get("resume_url", f"https://resumes.example.com/{cid}.pdf"),
        "stage": "new",
        "archived": False,
        "tags": kw.get("tags", ["v3.0", "ats-sync"]),
        "createdAt": 1717200000000,
        "updatedAt": 1720000000000,
    }


def _lever_posting(pid: str, title: str, **kw: Any) -> dict[str, Any]:
    return {
        "id": pid,
        "text": title,
        "state": kw.get("state", "published"),
        "location": kw.get("location", "Remote, UK"),
        "categories": {
            "department": kw.get("department", "Engineering"),
            "commitment": kw.get("commitment", "Full-time"),
        },
        "content": {"description": kw.get("description", f"{title} description")},
        "hostedUrl": f"https://jobs.lever.co/{pid}",
        "applyUrl": f"https://jobs.lever.co/{pid}/apply",
        "createdAt": 1717200000000,
        "updatedAt": 1720000000000,
    }


@dataclass
class LeverMockRouter:
    """Lever 用 next-cursor 分页 + data envelope."""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    postings: list[dict[str, Any]] = field(default_factory=list)
    auth_fail: bool = False
    page_size: int = 2

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.auth_fail:
            return httpx.Response(401, json={"error": "invalid api key"})
        path = request.url.path
        offset = request.url.params.get("offset")
        if "candidates" in path and request.method == "GET":
            return self._paginated(self.candidates, offset)
        if "postings" in path and request.method == "GET":
            return self._paginated(self.postings, offset)
        return httpx.Response(404, json={"error": "not_found"})

    def _paginated(self, rows: list[dict[str, Any]], offset: str | None) -> httpx.Response:
        start = int(offset) if offset else 0
        end = start + self.page_size
        chunk = rows[start:end]
        next_token = str(end) if end < len(rows) else None
        body: dict[str, Any] = {"data": chunk}
        if next_token:
            body["next"] = next_token
        return httpx.Response(200, json=body)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lever_pull_candidates_real_pipeline() -> None:
    """1) Lever provider 拉取 6 个候选 → 跨 3 页 (page_size=2)."""
    router = LeverMockRouter(
        candidates=[
            _lever_candidate(f"lev-{i}", f"User {i}", f"user{i}@globex.com", phone=f"555-020{i}")
            for i in range(1, 7)
        ],
        page_size=2,
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = LeverProvider(
            api_key="wb-test-lever-key",
            base_url="https://api.lever.co/v1",
            client=client,
        )
        cands_store = InMemoryCandidates()
        sync_log = InMemorySyncLog()
        engine = ATSSyncEngine(candidates=cands_store, sync_log=sync_log)

        result = await engine.pull_candidates(
            integration_id="int-globex", provider=provider, triggered_by="real_sync",
        )
        assert result.status == "ok"
        assert result.succeeded == 6
        assert len(cands_store.rows) == 6
        emails = sorted(r.email for r in cands_store.rows.values())
        assert emails[0] == "user1@globex.com"
        assert emails[-1] == "user6@globex.com"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lever_pull_postings() -> None:
    """2) Pull postings → 本地 jobs 表写入."""
    router = LeverMockRouter(
        postings=[
            _lever_posting("posting-1", "Senior Backend Engineer", department="Engineering"),
            _lever_posting("posting-2", "Product Designer", department="Design"),
            _lever_posting("posting-3", "Customer Success Lead", department="Ops"),
            _lever_posting("posting-4", "Data Scientist", department="Data"),
        ],
        page_size=2,
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = LeverProvider(
            api_key="wb-test-lever-key",
            base_url="https://api.lever.co/v1",
            client=client,
        )
        jobs_store = InMemoryJobs()
        sync_log = InMemorySyncLog()
        engine = ATSSyncEngine(jobs=jobs_store, sync_log=sync_log)

        result = await engine.pull_jobs(
            integration_id="int-globex", provider=provider, triggered_by="real_sync",
        )
        assert result.status == "ok"
        assert result.succeeded == 4
        titles = sorted(r.title for r in jobs_store.rows.values())
        assert "Product Designer" in titles
        assert "Senior Backend Engineer" in titles
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lever_basic_auth_header_correct() -> None:
    """3) Basic Auth 头 = base64(api_key + ':')."""
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = LeverProvider(
            api_key="lever-secret-1", base_url="https://api.lever.co/v1", client=client,
        )
        await provider._request("GET", "/candidates")
        assert seen_auth[0].startswith("Basic ")
        decoded = base64.b64decode(seen_auth[0].split(" ", 1)[1]).decode()
        assert decoded == "lever-secret-1:"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lever_oauth2_bearer_path() -> None:
    """4) OAuth2 TokenManager 注入 — Bearer 头 + 自动 refresh."""
    bearer_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/oauth/token" in url:
            return httpx.Response(200, json={
                "access_token": "BEARER-LEVER-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "candidates:read",
            })
        if "candidates" in url:
            bearer_seen.append(request.headers.get("Authorization", ""))
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={"error": "not_found"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        # 共享同一 MockTransport
        class _Adapter:
            def __init__(self, c): self._c = c
            async def post(self, url, *, data=None, timeout=30.0):
                resp = await self._c.post(url, data=data, timeout=timeout)
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    return resp.status_code, {"raw": resp.text[:512]}

        mgr = OAuth2TokenManager(http_client=_Adapter(client))
        provider = LeverProvider(
            api_key="ignored",
            base_url="https://api.lever.co/v1",
            client=client,
            oauth2_manager=mgr,
            oauth2_tenant="globex",
            oauth2_client_id="cid",
            oauth2_client_secret="sec",
            oauth2_token_url="https://auth.lever.co/oauth/token",
        )
        await provider._request("GET", "/candidates")
        assert len(bearer_seen) == 1
        assert bearer_seen[0] == "Bearer BEARER-LEVER-1"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lever_pull_candidates_then_conflict() -> None:
    """5) Pull → 本地修改 → 二次 pull → conflict."""
    router = LeverMockRouter(
        candidates=[
            _lever_candidate("l-1", "Frank Wright", "frank@globex.com", phone="555-0210"),
            _lever_candidate("l-2", "Grace Lin", "grace@globex.com", phone="555-0211"),
        ],
        page_size=10,
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = LeverProvider(
            api_key="k", base_url="https://api.lever.co/v1", client=client,
        )
        cands_store = InMemoryCandidates()
        sync_log = InMemorySyncLog()
        conflicts = InMemoryConflicts()
        engine = ATSSyncEngine(
            candidates=cands_store, sync_log=sync_log, conflicts=conflicts,
        )
        first = await engine.pull_candidates(
            integration_id="i", provider=provider, triggered_by="real_sync",
        )
        assert first.conflicts == 0
        # 二次 pull: 远端 phone 改了
        router.candidates[0]["contact"]["phoneNumbers"] = [{"value": "555-0210-NEW"}]
        second = await engine.pull_candidates(
            integration_id="i", provider=provider, triggered_by="real_sync",
        )
        assert second.conflicts == 1
        assert len(conflicts.rows) == 1
        assert conflicts.rows[0]["entity_type"] == "candidate"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_lever_auth_failure() -> None:
    """6) 401 → AuthError."""
    router = LeverMockRouter(candidates=[], postings=[], auth_fail=True)
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = LeverProvider(
            api_key="bad", base_url="https://api.lever.co/v1", client=client,
        )
        with pytest.raises(AuthError):
            await provider._request("GET", "/candidates")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(test_lever_basic_auth_header_correct())
    print("OK: lever tests")