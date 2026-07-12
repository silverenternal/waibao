"""数据驻留 / 区域路由 测试 — T1202."""
from __future__ import annotations

import pytest

from compliance.data_residency import (
    Region,
    ResidencyPolicy,
    ResidencyRouter,
    ensure_data_in_region,
    get_region_for_user,
    set_user_region,
)
from services.region_config import (
    REGIONS,
    get_region_config,
    list_regions,
    region_for_phone,
)
from services.region_router import (
    RegionAwareRouter,
    RouteDecision,
    get_region_aware_router,
)


@pytest.fixture(autouse=True)
def reset_state():
    """每个测试前重置单例 + 用户区域 store."""
    import compliance.data_residency as mod
    from compliance.data_residency import _user_region_lock, _user_region_store

    mod._singleton = ResidencyRouter()
    with _user_region_lock:
        _user_region_store.clear()
    import services.region_router as rmod

    rmod._singleton = RegionAwareRouter()
    yield


# ---------------------------------------------------------------------------
# 单元 — Region + Policy
# ---------------------------------------------------------------------------

def test_region_enum_has_three_core():
    """T1202 核心三区域: CN / SG / US."""
    assert Region.CN.value == "cn"
    assert Region.SG.value == "sg"
    assert Region.US.value == "us"


def test_residency_router_pii_forced_local():
    router = get_residency_router_default()
    # PII 即使请求 US,也会被强制本地化为 CN
    out = router.resolve_region(Region.US, is_pii=True)
    assert out == Region.CN


def test_residency_router_cross_border_no_consent():
    router = get_residency_router_default()
    out = router.resolve_region(Region.US, has_cross_border_consent=False)
    assert out == Region.CN


def test_residency_router_cross_border_with_consent():
    router = get_residency_router_default()
    out = router.resolve_region(Region.US, has_cross_border_consent=True)
    assert out == Region.US


def test_residency_router_can_transfer():
    router = get_residency_router_default()
    # 同区域 → 允许
    assert router.can_transfer(Region.CN, Region.CN, is_pii=True) is True
    # PII 跨区域 → 禁止
    assert router.can_transfer(Region.CN, Region.US, is_pii=True) is False
    # 非 PII + 有 consent → 允许
    assert router.can_transfer(Region.CN, Region.US, has_cross_border_consent=True) is True


def get_residency_router_default():
    import compliance.data_residency as mod

    mod._singleton = ResidencyRouter(ResidencyPolicy(
        primary_region=Region.CN,
        allow_cross_border=True,
        require_explicit_consent_for_cross_border=True,
        pii_must_stay_local=True,
    ))
    return mod._singleton


# ---------------------------------------------------------------------------
# get_region_for_user / set_user_region
# ---------------------------------------------------------------------------

def test_get_region_for_user_default_cn():
    assert get_region_for_user("nobody") == Region.CN


def test_set_and_get_region():
    set_user_region("u1", Region.SG)
    assert get_region_for_user("u1") == Region.SG


# ---------------------------------------------------------------------------
# ensure_data_in_region
# ---------------------------------------------------------------------------

def test_ensure_data_in_region_simple():
    data = {"x": 1, "_target_region": Region.CN.value}
    assert ensure_data_in_region(data, Region.CN) is True


def test_ensure_data_in_region_pii_blocked():
    data = {"pii": "secret", "_target_region": Region.US.value}
    # PII 不允许跨区域 → 重定向到 CN
    out = ensure_data_in_region(data, Region.US, is_pii=True)
    assert out is False  # 期望 US,实际被重定向


def test_ensure_data_in_region_with_consent():
    data = {"x": 1, "_target_region": Region.US.value}
    out = ensure_data_in_region(
        data, Region.US, has_cross_border_consent=True
    )
    assert out is True


# ---------------------------------------------------------------------------
# RegionAwareRouter
# ---------------------------------------------------------------------------

def test_route_for_user_native_region():
    set_user_region("u1", Region.CN)
    router = get_region_aware_router()
    decision = router.route_for_user("u1")
    assert isinstance(decision, RouteDecision)
    assert decision.source_region == Region.CN
    assert decision.target_region == Region.CN


def test_route_for_user_cross_border_blocked():
    set_user_region("u1", Region.CN)
    router = get_region_aware_router()
    decision = router.route_for_user("u1", requested_region=Region.US, is_pii=True)
    assert decision.target_region == Region.CN  # 被强制本地化


def test_route_for_user_cross_border_allowed():
    set_user_region("u1", Region.CN)
    router = get_region_aware_router()
    decision = router.route_for_user(
        "u1",
        requested_region=Region.SG,
        has_cross_border_consent=True,
    )
    assert decision.target_region == Region.SG


def test_route_for_data():
    router = get_region_aware_router()
    decision = router.route_for_data({"_target_region": "us"}, user_id="x", is_pii=True)
    assert decision.target_region == Region.CN  # PII 本地化


def test_get_supabase_config():
    router = get_region_aware_router()
    cfg = router.get_supabase_config(Region.CN)
    assert cfg.region == Region.CN
    assert cfg.storage_bucket == "waibao-cn-storage"


# ---------------------------------------------------------------------------
# config/regions
# ---------------------------------------------------------------------------

def test_regions_has_three():
    assert Region.CN in REGIONS
    assert Region.SG in REGIONS
    assert Region.US in REGIONS


def test_region_for_phone():
    assert region_for_phone("+86 138 0000 0000") == Region.CN
    assert region_for_phone("+1 415 555 1234") == Region.US
    assert region_for_phone("+65 9123 4567") == Region.SG
    assert region_for_phone(None) == Region.CN  # 默认


def test_list_regions_api():
    regions = list_regions()
    codes = [r["code"] for r in regions]
    assert "cn" in codes
    assert "sg" in codes
    assert "us" in codes


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------

def test_residency_decision_audited():
    from compliance.audit import get_audit_logger

    audit = get_audit_logger()
    before = len(audit.query(action="residency_decision", limit=200))
    router = get_region_aware_router()
    router.route_for_user("u1", requested_region=Region.US, is_pii=True)
    after = len(audit.query(action="residency_decision", limit=200))
    assert after >= before + 1