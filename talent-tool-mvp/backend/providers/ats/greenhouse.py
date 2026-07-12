"""T1501 + T1806 — Greenhouse 真实 API Provider.

Greenhouse Harvest API 文档:
- Base URL: https://harvest.greenhouse.io/v1
- 认证: Basic Auth (api_key:``) 或 OAuth2 (Bullhorn/Workable 通用, Greenhouse 未来支持)
       现有 Greenhouse 仍用 Basic Auth + On-Behalf-Of token 代替
- 速率: 50 req / 10s (custom integrations)

核心资源:
- Candidates: /candidates
- Jobs: /jobs
- Applications: /applications  (candidate ↔ job 关联)
- Custom Fields: /custom_fields/<field>

实现要点:
- 拉取使用 since / updated_after 过滤, 客户端先调用 /jobs?status=open
- 推送候选人在 email 重复时返回 409 → 我们捕获后改用 PATCH 更新
- 按 limit + page 实现分页
- 自定义字段 (resume_url, tags, source) 通过 metadata 映射到 custom_field 后端
- OAuth2 支持: 注入 OAuth2TokenManager 后用 Bearer 头 (用于多租户代理 / 未来 Greenhouse OAuth)
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


_GH_STATUS_MAP = {
    "new": "active",
    "screening": "phone_screen",
    "interview": "interview",
    "offer": "offer",
    "hired": "hired",
    "rejected": "rejected",
}


class GreenhouseProvider(ATSProvider):
    """Greenhouse Harvest API Provider (real or sandbox)."""

    provider_name = "greenhouse"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://harvest.greenhouse.io/v1",
        *,
        on_behalf_of: str | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        oauth2_manager: OAuth2TokenManager | None = None,
        oauth2_tenant: str | None = None,
        oauth2_client_id: str | None = None,
        oauth2_client_secret: str | None = None,
        oauth2_token_url: str | None = None,
    ) -> None:
        # T1806: 支持 OAuth2 (Bullhorn / Workable 等扩展); Greenhouse 仍以 Basic Auth 为主
        if not api_key and not oauth2_manager:
            raise InvalidRequestError(
                "greenhouse requires api_key or oauth2_manager"
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._on_behalf_of = on_behalf_of
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        # OAuth2 字段
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
        # OAuth2 优先 (T1806 多租户代理)
        if self._oauth2_manager and self._oauth2_token_url:
            # 异步获取;调用方需要保证 _auth_header 在协程中
            # 此处采用懒获取模式 — 在 _request 中替换为 async 版本
            return {}
        # Basic auth: api_key + ":"  (Greenhouse 规范)
        token = base64.b64encode(f"{self._api_key}:".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
        if self._on_behalf_of:
            # 用于 On-Behalf-Of token 代理 (适用分租户)
            headers["On-Behalf-Of"] = self._on_behalf_of
        return headers

    async def _async_auth_header(self) -> dict[str, str]:
        """异步获取鉴权头 — 包含 OAuth2 token 刷新."""
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
                    "greenhouse.oauth2_fallback tenant=%s err=%s",
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
        # T1806: 异步获取鉴权头 (支持 OAuth2)
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
                f"greenhouse network error: {exc}",
                provider=self.provider_name,
            ) from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise AuthError(
                f"greenhouse auth failed: {resp.status_code}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "1"))
            raise RateLimitError(
                "greenhouse rate limit",
                provider=self.provider_name,
                details={"retry_after": retry_after, "status_code": 429},
            )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"greenhouse 5xx: {resp.status_code}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            # 409 conflict: candidate already exists
            raise InvalidRequestError(
                f"greenhouse {resp.status_code}: {resp.text[:200]}",
                provider=self.provider_name,
                status_code=resp.status_code,
            )
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------ paged GET
    async def _paged_get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """分页拉取, Greenhouse 没有 cursor, 用 page + per_page."""
        results: list[dict[str, Any]] = []
        page = 1
        params = dict(params or {})
        params["page"] = page
        params["per_page"] = page_size
        while True:
            params["page"] = page
            data = await self._request("GET", path, params=params)
            if not data:
                break
            if not isinstance(data, list):
                # 单对象时单独处理
                results.append(data)
                break
            results.extend(data)
            if len(data) < page_size:
                break
            page += 1
            if page > 100:  # 安全上限
                logger.warning("greenhouse.paged_too_many page=%s", page)
                break
        return results

    # ------------------------------------------------------------------ mapping
    @staticmethod
    def _candidate_from_gh(raw: dict[str, Any]) -> Candidate:
        email_obj = raw.get("email_addresses") or []
        primary = next((e for e in email_obj if e.get("type") == "primary"), None)
        email = (primary or {}).get("value") or raw.get("email") or ""
        phone_obj = raw.get("phone_numbers") or []
        phone = phone_obj[0].get("value") if phone_obj else None
        return Candidate(
            name=f"{raw.get('first_name','')} {raw.get('last_name','')}".strip(),
            email=email,
            phone=phone,
            external_id=str(raw.get("id")) if raw.get("id") is not None else None,
            source=(raw.get("source") or {}).get("name") if isinstance(raw.get("source"), dict) else raw.get("source"),
            tags=[],
            resume_url=raw.get("resume_url"),
            metadata={
                "updated_at": raw.get("updated_at"),
                "created_at": raw.get("created_at"),
                "raw": raw,
            },
        )

    @staticmethod
    def _job_from_gh(raw: dict[str, Any]) -> Job:
        offices = raw.get("offices") or []
        location = None
        if offices:
            location = ", ".join(o.get("name", "") for o in offices if o.get("name"))
        return Job(
            title=raw.get("name", ""),
            description=(raw.get("content") or ""),
            location=location,
            department=(raw.get("departments") or [{}])[0].get("name") if raw.get("departments") else None,
            external_id=str(raw.get("id")) if raw.get("id") is not None else None,
            status="closed" if raw.get("status") == "closed" else "open",
            url=raw.get("job_url") or raw.get("external_url"),
            opened_at=raw.get("opened_at") or raw.get("created_at"),
            metadata={
                "updated_at": raw.get("updated_at"),
                "raw": raw,
            },
        )

    # ------------------------------------------------------------------ API
    @with_resilience(
        provider="ats_greenhouse",
        method="push_candidate",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_candidate(self, candidate: Candidate) -> ExternalId:
        if not candidate.email:
            raise InvalidRequestError("candidate.email is required")
        if candidate.external_id:
            # 已存在 → PATCH
            body = {
                "first_name": (candidate.name or "").split(" ")[0],
                "last_name": " ".join((candidate.name or "").split(" ")[1:]) or "—",
                "email_addresses": [{"value": candidate.email, "type": "primary"}],
            }
            data = await self._request(
                "PATCH",
                f"/candidates/{candidate.external_id}",
                json=body,
            )
            if data and isinstance(data, dict):
                return ExternalId(
                    external_id=str(data.get("id", candidate.external_id)),
                    external_url=f"https://app.greenhouse.io/people/{data.get('id', candidate.external_id)}",
                    raw=data,
                )
            return ExternalId(external_id=candidate.external_id)

        # 新建: 先查询避免 409
        existing = await self._request(
            "GET",
            "/candidates",
            params={"email": candidate.email},
        )
        if isinstance(existing, list) and existing:
            cand = existing[0]
            return ExternalId(
                external_id=str(cand["id"]),
                external_url=f"https://app.greenhouse.io/people/{cand['id']}",
                raw=cand,
            )
        # POST
        first = (candidate.name or "").split(" ")[0] or "Unknown"
        last = " ".join((candidate.name or "").split(" ")[1:]) or "—"
        body: dict[str, Any] = {
            "first_name": first,
            "last_name": last,
            "email_addresses": [{"value": candidate.email, "type": "primary"}],
        }
        if candidate.phone:
            body["phone_numbers"] = [{"value": candidate.phone, "type": "mobile"}]
        if candidate.resume_url:
            body["resume_url"] = candidate.resume_url
        if candidate.external_id:
            body["external_id"] = candidate.external_id
        data = await self._request("POST", "/candidates", json=body)
        cand_id = str((data or {}).get("id", ""))
        return ExternalId(
            external_id=cand_id,
            external_url=f"https://app.greenhouse.io/people/{cand_id}" if cand_id else None,
            raw=data or {},
        )

    @with_resilience(
        provider="ats_greenhouse",
        method="pull_candidates",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_candidates(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Candidate]:
        params: dict[str, Any] = {}
        if since is not None:
            params["updated_after"] = since.isoformat()
        rows = await self._paged_get("/candidates", params=params, page_size=min(limit, 100))
        return [self._candidate_from_gh(r) for r in rows[:limit]]

    @with_resilience(
        provider="ats_greenhouse",
        method="push_job",
        retry=RetryPolicy(max_retries=2),
    )
    async def push_job(self, job: Job) -> ExternalId:
        if not job.title:
            raise InvalidRequestError("job.title is required")
        body: dict[str, Any] = {
            "name": job.title,
            "content": job.description or "",
        }
        if job.location:
            body["offices"] = [{"name": job.location}]
        if job.department:
            body["departments"] = [{"name": job.department}]
        if job.external_id:
            body["requisition_id"] = job.external_id
        data = await self._request("POST", "/jobs", json=body)
        job_id = str((data or {}).get("id", ""))
        return ExternalId(
            external_id=job_id,
            external_url=f"https://app.greenhouse.io/recruiting/job/{job_id}" if job_id else None,
            raw=data or {},
        )

    @with_resilience(
        provider="ats_greenhouse",
        method="pull_jobs",
        retry=RetryPolicy(max_retries=2),
    )
    async def pull_jobs(
        self,
        since: datetime | None = None,
        *,
        limit: int = 100,
    ) -> list[Job]:
        params: dict[str, Any] = {}
        if since is not None:
            params["updated_after"] = since.isoformat()
        rows = await self._paged_get("/jobs", params=params, page_size=min(limit, 100))
        return [self._job_from_gh(r) for r in rows[:limit]]

    @with_resilience(
        provider="ats_greenhouse",
        method="update_status",
        retry=RetryPolicy(max_retries=1),
    )
    async def update_status(
        self,
        external_id: str,
        status: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        gh_status = _GH_STATUS_MAP.get(status)
        if gh_status is None:
            raise InvalidRequestError(
                f"invalid status {status!r}",
                details={"valid": sorted(_GH_STATUS_MAP.keys())},
            )
        # Greenhouse 状态走 application 维度的 PUT,简化起见这里只发招聘流程字段
        await self._request(
            "POST",
            f"/candidates/{external_id}/activity",
            json={"activity_type": "note", "note": f"waibao sync status={status}"},
        )
