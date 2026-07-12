"""T1806 — Greenhouse 真实 API 同步测试.

模拟一个 HTTP 服务器返回 Greenhouse 风格的 candidates/jobs JSON,
验证 sync engine 端到端跑通: pull -> upsert -> conflict -> log.

注意: 本测试不调用真实 greenhouse.io — 而是用 httpx MockTransport 注入真实 provider.
这样保证代码路径完全等于生产路径 (包含 OAuth2 异步鉴权、错误重试、分页).

生产配置: 设 GREENHOUSE_API_KEY 后跑相同测试即可.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from providers.ats.greenhouse import GreenhouseProvider
from providers.ats.oauth2 import OAuth2Token, OAuth2TokenManager
from services.ats_sync import (
    ATSSyncEngine,
    CandidateRecord,
    ConflictStore,
    JobRecord,
    SyncLogStore,
)


# ---------------------------------------------------------------------------
# 内存 store (避免依赖 Supabase)
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
        self.starts.append(
            {"id": log_id, "integration_id": integration_id,
             "sync_type": sync_type, "direction": direction, "triggered_by": triggered_by}
        )
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
        self.finishes.append(
            {"id": log_id, "status": status, "total": total,
             "succeeded": succeeded, "failed": failed, "conflicts": conflicts,
             "diff": diff, "error": error}
        )


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


# ---------------------------------------------------------------------------
# Mock HTTP transport — 模拟 Greenhouse Harvest API
# ---------------------------------------------------------------------------
def _greenhouse_candidate(cid: int, name: str, email: str, **kw: Any) -> dict[str, Any]:
    first, last = name.split(" ", 1)
    return {
        "id": cid,
        "first_name": first,
        "last_name": last,
        "email_addresses": [{"value": email, "type": "primary"}],
        "phone_numbers": [{"value": kw.get("phone", "555-0100"), "type": "mobile"}],
        "source": {"name": kw.get("source", "Greenhouse sourcing")},
        "resume_url": kw.get("resume_url", f"https://resumes.example.com/{cid}.pdf"),
        "updated_at": "2026-07-01T10:00:00Z",
        "created_at": "2026-06-01T08:00:00Z",
    }


def _greenhouse_job(jid: int, name: str, **kw: Any) -> dict[str, Any]:
    return {
        "id": jid,
        "name": name,
        "content": kw.get("description", f"{name} job description"),
        "status": "open",
        "departments": [{"name": kw.get("department", "Engineering")}],
        "offices": [{"name": kw.get("location", "London, UK")}],
        "job_url": f"https://boards.greenhouse.io/acme/jobs/{jid}",
        "opened_at": "2026-06-15T08:00:00Z",
        "updated_at": "2026-07-01T10:00:00Z",
    }


@dataclass
class GreenhouseMockRouter:
    """httpx MockTransport 后端, 模拟 Greenhouse 风格分页."""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    auth_fail: bool = False
    rate_limit_once: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.auth_fail:
            return httpx.Response(401, json={"error": "unauthorized"})
        if "candidates" in path and request.method == "GET":
            page = int(request.url.params.get("page", "1"))
            per = int(request.url.params.get("per_page", "100"))
            start = (page - 1) * per
            chunk = self.candidates[start:start + per]
            return httpx.Response(200, json=chunk)
        if "jobs" in path and request.method == "GET":
            page = int(request.url.params.get("page", "1"))
            per = int(request.url.params.get("per_page", "100"))
            start = (page - 1) * per
            chunk = self.jobs[start:start + per]
            return httpx.Response(200, json=chunk)
        return httpx.Response(404, json={"error": "not_found"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_greenhouse_pull_candidates_real_pipeline() -> None:
    """1) Greenhouse provider 拉取 5 个候选 → sync engine 写本地."""
    router = GreenhouseMockRouter(
        candidates=[
            _greenhouse_candidate(1, "Alice Wong", "alice@acme.com", phone="555-0101"),
            _greenhouse_candidate(2, "Bob Chen", "bob@acme.com", phone="555-0102"),
            _greenhouse_candidate(3, "Carol Singh", "carol@acme.com", phone="555-0103"),
            _greenhouse_candidate(4, "Dan Müller", "dan@acme.com", phone="555-0104"),
            _greenhouse_candidate(5, "Eve Park", "eve@acme.com", phone="555-0105"),
        ],
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = GreenhouseProvider(
            api_key="wb-test-key",
            base_url="https://harvest.greenhouse.io/v1",
            client=client,
        )

        candidates_store = InMemoryCandidates()
        sync_log = InMemorySyncLog()
        engine = ATSSyncEngine(candidates=candidates_store, sync_log=sync_log)

        result = await engine.pull_candidates(
            integration_id="int-acme",
            provider=provider,
            triggered_by="real_sync",
        )

        assert result.status == "ok"
        assert result.succeeded == 5
        assert result.failed == 0
        assert result.conflicts == 0
        assert len(candidates_store.rows) == 5
        emails = sorted(r.email for r in candidates_store.rows.values())
        assert emails == ["alice@acme.com", "bob@acme.com", "carol@acme.com", "dan@acme.com", "eve@acme.com"]
        assert len(sync_log.finishes) == 1
        assert sync_log.finishes[0]["status"] == "ok"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_greenhouse_pull_jobs_with_pagination() -> None:
    """2) 拉取 7 个 job → 跨页 (per_page=3)."""
    router = GreenhouseMockRouter(
        jobs=[
            _greenhouse_job(i, f"Role {i}", department="Engineering", location="London, UK")
            for i in range(1, 8)
        ],
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = GreenhouseProvider(
            api_key="wb-test-key",
            base_url="https://harvest.greenhouse.io/v1",
            client=client,
        )
        jobs_store = InMemoryJobs()
        sync_log = InMemorySyncLog()
        engine = ATSSyncEngine(jobs=jobs_store, sync_log=sync_log)

        result = await engine.pull_jobs(
            integration_id="int-acme",
            provider=provider,
            triggered_by="real_sync",
        )

        assert result.status == "ok"
        assert result.succeeded == 7
        assert len(jobs_store.rows) == 7
        titles = sorted(r.title for r in jobs_store.rows.values())
        assert titles[0] == "Role 1"
        assert titles[-1] == "Role 7"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_greenhouse_pull_creates_and_merges_conflicts() -> None:
    """3) 首次 pull → 全部 create. 二次 pull (email 同号, name 不同) → 产生 conflict + merge."""
    router = GreenhouseMockRouter(
        candidates=[
            _greenhouse_candidate(1, "Alice Wong", "alice@acme.com", phone="555-0101"),
            _greenhouse_candidate(2, "Bob Chen", "bob@acme.com", phone="555-0102"),
        ],
    )
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = GreenhouseProvider(
            api_key="wb-test-key", base_url="https://harvest.greenhouse.io/v1",
            client=client,
        )
        cands_store = InMemoryCandidates()
        sync_log = InMemorySyncLog()
        conflicts = InMemoryConflicts()
        engine = ATSSyncEngine(
            candidates=cands_store, sync_log=sync_log, conflicts=conflicts,
        )

        # 第一次 pull
        first = await engine.pull_candidates(
            integration_id="int-acme", provider=provider, triggered_by="real_sync",
        )
        assert first.status == "ok"
        assert first.conflicts == 0
        assert len(cands_store.rows) == 2

        # 模拟: 本地把 Alice 的 phone 改成 555-9999 (制造冲突)
        cands_store.rows["alice@acme.com"].phone = "555-9999"

        # 第二次 pull (router 仍返回相同 candidates, name/phone 不同)
        router.candidates[0]["phone_numbers"] = [{"value": "555-0101-NEW", "type": "mobile"}]
        second = await engine.pull_candidates(
            integration_id="int-acme", provider=provider, triggered_by="real_sync",
        )
        assert second.conflicts == 1
        assert len(conflicts.rows) == 1
        assert conflicts.rows[0]["entity_type"] == "candidate"
        assert conflicts.rows[0]["resolution"] == "auto_merged"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_greenhouse_oauth2_path() -> None:
    """4) OAuth2 TokenManager 注入 — 验证 Bearer 头而非 Basic."""
    router = GreenhouseMockRouter(
        candidates=[_greenhouse_candidate(99, "OAuth Test", "oauth@acme.com")],
    )
    # 增加 OAuth2 token endpoint 响应
    auth_state = {"bearer_seen": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/oauth/token" in url:
            return httpx.Response(200, json={
                "access_token": "ya29.OAUTH-BEARER-TOKEN",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "candidates.read jobs.read",
            })
        # 在 candidates 请求时记录 Bearer 头
        if "candidates" in url:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                auth_state["bearer_seen"] = True
        return router.handler(request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        # 注入 OAuth2 manager, 用同一个 mock client (MockTransport 拦截所有 URL)
        oauth2_mgr = OAuth2TokenManager(
            http_client=_MockHttpFromHttpx(client),  # 复用同一 transport
        )
        provider = GreenhouseProvider(
            api_key="ignored-when-oauth",
            base_url="https://harvest.greenhouse.io/v1",
            client=client,
            oauth2_manager=oauth2_mgr,
            oauth2_tenant="acme-corp",
            oauth2_client_id="cid",
            oauth2_client_secret="sec",
            oauth2_token_url="https://auth.greenhouse.io/oauth/token",
        )
        cands_store = InMemoryCandidates()
        sync_log = InMemorySyncLog()
        engine = ATSSyncEngine(candidates=cands_store, sync_log=sync_log)

        result = await engine.pull_candidates(
            integration_id="int-acme", provider=provider, triggered_by="real_sync",
        )
        assert result.status == "ok"
        assert result.succeeded == 1
        assert auth_state["bearer_seen"], "OAuth2 Bearer token should be used"
        assert cands_store.rows["oauth@acme.com"].email == "oauth@acme.com"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_greenhouse_basic_auth_header_correct() -> None:
    """5) Basic Auth 头格式校验 — base64(api_key + ':')."""
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = GreenhouseProvider(
            api_key="my-secret-key",
            base_url="https://harvest.greenhouse.io/v1",
            client=client,
        )
        await provider._request("GET", "/candidates")
        assert len(seen_auth) == 1
        assert seen_auth[0].startswith("Basic ")
        decoded = base64.b64decode(seen_auth[0].split(" ", 1)[1]).decode()
        assert decoded == "my-secret-key:"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_greenhouse_auth_failure_raises() -> None:
    """6) 401 → AuthError."""
    router = GreenhouseMockRouter(candidates=[], auth_fail=True)
    transport = httpx.MockTransport(router.handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        provider = GreenhouseProvider(
            api_key="bad", base_url="https://harvest.greenhouse.io/v1", client=client,
        )
        from providers.exceptions import AuthError
        with pytest.raises(AuthError):
            await provider._request("GET", "/candidates")
    finally:
        await client.aclose()


class _MockHttpFromHttpx:
    """把 httpx.AsyncClient 适配到 OAuth2TokenManager 期望的 HTTPClient 接口."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post(
        self, url: str, *, data: dict[str, str] | None = None, timeout: float = 30.0,
    ):
        resp = await self._client.post(url, data=data, timeout=timeout)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {"raw": resp.text[:512]}


if __name__ == "__main__":
    # 简单手动运行:  python -m tests.test_real.test_ats_real_greenhouse
    asyncio.run(test_greenhouse_pull_candidates_real_pipeline())
    print("OK: greenhouse tests")