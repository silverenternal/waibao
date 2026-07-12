"""Region-aware 数据路由服务 — T1202.

根据用户的 region 路由到对应的 Supabase 实例 / 存储桶 / LLM provider region.

特点:
- 默认 CN(中国大陆境内 PII 强制本地化)
- 海外区域(SG / US)需要单独同意
- 所有路由决策写入 audit log
- 抽象 Supabase 客户端,便于单元测试
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from compliance.audit import get_audit_logger
from compliance.data_residency import (
    Region,
    ResidencyRouter,
    get_region_for_user,
    get_residency_router,
    audit_residency_decision,
)
from services.region_config import REGIONS, RegionConfig, get_region_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RouteDecision:
    """路由决策结果."""

    user_id: str | None
    source_region: Region
    target_region: Region
    allowed: bool
    reason: str
    config: RegionConfig | None = None


class RegionAwareRouter:
    """根据用户区域 + 驻留策略路由请求.

    内部使用 ResidencyRouter 做策略判断,本类负责拼装 RegionConfig.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._residency = get_residency_router()

    def route_for_user(
        self,
        user_id: str,
        *,
        requested_region: Region | None = None,
        is_pii: bool = False,
        has_cross_border_consent: bool = False,
        tenant_id: str | None = None,
    ) -> RouteDecision:
        """为某用户的请求决定目标 region.

        - 不传 requested_region: 用用户默认 region
        - 传了 requested_region: 走驻留策略判断
        """
        source = get_region_for_user(user_id)
        target = requested_region or source

        resolved = self._residency.resolve_region(
            target,
            is_pii=is_pii,
            tenant_id=tenant_id,
            has_cross_border_consent=has_cross_border_consent,
        )

        allowed = resolved == target or (resolved == source and resolved != target)
        # 注意:即使 fallback 到 primary_region,我们仍然允许写入,只是 target 变了
        # 因此 allowed 总是 True,但 resolved 可能 != target
        allowed = True

        reason = self._build_reason(source, target, resolved, is_pii, has_cross_border_consent)
        cfg = get_region_config(resolved)

        decision = RouteDecision(
            user_id=user_id,
            source_region=source,
            target_region=resolved,
            allowed=allowed,
            reason=reason,
            config=cfg,
        )

        # 写入审计
        try:
            audit_residency_decision(
                actor_id=user_id,
                from_region=source,
                to_region=resolved,
                resource="region_router",
                is_pii=is_pii,
                decision="allow" if allowed else "block",
            )
        except Exception:  # noqa: BLE001
            logger.exception("region_router.audit_failed")

        return decision

    def route_for_data(
        self,
        data: dict[str, Any],
        *,
        user_id: str | None = None,
        is_pii: bool = False,
        tenant_id: str | None = None,
        has_cross_border_consent: bool = False,
    ) -> RouteDecision:
        """根据数据中带的目标 region 字段路由."""
        raw = data.get("_target_region", Region.CN)
        try:
            requested = Region(raw) if isinstance(raw, str) else raw
        except ValueError:
            requested = Region.CN
        return self.route_for_user(
            user_id or "anonymous",
            requested_region=requested,
            is_pii=is_pii,
            tenant_id=tenant_id,
            has_cross_border_consent=has_cross_border_consent,
        )

    def get_supabase_config(self, region: Region) -> RegionConfig:
        return get_region_config(region)

    @staticmethod
    def _build_reason(
        source: Region,
        requested: Region,
        resolved: Region,
        is_pii: bool,
        has_consent: bool,
    ) -> str:
        if source == resolved == requested:
            return f"native region: {requested.value}"
        if resolved != requested:
            if is_pii:
                return "pii_forced_local: redirected to primary_region"
            if not has_consent:
                return "no_cross_border_consent: redirected to primary_region"
            return f"policy_redirect: {requested.value} → {resolved.value}"
        return f"cross_border_ok: {source.value} → {resolved.value}"


_singleton: RegionAwareRouter | None = None


def get_region_aware_router() -> RegionAwareRouter:
    global _singleton
    if _singleton is None:
        _singleton = RegionAwareRouter()
    return _singleton


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def resolve_supabase_target(
    user_id: str | None,
    *,
    requested_region: Region | None = None,
    is_pii: bool = False,
    has_cross_border_consent: bool = False,
) -> RegionConfig:
    """API 层调用此函数获取实际应使用的 Supabase 配置."""
    router = get_region_aware_router()
    if user_id is None:
        user_id = "anonymous"
    decision = router.route_for_user(
        user_id,
        requested_region=requested_region,
        is_pii=is_pii,
        has_cross_border_consent=has_cross_border_consent,
    )
    return decision.config or get_region_config(Region.CN)