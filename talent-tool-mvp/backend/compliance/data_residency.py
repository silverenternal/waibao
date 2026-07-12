"""数据驻留策略 — 中国境内 / 海外.

T1202 中国合规 — 重要数据 / 个人数据应在境内存储与处理;
跨境传输须经用户单独同意 + 安全评估.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Region(str, Enum):
    """区域代码.

    T1202 — 三区域核心: CN (中国大陆) / SG (新加坡) / US (美国)
    其他保留以兼容既有调用方.
    """

    CN = "cn"  # 中国大陆
    SG = "sg"  # 新加坡
    US = "us"  # 美国
    EU = "eu"  # 欧盟
    UK = "uk"  # 英国
    APAC = "apac"  # 亚太(非中国大陆)
    GLOBAL = "global"


@dataclass(slots=True)
class ResidencyPolicy:
    """数据驻留策略.

    默认:中国为主区域;允许跨境但需明示同意;PII 强制本地化.
    """

    primary_region: Region = Region.CN
    allow_cross_border: bool = True
    require_explicit_consent_for_cross_border: bool = True
    blocked_destinations: list[Region] = field(default_factory=list)
    pii_must_stay_local: bool = True  # PII 是否必须本地化
    metadata: dict[str, Any] = field(default_factory=dict)


class ResidencyRouter:
    """根据策略判断数据应存储到哪个 region / bucket."""

    def __init__(self, policy: ResidencyPolicy | None = None) -> None:
        self._lock = threading.RLock()
        self._policy = policy or ResidencyPolicy()
        self._per_tenant: dict[str, ResidencyPolicy] = {}

    def set_policy(self, policy: ResidencyPolicy) -> None:
        with self._lock:
            self._policy = policy

    def set_tenant_policy(self, tenant_id: str, policy: ResidencyPolicy) -> None:
        with self._lock:
            self._per_tenant[tenant_id] = policy

    def policy_for(self, tenant_id: str | None = None) -> ResidencyPolicy:
        with self._lock:
            if tenant_id and tenant_id in self._per_tenant:
                return self._per_tenant[tenant_id]
        return self._policy

    def resolve_region(
        self,
        requested: Region,
        *,
        is_pii: bool = False,
        tenant_id: str | None = None,
        has_cross_border_consent: bool = False,
    ) -> Region:
        """根据策略决定数据应存放在哪个 region.

        - PII 强制本地化时,即使请求跨区域,也会被路由回 primary_region
        - 缺少跨境同意时,跨区域请求 fallback 到 primary_region
        """
        policy = self.policy_for(tenant_id)
        if is_pii and policy.pii_must_stay_local and requested != policy.primary_region:
            return policy.primary_region
        if requested == policy.primary_region:
            return policy.primary_region
        if requested in policy.blocked_destinations:
            return policy.primary_region
        if not policy.allow_cross_border:
            return policy.primary_region
        if (
            policy.require_explicit_consent_for_cross_border
            and not has_cross_border_consent
        ):
            return policy.primary_region
        return requested

    def can_transfer(
        self,
        from_region: Region,
        to_region: Region,
        *,
        is_pii: bool = False,
        tenant_id: str | None = None,
        has_cross_border_consent: bool = False,
    ) -> bool:
        """判断 from -> to 是否允许."""
        if from_region == to_region:
            return True
        policy = self.policy_for(tenant_id)
        if is_pii and policy.pii_must_stay_local:
            return False
        if to_region in policy.blocked_destinations:
            return False
        if not policy.allow_cross_border:
            return False
        if policy.require_explicit_consent_for_cross_border and not has_cross_border_consent:
            return False
        return True


_singleton: ResidencyRouter | None = None


def get_residency_router() -> ResidencyRouter:
    global _singleton
    if _singleton is None:
        _singleton = ResidencyRouter()
    return _singleton


# ---------------------------------------------------------------------------
# 顶层便捷函数 — T1202
# ---------------------------------------------------------------------------

_user_region_store: dict[str, Region] = {}
_user_region_lock = __import__("threading").RLock()


def set_user_region(user_id: str, region: Region) -> None:
    """记录用户所在区域(由 API 层在登录 / 注册时调用)."""
    with _user_region_lock:
        _user_region_store[user_id] = region


def get_region_for_user(user_id: str) -> Region:
    """获取用户所在区域;未知则默认 CN."""
    with _user_region_lock:
        return _user_region_store.get(user_id, Region.CN)


def ensure_data_in_region(
    data: dict[str, Any] | list[Any] | str | bytes,
    region: Region,
    *,
    is_pii: bool = False,
    tenant_id: str | None = None,
    has_cross_border_consent: bool = False,
) -> bool:
    """确保数据可存放在指定 region.

    返回:
        True  — 数据可存放在 region(resolved == region 或 fallback 到 region)
        False — 数据需路由到其他 region(调用方需重定向)

    通过在 data 中附带 `_target_region` 字段,本函数会判断是否需要
    fallback 到 primary region.
    """
    router = get_residency_router()
    target = data.get("_target_region", region) if isinstance(data, dict) else region
    if isinstance(target, str):
        try:
            target = Region(target)
        except ValueError:
            target = region
    resolved = router.resolve_region(
        target,
        is_pii=is_pii,
        tenant_id=tenant_id,
        has_cross_border_consent=has_cross_border_consent,
    )
    # data 已存或被 fallback 到 region,均视为 OK
    return resolved == region


def audit_residency_decision(
    *,
    actor_id: str | None,
    from_region: Region,
    to_region: Region,
    resource: str,
    is_pii: bool,
    decision: str,  # "allow" | "block" | "redirect"
) -> None:
    """记录数据驻留决策到 audit log."""
    from .audit import get_audit_logger

    logger = get_audit_logger()
    logger.log(
        actor_id=actor_id,
        actor_role="system",
        action="residency_decision",
        resource=resource,
        cross_border=(from_region != to_region),
        legal_basis="legitimate_interest",
        data_categories=["metadata"] + (["pii"] if is_pii else []),
        metadata={
            "from_region": from_region.value,
            "to_region": to_region.value,
            "decision": decision,
        },
    )