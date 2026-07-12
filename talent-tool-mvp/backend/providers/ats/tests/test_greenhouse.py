"""Greenhouse Provider tests (httpx mock transport)."""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from providers.ats.greenhouse import GreenhouseProvider
from providers.ats.types import Candidate, Job
from providers.exceptions import AuthError, InvalidRequestError, RateLimitError


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        return await self.handler(request)


def _make_provider(handler) -> tuple[GreenhouseProvider, _MockTransport]:
    transport = _MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    p = GreenhouseProvider(
        api_key="gh-test-key",
        base_url="https://harvest.example.com/v1",
        client=client,
    )
    return p, transport


@pytest.mark.asyncio
async def test_push_candidate_creates_new() -> None:
    async def handler(req: httpx.Request):
        if req.url.path == "/v1/candidates" and req.method == "GET":
            return httpx.Response(200, json=[])
        if req.url.path == "/v1/candidates" and req.method == "POST":
            body = json.loads(req.content or b"{}")
            return httpx.Response(201, json={"id": 1001, "first_name": body["first_name"]})
        return httpx.Response(404, json={})

    p, transport = _make_provider(handler)
    try:
        result = await p.push_candidate(
            Candidate(name="Jane Smith", email="jane@example.com")
        )
    finally:
        await p.aclose()

    assert result.external_id == "1001"
    assert "1001" in (result.external_url or "")
    assert any(c == ("POST", "/v1/candidates") for c in transport.calls)


@pytest.mark.asyncio
async def test_push_candidate_dedup_via_get() -> None:
    async def handler(req: httpx.Request):
        if req.url.path == "/v1/candidates" and req.method == "GET":
            return httpx.Response(
                200,
                json=[{"id": 999, "first_name": "Jane", "last_name": "Smith", "email_addresses": [{"value": "jane@example.com"}]}],
            )
        return httpx.Response(404, json={})

    p, transport = _make_provider(handler)
    try:
        result = await p.push_candidate(
            Candidate(name="Jane Smith", email="jane@example.com")
        )
    finally:
        await p.aclose()
    assert result.external_id == "999"
    assert not any(c == ("POST", "/v1/candidates") for c in transport.calls)


@pytest.mark.asyncio
async def test_push_candidate_requires_email() -> None:
    p = GreenhouseProvider(api_key="k")
    with pytest.raises(InvalidRequestError):
        await p.push_candidate(Candidate(name="no email", email=""))
    await p.aclose()


@pytest.mark.asyncio
async def test_pull_candidates_parses_payload() -> None:
    async def handler(req: httpx.Request):
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "first_name": "A",
                    "last_name": "B",
                    "email_addresses": [{"value": "a@b.com", "type": "primary"}],
                    "phone_numbers": [{"value": "+1"}],
                    "resume_url": "https://r.example.com/x.pdf",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ],
        )

    p, _ = _make_provider(handler)
    try:
        results = await p.pull_candidates()
    finally:
        await p.aclose()
    assert len(results) == 1
    assert results[0].email == "a@b.com"
    assert results[0].phone == "+1"
    assert results[0].external_id == "1"


@pytest.mark.asyncio
async def test_push_and_pull_jobs() -> None:
    async def handler(req: httpx.Request):
        if req.url.path == "/v1/jobs" and req.method == "POST":
            return httpx.Response(201, json={"id": 500})
        if req.url.path == "/v1/jobs" and req.method == "GET":
            return httpx.Response(200, json=[{"id": 500, "name": "X", "content": "y"}])
        return httpx.Response(404)

    p, _ = _make_provider(handler)
    try:
        created = await p.push_job(Job(title="X", description="y"))
        jobs = await p.pull_jobs()
    finally:
        await p.aclose()
    assert created.external_id == "500"
    assert jobs and jobs[0].title == "X"


@pytest.mark.asyncio
async def test_auth_error_unauthorized() -> None:
    async def handler(req: httpx.Request):
        return httpx.Response(401, json={"error": "nope"})

    p, _ = _make_provider(handler)
    try:
        with pytest.raises(AuthError):
            await p.pull_candidates()
    finally:
        await p.aclose()


@pytest.mark.asyncio
async def test_rate_limit_is_retryable() -> None:
    async def handler(req: httpx.Request):
        return httpx.Response(429, json={"error": "slow down"})

    p, _ = _make_provider(handler)
    try:
        with pytest.raises(RateLimitError):
            await p.pull_candidates()
    finally:
        await p.aclose()


@pytest.mark.asyncio
async def test_basic_auth_header_value() -> None:
    async def handler(req: httpx.Request):
        # Verify Basic token format
        auth = req.headers.get("Authorization")
        token = auth.replace("Basic ", "")
        decoded = base64.b64decode(token).decode()
        assert decoded == "gh-test-key:"
        return httpx.Response(200, json=[])

    p, _ = _make_provider(handler)
    try:
        await p.pull_candidates()
    finally:
        await p.aclose()
