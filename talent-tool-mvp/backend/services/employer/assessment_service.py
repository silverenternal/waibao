"""Assessment 业务服务 (T1306).

  - send_invite: 选择 provider 发送测评邀请,持久化 invitation + candidate score
  - get_result: 查询结果,把 overall_score 注入 candidate.assessment_score
                 供 matching engine 加权
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from providers.assessment.registry import get_assessment_provider

logger = logging.getLogger(__name__)


class AssessmentService:
    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase
        self._mock = None

    def _mock_provider(self):
        from providers.assessment.mock import MockAssessmentProvider
        if self._mock is None:
            self._mock = MockAssessmentProvider()
        return self._mock

    def _provider(self):
        from providers.assessment.registry import (
            get_assessment_provider, reset_cache,
        )
        import os
        preferred = os.getenv("ASSESSMENT_PROVIDER")
        if preferred:
            # 业务可显式设置
            pass
        try:
            return get_assessment_provider()
        except Exception as exc:
            logger.warning("assessment.provider.fallback err=%s", exc)
            return self._mock_provider()

    def _provider_by_name(self, name: str):
        from providers.assessment.mock import MockAssessmentProvider
        if name == "mock_assessment":
            return self._mock_provider()
        if name == "beisen":
            from providers.assessment.beisen import BeisenProvider
            return BeisenProvider()
        return self._mock_provider()

    # ------------------------------------------------------------------
    async def send_invite(
        self,
        *,
        candidate_id: str,
        assessment_id: str,
        candidate_email: str | None,
        candidate_name: str | None,
        expires_in_hours: int = 72,
        job_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        provider = self._provider()
        try:
            inv = await provider.send_invitation(
                candidate_id=candidate_id,
                assessment_id=assessment_id,
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                expires_in_hours=expires_in_hours,
                metadata={**(metadata or {}), "job_id": job_id or ""},
            )
        except Exception as exc:
            logger.warning(
                "assessment.send_invite.fallback provider=%s err=%s",
                getattr(provider, "provider_name", "?"), exc,
            )
            inv = await self._mock_provider().send_invitation(
                candidate_id=candidate_id,
                assessment_id=assessment_id,
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                expires_in_hours=expires_in_hours,
                metadata={**(metadata or {}), "job_id": job_id or ""},
            )
        # 落库 (unique invitation_id)
        record = {
            "invitation_id": inv.invitation_id,
            "candidate_id": candidate_id,
            "assessment_id": assessment_id,
            "provider": inv.provider,
            "status": inv.status,
            "invite_url": inv.invite_url,
            "expires_at": (
                inv.expires_at.astimezone(timezone.utc).isoformat()
                if inv.expires_at else None
            ),
            "job_id": job_id,
            "metadata": inv.metadata,
        }
        r = self.supabase.table("assessment_invitations").insert(record).execute()
        return r.data[0] if r.data else record

    async def get_result(self, invitation_id: str) -> dict[str, Any]:
        # 1) 读库找到 provider + candidate
        v = (
            self.supabase.table("assessment_invitations")
            .select("*")
            .eq("invitation_id", invitation_id)
            .execute()
        )
        rows = v.data or []
        if not rows:
            # 没找到 invitation_id → 直接尝试 mock,失败则返回 pending 兜底
            try:
                res = await self._mock_provider().get_results(invitation_id)
            except Exception:
                # 真实供应商的 invitation_id 也可能不在本地 DB
                # 返回最小 pending 结果,避免抛错
                from providers.assessment.types import AssessmentResult
                res = AssessmentResult(
                    invitation_id=invitation_id,
                    candidate_id="",
                    assessment_id="",
                    status="pending",
                    provider="mock_assessment",
                )
            return _result_to_dict(invitation_id, res)

        inv_row = rows[0]
        provider = self._provider_by_name(inv_row["provider"])
        try:
            res = await provider.get_results(invitation_id)
        except Exception:
            res = await self._mock_provider().get_results(invitation_id)
        result = _result_to_dict(invitation_id, res)

        # 2) 写回 candidate.assessment_score (供 matching 加权)
        if (
            res.status == "scored"
            and res.overall_score is not None
            and inv_row.get("candidate_id")
        ):
            confidence = _score_to_confidence(res.overall_score)
            self.supabase.table("candidates").update(
                {
                    "assessment_score": float(res.overall_score),
                    "assessment_confidence": confidence,
                    "assessment_updated_at": (
                        datetime.now(timezone.utc).isoformat()
                    ),
                }
            ).eq(
                "id", str(inv_row["candidate_id"]),
            ).execute()
            result["confidence"] = confidence
        return result


def _result_to_dict(invitation_id: str, res) -> dict[str, Any]:
    return {
        "invitation_id": invitation_id,
        "candidate_id": res.candidate_id,
        "assessment_id": res.assessment_id,
        "status": res.status,
        "overall_score": res.overall_score,
        "percentile": res.percentile,
        "passed": res.passed,
        "scores": [
            {"name": s.name, "value": s.value, "max": s.max, "band": s.band}
            for s in (res.scores or [])
        ],
        "report_url": res.report_url,
        "completed_at": (
            res.completed_at.astimezone(timezone.utc).isoformat()
            if res.completed_at else None
        ),
        "provider": res.provider,
        "confidence": (
            _score_to_confidence(res.overall_score)
            if res.overall_score is not None else None
        ),
    }


def _score_to_confidence(score: float) -> str:
    """把测评分(0-100)转换为 confidence 标签供 UI 显示."""
    if score >= 85:
        return "very_high"
    if score >= 70:
        return "high"
    if score >= 55:
        return "medium"
    if score >= 40:
        return "low"
    return "very_low"


__all__ = ["AssessmentService"]
