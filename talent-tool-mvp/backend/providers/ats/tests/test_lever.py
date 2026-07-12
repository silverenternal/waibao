"""Lever Provider tests (httpx mock transport)."""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from providers.ats.lever import LeverProvider
from providers.ats.types import Candidate, Job
from providers.exceptions import AuthError, InvalidRequestError


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        return await self.handler(request)


def _make_provider(handler) -> tuple[LeverProvider, _MockTransport]:
    transport = _MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    p = LeverProvider(
        api_key="lv-test-key",
        base_url="https://api.example.com/v1",
        client=client,
    )
    return p, transport


@pytest.mark.asyncio
async def test_push_candidate_basic() -> None:
    async def handler(req: httpx.Request):
        if req.url.path == "/v1/candidates":
            body = json.loads(req.content or b"{}")
            assert body["firstName"] == "Jane"
            return httpx.Response(201, json={"data": {"id": "p_abc123"}})
        return httpx.Response(404, json={})

    p, t = _make_provider(handler)
    try:
        result = await p.push_candidate(Candidate(name="Jane Doe", email="j@x.com"))
    finally:
        await p.aclose()
    assert result.external_id == "p_abc123"
    assert any(c == ("POST", "/v1/candidates") for c in t.calls)


@pytest.mark.asyncio
async def test_pull_candidates_handles_pagination_with_next() -> None:
    call_count = {"n": 0}

    async def handler(req: httpx.Request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, json={
                "data": [
                    {"id": "c1", "first_name": "A", "last_name": "B", "contact": {"emails": ["a@b.com"]}},
                ],
                "next": "NEXT_TOKEN",
            })
        # 第二次无 next 表示结束
        return httpx.Response(200, json={"data": [
            {"id": "c2", "first_name": "C", "last_name": "D", "contact": {"emails": ["c@d.com"]}}
        ]})

    p, _ = _make_provider(handler)
    try:
        results = await p.pull_candidates()
    finally:
        await p.aclose()
    assert len(results) == 2
    assert results[0].external_id == "c1"
    assert results[1].external_id == "c2"


@pytest.mark.asyncio
async def test_pull_jobs_parses_postings() -> None:
    async def handler(req: httpx.Request):
        return httpx.Response(200, json={"data": [
            {"id": "j1", "text": "Engineer", "content": {"description": "do things"}, "state": "published"}
        ]})

    p, _ = _make_provider(handler)
    try:
        jobs = await p.pull_jobs()
    finally:
        await p.aclose()
    assert len(jobs) == 1
    assert jobs[0].title == "Engineer"
    assert jobs[0].status == "open"


@pytest.mark.asyncio
async def test_push_job_basic() -> None:
    async def handler(req: httpx.Request):
        if req.url.path == "/v1/postings":
            body = json.loads(req.content or b"{}")
            assert body["text"] == "Engineer"
            return httpx.Response(201, json={"data": {"id": "j_new"}})
        return httpx.Response(404, json={})

    p, _ = _make_provider(handler)
    try:
        result = await p.push_job(Job(title="Engineer", description="do things"))
    finally:
        await p.aclose()
    assert result.external_id == "j_new"


@pytest.mark.asyncio
async def test_auth_error_403() -> None:
    async def handler(req: httpx.Request):
        return httpx.Response(403, json={"error": "nope"})

    p, _ = _make_provider(handler)
    try:
        with pytest.raises(AuthError):
            await p.pull_jobs()
    finally:
        await p.aclose()


@pytest.mark.asyncio
async def test_basic_auth_header() -> None:
    async def handler(req: httpx.Request):
        auth = req.headers.get("Authorization")
        assert auth and auth.startswith("Basic ")
        decoded = base64.b64decode(auth.split(" ")[1]).decode()
        assert decoded == "lv-test-key:"
        return httpx.Response(200, json={"data": []})

    p, _ = _make_provider(handler)
    try:
        await p.pull_candidates()
    finally:
        await p.aclose()


@pytest.mark.asyncio
async def test_invalid_email_raises() -> None:
    p = LeverProvider(api_key="k")
    with pytest.raises(InvalidRequestError):
        await p.push_candidate(Candidate(name="X", email=""))
    await p.aclose()


@pytest.mark.asyncio
async def test_status_translation() -> None:
    captured = {}

    async def handler(req: httpx.Request):
        if "/transition" in req.url.path:
            body = json.loads(req.content or b"{}")
            captured["stage"] = body["stage"]
            return httpx.Response(200, json={"data": {"id": "c1"}})
        return httpx.Response(404, json={})

    p, _ = _make_provider(handler)
    try:
        await p.update_status("c1", "hired", metadata={"note": "done"})
    finally:
        await p.aclose()
    assert captured["stage"] == "hired"


@pytest.mark.asyncio
async def test_invalid_status() -> None:
    p = LeverProvider(api_key="k")
    with pytest.raises(InvalidRequestError):
        await p.update_status("c1", "unknown_status")
    await p.aclose()
