"""北森 (Beisen) Assessment Provider (T1306).

北森开放平台: https://open.beisen.com
  - Auth: client_credentials OAuth2
  - 创建测评任务: POST /v1/interfaces/invitation/create
  - 查询任务结果:  GET /v1/interfaces/invitation/result?invitationId={id}

环境变量:
  BEISEN_PROVIDER=true                 # 启用 (其余走 mock)
  BEISEN_BASE_URL=https://open.beisen.com
  BEISEN_APP_ID                        # AppId (client_id)
  BEISEN_APP_SECRET                    # AppSecret (client_secret)
  BEISEN_TENANT_ID                     # 企业账号 id
  BEISEN_REDIRECT_URI                  # OAuth2 redirect (agent 用)
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
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
from .base import AssessmentProvider
from .types import AssessmentResult, Invitation, Score

logger = logging.getLogger(__name__)

_BEISEN_DEFAULT_BASE = "https://open.beisen.com"


class BeisenProvider(AssessmentProvider):
    """北森一体化人才测评云 (云端 SaaS) Provider.

    通过 OAuth2 client_credentials 拿 access_token 后调用开放接口.
    """

    provider_name = "beisen"

    def __init__(self) -> None:
        self.app_id = os.getenv("BEISEN_APP_ID") or ""
        self.app_secret = os.getenv("BEISEN_APP_SECRET") or ""
        self.tenant_id = os.getenv("BEISEN_TENANT_ID") or ""
        self.base_url = (
            os.getenv("BEISEN_BASE_URL") or _BEISEN_DEFAULT_BASE
        ).rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    def _configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _ensure_config(self) -> None:
        if not self._configured():
            raise UpstreamUnavailableError(
                "Beisen credentials missing (BEISEN_APP_ID/BEISEN_APP_SECRET)",
                provider=self.provider_name,
            )

    # ------------------------------------------------------------------
    async def _get_token(self) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - 60:
                return self._token
            self._ensure_config()
            payload = {
                "appId": self.app_id,
                "appSecret": self.app_secret,
                "tenantId": self.tenant_id or "",
                "grantType": "client_credentials",
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/interfaces/oauth2/token",
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"beisen oauth timeout: {exc}",
                    provider=self.provider_name,
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"beisen oauth network error: {exc}",
                    provider=self.provider_name,
                ) from exc
            if resp.status_code in (401, 403):
                raise AuthError(
                    f"beisen oauth unauthorized: {resp.text}",
                    provider=self.provider_name,
                )
            if resp.status_code >= 500:
                raise UpstreamUnavailableError(
                    f"beisen oauth {resp.status_code}",
                    provider=self.provider_name,
                )
            try:
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                raise UpstreamUnavailableError(
                    f"beisen oauth invalid json: {exc}",
                    provider=self.provider_name,
                ) from exc
            if data.get("errorCode") not in (0, None, "0"):
                raise AuthError(
                    f"beisen oauth error: "
                    f"{data.get('errorCode')} {data.get('errorMessage')}",
                    provider=self.provider_name,
                )
            self._token = data.get("accessToken") or data.get("access_token")
            if not self._token:
                raise AuthError(
                    f"beisen oauth missing accessToken: {data}",
                    provider=self.provider_name,
                )
            self._token_expires_at = now + float(
                data.get("expiresIn") or data.get("expires_in") or 7200
            )
            return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "AppId": self.app_id,
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
                f"beisen {method} {path} timeout: {exc}",
                provider=self.provider_name,
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"beisen {method} {path} network error: {exc}",
                provider=self.provider_name,
            ) from exc

        if resp.status_code == 401 and self._token is not None:
            self._token = None
            self._token_expires_at = 0.0
            token = await self._get_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.request(
                        method, url, headers=headers, json=json, params=params,
                    )
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"beisen retry network: {exc}",
                    provider=self.provider_name,
                ) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                f"beisen rate-limited: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code in (401, 403):
            raise AuthError(
                f"beisen {method} {path} unauthorized: {resp.text}",
                provider=self.provider_name,
            )
        if resp.status_code == 404:
            return 404, None
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"beisen {method} {path} {resp.status_code}",
                provider=self.provider_name,
            )
        try:
            data = resp.json() if resp.text else {}
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data

    # ------------------------------------------------------------------
    @with_resilience(
        provider="beisen",
        method="send_invitation",
        retry=RetryPolicy(max_retries=2),
    )
    async def send_invitation(
        self,
        candidate_id: str,
        assessment_id: str,
        *,
        candidate_email: str | None = None,
        candidate_name: str | None = None,
        expires_in_hours: int = 72,
        metadata: dict[str, str] | None = None,
    ) -> Invitation:
        if not candidate_id or not assessment_id:
            raise InvalidRequestError(
                "candidate_id and assessment_id are required",
                provider=self.provider_name,
            )
        payload: dict[str, Any] = {
            "assessmentId": assessment_id,
            "candidateId": candidate_id,
            "candidateName": candidate_name or "Candidate",
            "email": candidate_email or "",
            "expireAt": (
                datetime.now(timezone.utc)
                + timedelta(hours=expires_in_hours)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "tenantId": self.tenant_id or "",
            "bizData": metadata or {},
        }
        status, data = await self._request(
            "POST",
            "/v1/interfaces/invitation/create",
            json=payload,
        )
        if status >= 400 or not isinstance(data, dict):
            raise UpstreamUnavailableError(
                f"beisen invitation error {status}: {data}",
                provider=self.provider_name,
            )
        ec = data.get("errorCode")
        if ec not in (0, None, "0"):
            raise UpstreamUnavailableError(
                f"beisen invitation error {ec}: "
                f"{data.get('errorMessage')}",
                provider=self.provider_name,
                details={"response": data},
            )
        invitation_id = str(
            data.get("invitationId")
            or data.get("inviteId")
            or f"inv_beisen_{secrets.token_hex(6)}"
        )
        invite_url = (
            data.get("url")
            or data.get("inviteUrl")
            or f"https://exam.beisen.com/take/{invitation_id}"
        )
        return Invitation(
            invitation_id=invitation_id,
            candidate_id=candidate_id,
            assessment_id=assessment_id,
            status="pending",
            invite_url=invite_url,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
            ),
            provider=self.provider_name,
            metadata={
                **(metadata or {}),
                "candidate_email": candidate_email or "",
                "candidate_name": candidate_name or "",
                "tenant_id": self.tenant_id,
                "error_code": str(ec or ""),
            },
        )

    @with_resilience(
        provider="beisen",
        method="get_results",
        retry=RetryPolicy(max_retries=3),
    )
    async def get_results(self, invitation_id: str) -> AssessmentResult:
        status, data = await self._request(
            "GET",
            "/v1/interfaces/invitation/result",
            params={"invitationId": invitation_id},
        )
        if status == 404 or not data:
            return AssessmentResult(
                invitation_id=invitation_id,
                candidate_id="",
                assessment_id="",
                status="pending",
                provider=self.provider_name,
            )
        ec = data.get("errorCode")
        if ec not in (0, None, "0"):
            # 业务错误视为 pending (北森约定: 候选人未开始 = 业务未结束)
            return AssessmentResult(
                invitation_id=invitation_id,
                candidate_id="",
                assessment_id="",
                status="pending",
                provider=self.provider_name,
                raw=data,
            )

        result_status = data.get("status") or data.get("resultStatus") or "pending"
        result_status = str(result_status).lower()
        # 状态映射: 北森 pending / submitted / scored / expired
        if result_status in ("0", "start", "started", "in_progress"):
            mapped = "submitted"
        elif result_status in ("1", "finish", "completed", "scored"):
            mapped = "scored"
        elif result_status in ("-1", "expired", "out_of_date"):
            mapped = "expired"
        else:
            mapped = "pending"

        scores: list[Score] = []
        for s in data.get("scoreList") or data.get("scores") or []:
            scores.append(
                Score(
                    name=str(s.get("name") or s.get("dimension") or "score"),
                    value=float(s.get("value") or s.get("score") or 0),
                    max=float(s.get("max") or 100),
                    band=str(s.get("band")) if s.get("band") else None,
                )
            )

        overall = (
            data.get("overallScore")
            if data.get("overallScore") is not None
            else data.get("totalScore")
        )
        overall = float(overall) if overall is not None else None
        return AssessmentResult(
            invitation_id=invitation_id,
            candidate_id=str(data.get("candidateId") or ""),
            assessment_id=str(data.get("assessmentId") or ""),
            status=mapped,
            overall_score=overall,
            percentile=(
                float(data.get("percentile"))
                if data.get("percentile") is not None
                else None
            ),
            passed=(
                bool(data.get("passed"))
                if data.get("passed") is not None
                else None
            ),
            scores=scores,
            report_url=data.get("reportUrl") or data.get("report_url"),
            completed_at=_parse_iso(data.get("completedAt")),
            provider=self.provider_name,
            raw=data,
        )


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
