"""v10.0 T5029 — ServiceToggle fallback (registry miss → degrade) tests."""
from __future__ import annotations

import logging

import pytest

from services.platform.service_catalog import (
    PlanTier,
    Service,
    ServiceCategory,
    ServiceStatus,
)
from services.platform.service_toggle import (
    MockToggleRegistry,
    check_service_access_safe,
    is_enabled_safe,
    reset_fallback_state,
    service_toggle,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_fallback_state()
    yield
    reset_fallback_state()


def _register_known(name="agent.profile", *, status=ServiceStatus.ENABLED,
                     plan="free", roles=("jobseeker", "admin")):
    """Register a service directly into the in-memory catalog."""
    svc = Service(
        name=name,
        display_name=name,
        category=ServiceCategory.AGENT,
        plan_required=PlanTier(plan) if plan in ("free", "pro", "enterprise") else plan,
        roles_allowed=list(roles),
        status=status,
    )
    service_toggle.register_service(svc, persist=False, actor_id="test")


# ---------------------------------------------------------------------------
# Registry miss → fallback (default allow)
# ---------------------------------------------------------------------------
def test_registry_miss_falls_back_to_allow():
    # 'totally.unknown.service' is not in the catalog
    assert is_enabled_safe("totally.unknown.service") is True


def test_registry_miss_respects_mock_override_off():
    mock = MockToggleRegistry(default_allow=True)
    mock.set("unknown.feature", False)
    assert is_enabled_safe("unknown.feature", mock=mock) is False


def test_registry_miss_respects_mock_override_on():
    mock = MockToggleRegistry(default_allow=False)
    mock.set("unknown.feature", True)
    assert is_enabled_safe("unknown.feature", mock=mock) is True


def test_mock_registry_default_deny_mode():
    mock = MockToggleRegistry(default_allow=False)
    assert is_enabled_safe("unknown.feature", mock=mock) is False


def test_mock_registry_set_get_remove():
    mock = MockToggleRegistry()
    assert mock.get("x") is None
    mock.set("x", False)
    assert mock.get("x") is False
    mock.remove("x")
    assert mock.get("x") is None


# ---------------------------------------------------------------------------
# Registered service → real gate verdict
# (uses a fake toggle so the test doesn't depend on a live Supabase)
# ---------------------------------------------------------------------------
class _FakeToggle:
    """Minimal ServiceToggle stand-in backed by an in-process dict."""

    def __init__(self):
        self._services: dict[str, Service] = {}

    def register(self, svc: Service) -> None:
        self._services[svc.name] = svc

    def get_service(self, name: str):
        return self._services.get(name)

    def is_enabled(self, name, org_id, plan, role) -> bool:
        svc = self._services.get(name)
        if svc is None:
            return False
        if svc.status == ServiceStatus.DISABLED:
            return False
        return True


def test_registered_enabled_service_is_enabled():
    toggle = _FakeToggle()
    toggle.register(Service(
        name="agent.profile.test", display_name="x",
        category=ServiceCategory.AGENT, plan_required=PlanTier.FREE,
        roles_allowed=["jobseeker"], status=ServiceStatus.ENABLED,
    ))
    assert is_enabled_safe("agent.profile.test", plan="free",
                            role="jobseeker", toggle=toggle) is True


def test_registered_disabled_service_is_disabled():
    toggle = _FakeToggle()
    toggle.register(Service(
        name="agent.profile.disabled", display_name="x",
        category=ServiceCategory.AGENT, plan_required=PlanTier.FREE,
        roles_allowed=["jobseeker"], status=ServiceStatus.DISABLED,
    ))
    assert is_enabled_safe("agent.profile.disabled", plan="free",
                            role="jobseeker", toggle=toggle) is False


# ---------------------------------------------------------------------------
# Warning is emitted on miss (de-duplicated)
# ---------------------------------------------------------------------------
def test_registry_miss_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="recruittech.platform.service_toggle.fallback"):
        is_enabled_safe("brand.new.feature.v2")
    assert any("not in registry" in rec.message for rec in caplog.records)


def test_check_service_access_safe_alias():
    assert (check_service_access_safe("another.unknown.service")
            == is_enabled_safe("another.unknown.service"))


# ---------------------------------------------------------------------------
# get_mock_registry singleton
# ---------------------------------------------------------------------------
def test_get_mock_registry_singleton():
    from services.platform.service_toggle import get_mock_registry
    reg = get_mock_registry()
    reg.set("singleton.feature", True)
    assert get_mock_registry().get("singleton.feature") is True
