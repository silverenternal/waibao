"""T1501 + T1806 — Lever 真实 API Provider.

Lever ATS API:
- Base URL: https://api.lever.co/v1
- 认证: Basic Auth (api_key:``) 或 OAuth2 Bearer
- 速率: 10 req / sec (per partner-specific quota)

核心资源:
- Candidates: /candidates
- Postings: /postings  (公开职位)
- Opportunities: /opportunities  (candidate ↔ job 阶段)

实现要点:
- Lever 用 first_name / last_name 字段而非组合
- Lever 的 archived 字段控制 status
- 候选人按 email 唯一键合并
- postings.status: published / internal / closed / draft
- 阶段 (stage): 'new', 'screen', 'interview', 'offer', 'hired', 'rejected'
- T1806: 注入 OAuth2TokenManager 后用 Bearer 头
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    RateLimitError,
    UpstreamUnavailableError,
)
from .base import ATSProvider
from .oauth2 import OAuth2TokenManager
from .types import Candidate, ExternalId, Job

logger = logging.getLogger(__name__)


_LEVER_STATUS_MAP = {
    "new": "new",
    "screening": "screen",
    "interview": "interview",
    "offer": "offer",
    "hired": "hired",
    "rejected": "rejected",
}


class LeverProvider(ATSProvider):
    """Lever ATS API Provider (real or sandbox)."""

    provider_name = "lever"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.lever.co/v1",
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        oauth2_manager: OAuth2TokenManager | None = None,
        oauth2_tenant: str | None = None,
        oauth2_client_id: str | None = None,
        oauth2_client_secret: str | None = None,
        oauth2_token_url: str | None = None,
    ) -> None:
        # T1806: OAuth2 多租户支持
        if not api_key and not oauth2_manager:
            raise InvalidRequestError("lever requires api_key or oauth2_manager")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._oauth2_manager = oauth2_manager
        self._oauth2_tenant = oauth2_tenant
        self._oauth2_client_id = oauth2_client_id
        self._oauth2_client_secret = oauth2_client_secret
        self._oauth2_token_url = oauth2_token_url

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ helpers
    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(f"{self._api_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def _async_auth_header(self) -> dict[str, str]:
        """T1806: 异步鉴权 — 支持 OAuth2 Bearer."""
        if self._oauth2_manager and self._oauth2_token_url and self._oauth2_tenant:
            try:
                token = await self._oauth2_manager.get_or_refresh(
                    tenant=self._oauth2_tenant,
                    client_id=self._oauth2_client_id or "",
                    client_secret=self._oauth2_client_secret or "",
                    token_url=self._oauth2_token_url,
                )
                return {"Authorization": token.to_header()}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "lever.oauth2_fallback tenant=%s err=%s",
                    self._oauth2_tenant, exc,
                )
        return self._auth_header()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        # T1806: 异步鉴权 (OAuth2)
        headers = await self._async_auth_header()
        try:
            resp = await self._client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
            )
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"lever network error: {exc}",
                provider=self.provider_name,
            ) from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise AuthError(
                f"lever auth failed: {resp.status_code}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "1"))
            raise RateLimitError(
                "lever rate limit",
                provider=self.provider_name,
                details={"retry_after": retry_after, "status_code": 429},
            )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"lever 5xx: {resp.status_code}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise InvalidRequestError(
                f"lever {resp.status_code}: {resp.text[:200]}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    async def _next_get(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Lever 提供 next 字段 cursor 分页, 一并递归获取."""
        rows: list[dict[str, Any]] = []
        data = await self._request("GET", path, params=params)
        if isinstance(data, dict):
            rows.extend(data.get("data", []) or [])
            next_token = data.get("next")
            while next_token and len(rows) < 1000:
                data = await self._request(
                    "GET",
                    path,
                    params={**(params or {}), "offset": next_token},
                )
                if not isinstance(data, dict):
                    break
                rows.extend(data.get("data", []) or [])
                next_token = data.get("next")
        elif isinstance(data, list):
            rows.extend(data)
        return rows

    # ------------------------------------------------------------------ mapping
    @staticmethod
    def _candidate_from_lever(raw: dict[str, Any]) -> Candidate:
        contact = raw.get("contact") or {}
        emails = contact.get("emails") or []
        email = emails[0] if emails else contact.get("email", "")
        phones = contact.get("phoneNumbers") or []
        phone = phones[0].get("value") if phones else None
        return Candidate(
            name=f"{raw.get('first_name','')} {raw.get('last_name','')}".strip(),
            email=email or "",
            phone=phone,
            external_id=raw.get("id"),
            source=raw.get("sources") or None,
            tags=raw.get("tags") or [],
            resume_url=raw.get("resume"),
            metadata={
                "archived": raw.get("archived"),
                "stage": raw.get("stage"),
                "updated_at": raw.get("updatedAt"),
                "created_at": raw.get("createdAt"),
                "raw": raw,
            },
        )

    @staticmethod
    def _job_from_lever(raw: dict[str, Any]) -> Job:
        cats = raw.get("categories") or {}
        return Job(
            title=raw.get("text", ""),
            description=raw.get("content") or {},
            location=(raw.get("location") or ""),
            department=cats.get("department") or cats.get("team"),
            employment_type=cats.get("commitment"),
            external_id=raw.get("id"),
            status="closed" if raw.get("state") == "closed" else "open",
            url=raw.get("hostedUrl") or raw.get("applyUrl"),
            opened_at=raw.get("createdAt"),
            metadata={
                "updated_at": raw.get("updatedAt"),
                "raw": raw,
            },
        )

    # ------------------------------------------------------------------ API
    @with_resilience(
        provider="ats_lever",
        method="push_candidate",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_candidate(self, candidate: Candidate) -> ExternalId:
        if not candidate.email:
            raise InvalidRequestError("candidate.email is required")
        name_parts = (candidate.name or "").split(" ", 1)
        first = name_parts[0] if name_parts else "Unknown"
        last = name_parts[1] if len(name_parts) > 1 else ""
        # Lever 通过 POST /v1/candidates 添加候选人,POST 成功返回 opportunities 或 candidates
        body: dict[str, Any] = {
            "name": candidate.name or "",
            "firstName": first,
            "lastName": last,
            "email": candidate.email,
        }
        if candidate.phone:
            body["phone"] = candidate.phone
        if candidate.resume_url:
            body["resume"] = candidate.resume_url
        if candidate.source:
            body["sources"] = [candidate.source]
        # Lever POST /candidates 时也会检查重复,若重复返回 409
        data = await self._request("POST", "/candidates", json=body, params={"perform_as": "auto"})
        if isinstance(data, dict):
            cand_id = str((data.get("data") or {}).get("id", ""))
            return ExternalId(
                external_id=cand_id,
                external_url=f"https://hire.lever.co/candidates/{cand_id}" if cand_id else None,
                raw=data,
            )
        return ExternalId(external_id="")

    @with_resilience(
        provider="ats_lever",
        method="pull_candidates",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_candidates(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Candidate]:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if since is not None:
            params["updated_at_start"] = int(since.timestamp() * 1000)
        rows = await self._next_get("/candidates", params=params)
        return [self._candidate_from_lever(r) for r in rows[:limit]]

    @with_resilience(
        provider="ats_lever",
        method="push_job",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_job(self, job: Job) -> ExternalId:
        if not job.title:
            raise InvalidRequestError("job.title is required")
        body: dict[str, Any] = {
            "text": job.title,
            "content": {
                "description": job.description or "",
                "lists": [],
                "closing": "",
            },
        }
        if job.location:
            body["location"] = job.location
        if job.department:
            body["categories"] = {"department": job.department}
        if job.employment_type:
            body.setdefault("categories", {})["commitment"] = job.employment_type
        if job.external_id:
            body["id"] = job.external_id
        data = await self._request("POST", "/postings", json=body)
        if isinstance(data, dict):
            posting_id = str((data.get("data") or {}).get("id", ""))
        elif isinstance(data, list) and data:
            posting_id = str(data[0].get("id", ""))
        else:
            posting_id = ""
        return ExternalId(
            external_id=posting_id,
            external_url=f"https://jobs.lever.co/{posting_id}" if posting_id else None,
            raw=data if isinstance(data, (dict, list)) else {},
        )

    @with_resilience(
        provider="ats_lever",
        method="pull_jobs",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_jobs(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Job]:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if since is not None:
            params["updated_at_start"] = int(since.timestamp() * 1000)
        rows = await self._next_get("/postings", params=params)
        return [self._job_from_lever(r) for r in rows[:limit]]

    @with_resilience(
        provider="ats_lever",
        method="update_status",
        retry=RetryPolicy(max_retries=1),
    )
    async def update_status(
        self,
        external_id: str,
        status: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        stage = _LEVER_STATUS_MAP.get(status)
        if stage is None:
            raise InvalidRequestError(
                f"invalid status {status!r}",
                details={"valid": sorted(_LEVER_STATUS_MAP.keys())},
            )
        await self._request(
            "POST",
            f"/candidates/{external_id}/transition",
            params={"perform_as": "auto"},
            json={"stage": stage, "rationale": (metadata or {}).get("note", "waibao sync")},
        )
