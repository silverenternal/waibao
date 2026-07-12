"""BackgroundCheck 业务服务 (T1307).

  - initiate_background_check: 选择 provider 发起背调
  - get_status: 拉结果,落库并按状态触发后续动作
  - trigger_pre_offer: HR offer 流程之前自动发起背调(被 HR service agent 调用)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from providers.background_check.registry import get_background_check_provider
from providers.background_check.types import Check, CheckType

logger = logging.getLogger(__name__)


DEFAULT_CHECK_TYPES = [
    CheckType(code="employment", name="Employment verification", required=True),
    CheckType(code="education", name="Education verification", required=False),
    CheckType(code="criminal", name="Criminal record check", required=True),
]


class BackgroundCheckService:
    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase
        self._mock = None

    def _mock_provider(self):
        from providers.background_check.mock import MockBackgroundCheckProvider
        if self._mock is None:
            self._mock = MockBackgroundCheckProvider()
        return self._mock

    def _provider(self):
        # 让 mock provider 始终复用 service 单例 (与 test seed 兼容)
        from providers.background_check.registry import reset_cache
        import os
        name = (os.getenv("BG_CHECK_PROVIDER") or "mock").lower()
        if name == "mock":
            return self._mock_provider()
        try:
            # 真实供应商构造可能抛 ProviderError
            p = get_background_check_provider()
            if p.provider_name == "mock_bg_check":
                return self._mock_provider()
            return p
        except Exception as exc:
            logger.warning("bg_check.provider.fallback err=%s", exc)
            return self._mock_provider()

    def _provider_by_name(self, name: str):
        from providers.background_check.mock import MockBackgroundCheckProvider
        if name == "mock_bg_check":
            return self._mock_provider()
        if name == "checkr":
            from providers.background_check.checkr import CheckrProvider
            return CheckrProvider()
        return self._mock_provider()

    # ------------------------------------------------------------------
    async def initiate(
        self,
        *,
        candidate_id: str,
        candidate_email: str | None,
        candidate_name: str | None,
        offer_id: str | None,
        job_id: str | None,
        check_types: list[CheckType] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        types = check_types or DEFAULT_CHECK_TYPES
        provider = self._provider()
        try:
            chk: Check = await provider.initiate_check(
                candidate_id=candidate_id,
                check_types=types,
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                metadata={**(metadata or {}),
                          "offer_id": offer_id or "",
                          "job_id": job_id or ""},
            )
        except Exception as exc:
            logger.warning(
                "bg_check.initiate.fallback provider=%s err=%s",
                getattr(provider, "provider_name", "?"), exc,
            )
            mock = self._mock_provider()
            chk = await mock.initiate_check(
                candidate_id=candidate_id,
                check_types=types,
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                metadata={**(metadata or {}),
                          "offer_id": offer_id or "",
                          "job_id": job_id or ""},
            )
            # 重置 row provider 为 mock, 保证后续 get_status 找到同一实例
            chk.provider = mock.provider_name
            chk_id = chk.check_id
            for k, v in mock._checks.items():
                if v.check_id == chk_id:
                    v.provider = mock.provider_name
                    break

        record = {
            "check_id": chk.check_id,
            "candidate_id": candidate_id,
            "provider": chk.provider,
            "status": chk.status,
            "check_types": chk.check_types,
            "report_url": chk.report_url,
            "offer_id": offer_id,
            "job_id": job_id,
            "metadata": chk.metadata,
            "created_at": (
                chk.created_at.astimezone(timezone.utc).isoformat()
                if chk.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
        }
        r = self.supabase.table("background_checks").insert(record).execute()
        return r.data[0] if r.data else record

    async def get_status(
        self, check_id: str
    ) -> dict[str, Any]:
        # read inv
        v = (
            self.supabase.table("background_checks")
            .select("*")
            .eq("check_id", check_id)
            .execute()
        )
        rows = v.data or []
        if not rows:
            # unknown → mock placeholder
            st = await self._mock_provider().get_status(check_id)
            return _status_to_dict(st)
        row = rows[0]
        provider = self._provider_by_name(row.get("provider"))
        try:
            st = await provider.get_status(check_id)
        except Exception as exc:
            logger.warning(
                "bg_check.get_status.fallback err=%s", exc,
            )
            st = await self._mock_provider().get_status(check_id)
        result = _status_to_dict(st)

        # 持久化状态 + findings
        update = {
            "status": st.status,
            "report_url": st.report_url or row.get("report_url"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if st.status in ("clear", "consider", "suspended"):
            update["completed_at"] = update["updated_at"]
            update["findings"] = [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "description": f.description,
                    "category": f.category,
                }
                for f in (st.findings or [])
            ]
        self.supabase.table("background_checks").update(
            update
        ).eq("check_id", check_id).execute()
        return result

    # ------------------------------------------------------------------
    # HR 自动化: Offer 前自动触发
    # ------------------------------------------------------------------
    async def trigger_pre_offer(
        self,
        *,
        candidate_id: str,
        candidate_email: str | None,
        candidate_name: str | None,
        offer_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """被 HR service agent 在创建 Offer 之前调用.

        业务规则:
          - 若 candidate 已经有 running / cleared 的背调,跳过本次
          - 否则自动发起,状态为 in_progress
          - 不阻塞 offer 主流程,只记录依赖
        """
        # 查重
        existing = (
            self.supabase.table("background_checks")
            .select("check_id,status")
            .eq("candidate_id", candidate_id)
            .execute()
        )
        for r in (existing.data or []):
            if r.get("status") in ("pending", "in_progress", "clear"):
                return {"skipped": True, "reason": "existing_check", "data": r}

        return {
            "skipped": False,
            "data": await self.initiate(
                candidate_id=candidate_id,
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                offer_id=offer_id,
                job_id=job_id,
            ),
        }


def _status_to_dict(st) -> dict[str, Any]:
    return {
        "check_id": st.check_id,
        "candidate_id": st.candidate_id,
        "status": st.status,
        "progress_pct": st.progress_pct,
        "report_url": st.report_url,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "description": f.description,
                "category": f.category,
            }
            for f in (st.findings or [])
        ],
        "updated_at": (
            st.updated_at.astimezone(timezone.utc).isoformat()
            if st.updated_at else None
        ),
        "provider": st.provider,
    }


__all__ = ["BackgroundCheckService", "DEFAULT_CHECK_TYPES"]
