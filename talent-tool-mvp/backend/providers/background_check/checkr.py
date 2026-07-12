"""Checkr Background Check Provider (T1307).

Checkr 是美国主流的就业背景调查 SaaS,提供:
  - 创建候选人
  - 发起报告 (Report)
  - 查询报告状态 + findings

API base: https://api.checkr.com/v1
Auth: Basic auth (api_key 作为 username, 密码空)

环境变量:
  CHECKR_PROVIDER=true
  CHECKR_API_KEY=acct_...
  CHECKR_BASE_URL=https://api.checkr.com/v1
  CHECKR_PACKAGE=tasker_standard    # Checkr package slug 默认值
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    RateLimitError,
    TimeoutError,
    UpstreamUnavailableError,
)
from .base import BackgroundCheckProvider
from .types import Check, CheckStatus, CheckType, Finding

logger = logging.getLogger(__name__)

_CHECKR_DEFAULT_BASE = "https://api.checkr.com/v1"


class CheckrProvider(BackgroundCheckProvider):
    """Checkr background check provider."""

    provider_name = "checkr"

    def __init__(self) -> None:
        self.api_key = os.getenv("CHECKR_API_KEY") or ""
        self.base_url = (
            os.getenv("CHECKR_BASE_URL") or _CHECKR_DEFAULT_BASE
        ).rstrip("/")
        self.default_package = os.getenv("CHECKR_PACKAGE") or "tasker_standard"

    # ------------------------------------------------------------------
    def _configured(self) -> bool:
        return bool(self.api_key)

    def _ensure_config(self) -> None:
        if not self._configured():
            raise UpstreamUnavailableError(
                "Checkr credentials missing (CHECKR_API_KEY)",
                provider=self.provider_name,
            )

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.api_key}:".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        self._ensure_config()
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method, url, headers=headers, json=json, params=params,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"checkr {method} {path} timeout: {exc}",
                provider=self.provider_name,
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"checkr {method} {path} network error: {exc}",
                provider=self.provider_name,
            ) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"checkr rate-limited: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"checkr {method} {path} unauthorized: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code == 404:
            return 404, None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"checkr {method} {path} {resp.status_code}",
                provider=self.provider_name,
            )
        try:
            data = resp.json() if resp.text else {}
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data

    # ------------------------------------------------------------------
    @with_resilience(
        provider="checkr",
        method="initiate_check",
        retry=RetryPolicy(max_retries=2),
    )
    async def initiate_check(
        self,
        candidate_id: str,
        check_types: list[CheckType],
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Check:
        if not candidate_id:
            raise InvalidRequestError(
                "candidate_id is required", provider=self.provider_name,
            )
        if not check_types:
            raise InvalidRequestError(
                "check_types must not be empty",
                provider=self.provider_name,
            )

        # Step 1: create candidate
        first, *rest = (candidate_name or candidate_id).split(maxsplit=1)
        last = rest[0] if rest else "-"
        candidate_payload = {
            "candidate_id": candidate_id,
            "email": candidate_email or "",
            "first_name": first,
            "last_name": last,
            "no_middle_name": True,
            "custom_id": candidate_id,
        }
        status_c, cand_data = await self._request(
            "POST", "/candidates", json=candidate_payload,
        )
        if status_c >= 400 or not isinstance(cand_data, dict):
            raise UpstreamUnavailableError(
                f"checkr candidates {status_c}: {cand_data}",
                provider=self.provider_name,
            )
        checkr_candidate_id = cand_data.get("id")

        # Step 2: create report
        slugs = [t.code for t in check_types]
        report_payload: dict[str, Any] = {
            "candidate": checkr_candidate_id,
            "package": self.default_package,
            "work_locations": [],
        }
        # 显式 slug 用于非默认包
        if len(slugs) == 1:
            report_payload["slugs"] = slugs
        status_r, rep_data = await self._request(
            "POST", "/reports", json=report_payload,
        )
        if status_r >= 400 or not isinstance(rep_data, dict):
            raise UpstreamUnavailableError(
                f"checkr reports {status_r}: {rep_data}",
                provider=self.provider_name,
            )

        check_id = str(
            rep_data.get("id") or f"chk_checkr_{secrets.token_hex(6)}"
        )
        return Check(
            check_id=check_id,
            candidate_id=candidate_id,
            status="pending",
            check_types=slugs,
            report_url=rep_data.get("report_url"),
            created_at=_parse_iso(rep_data.get("created_at")),
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "candidate_email": candidate_email or "",
                "candidate_name": candidate_name or "",
                "checkr_candidate_id": str(checkr_candidate_id or ""),
                "checkr_report_id": check_id,
            },
        )

    @with_resilience(
        provider="checkr",
        method="get_status",
        retry=RetryPolicy(max_retries=3),
    )
    async def get_status(self, check_id: str) -> CheckStatus:
        status, data = await self._request(
            "GET", f"/reports/{check_id}",
        )
        if status == 404 or not data:
            return CheckStatus(
                check_id=check_id,
                candidate_id="",
                status="pending",
                provider=self.provider_name,
                updated_at=datetime.now(timezone.utc),
            )
        # Checkr status:
        #   pending / in_progress / consider / clear / suspended / cancelled
        mapped = _map_checkr_status(data.get("status"))
        findings: list[Finding] = []
        # checkr returns nested "records" with adjudication
        for adj in (data.get("records") or []):
            findings.append(
                Finding(
                    code=str(adj.get("type") or "record"),
                    severity=str(adj.get("adjudication") or "info"),
                    description=str(adj.get("comment") or ""),
                    category=adj.get("category"),
                )
            )
        return CheckStatus(
            check_id=check_id,
            candidate_id=str(data.get("candidate_id") or ""),
            status=mapped,
            progress_pct=_progress_pct(data.get("status")),
            report_url=data.get("report_url"),
            findings=findings,
            updated_at=_parse_iso(data.get("updated_at")),
            provider=self.provider_name,
            raw=data,
        )


def _map_checkr_status(s: str | None) -> str:
    s = (s or "").lower()
    return {
        "clear": "clear",
        "consider": "consider",
        "suspended": "suspended",
        "in_progress": "in_progress",
        "pending": "pending",
        "canceled": "suspended",
    }.get(s, "pending")


def _progress_pct(s: str | None) -> float:
    s = (s or "").lower()
    return {
        "pending": 10.0,
        "in_progress": 50.0,
        "consider": 90.0,
        "clear": 100.0,
    }.get(s, 0.0)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
