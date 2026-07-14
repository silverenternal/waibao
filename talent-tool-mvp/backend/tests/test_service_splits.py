"""v10.0 T5002 — Service-split backward-compatibility tests.

Each >400-line monolith (collaboration_room 1115, predictive 846,
service_toggle 792, billing 681) was split into a package of cohesive
submodules backed by ``_core.py``.  These tests assert the public surface is
identical across every import path so existing callers never break.
"""
from __future__ import annotations

import importlib

import pytest


# ===========================================================================
# collaboration_room: 5 submodules (Room / Thread / Member / Reaction / Mention)
# ===========================================================================
COLLAB_PUBLIC = [
    "ROOM_TYPES", "ROOM_MEMBER_ROLES", "MESSAGE_TYPES",
    "MAX_MESSAGE_LEN", "MAX_NAME_LEN", "MAX_REACTIONS_PER_MESSAGE",
    "RoomError", "NotMemberError", "MessageNotFoundError", "PermissionDeniedError",
    "Room", "RoomMember", "RoomMessage", "RoomReaction",
    "create_room", "get_room", "get_room_with_members", "list_my_rooms",
    "update_room", "archive_room",
    "invite_member", "remove_member", "leave_room", "list_members",
    "post_message", "edit_message", "delete_message",
    "list_messages", "list_thread_replies", "search_messages",
    "add_reaction", "list_reactions",
    "pin_message", "unpin_message", "list_pins",
    "mark_read", "get_unread_count", "get_total_unread_count",
    "list_my_mentions", "mark_mention_read",
]


def _has(obj, name):
    return hasattr(obj, name)


@pytest.mark.parametrize("name", COLLAB_PUBLIC)
def test_collab_public_surface_via_package(name):
    mod = importlib.import_module("services.integrations.collaboration_room")
    assert _has(mod, name), f"collaboration_room package missing {name}"


@pytest.mark.parametrize("name", COLLAB_PUBLIC)
def test_collab_public_surface_via_v5_shim(name):
    mod = importlib.import_module("services.collaboration_room")
    assert _has(mod, name), f"v5.0 shim missing {name}"


def test_collab_private_helpers_still_importable():
    from services.collaboration_room import (  # noqa: F401
        _check_admin, _check_member, _count_unread_for_room,
        _count_unread_batch, _parse_mentions, _now_iso, _get_last_read_at,
    )


class TestCollabSubmodules:
    """Each submodule re-exports its concern's slice."""

    def test_room_submodule(self):
        from services.integrations.collaboration_room import room
        for n in ("create_room", "get_room", "list_my_rooms", "update_room", "archive_room"):
            assert _has(room, n)

    def test_thread_submodule(self):
        from services.integrations.collaboration_room import thread
        for n in ("post_message", "edit_message", "delete_message",
                  "list_messages", "list_thread_replies", "search_messages"):
            assert _has(thread, n)

    def test_member_submodule(self):
        from services.integrations.collaboration_room import member
        for n in ("invite_member", "remove_member", "leave_room", "list_members",
                  "_check_admin", "_check_member"):
            assert _has(member, n)

    def test_reaction_submodule(self):
        from services.integrations.collaboration_room import reaction
        for n in ("add_reaction", "list_reactions", "pin_message",
                  "unpin_message", "list_pins"):
            assert _has(reaction, n)

    def test_mention_submodule(self):
        from services.integrations.collaboration_room import mention
        for n in ("list_my_mentions", "mark_mention_read", "mark_read",
                  "get_unread_count", "get_total_unread_count"):
            assert _has(mention, n)


# ===========================================================================
# predictive: 3 submodules (Model / Forecast / Calibration)
# ===========================================================================
PREDICTIVE_PUBLIC = [
    "AttritionFeatures", "AttritionModel", "AttritionRisk",
    "ForecastPoint", "ForecastResult",
    "HireSuccessModel", "HireSuccessScore",
    "ProphetModel", "celery_beat_task",
    "get_attrition_model", "get_hire_success_model", "train_all_synthetic",
]


@pytest.mark.parametrize("name", PREDICTIVE_PUBLIC)
def test_predictive_public_surface(name):
    mod = importlib.import_module("services.platform.predictive")
    assert _has(mod, name), f"predictive package missing {name}"


def test_predictive_model_submodule():
    from services.platform.predictive import model
    assert _has(model, "AttritionModel")
    assert _has(model, "HireSuccessModel")


# ===========================================================================
# service_toggle: 3 submodules (Registry / Gate / Dependency)
# ===========================================================================
TOGGLE_PUBLIC = [
    "ServiceToggle", "ServiceToggleError", "ServiceNotFoundError",
    "DependencyError", "service_toggle", "invalidate_cache", "CACHE_TTL_SECONDS",
]


@pytest.mark.parametrize("name", TOGGLE_PUBLIC)
def test_service_toggle_public_surface(name):
    mod = importlib.import_module("services.platform.service_toggle")
    assert _has(mod, name), f"service_toggle package missing {name}"


def test_service_toggle_private_internals_writable():
    # tests monkeypatch these on the module object; the split must keep them.
    import services.platform.service_toggle as st
    st._supabase = "x"
    assert st._supabase == "x"


def test_service_toggle_submodules():
    from services.platform.service_toggle import gate, registry, dependency
    assert _has(gate, "service_toggle")
    assert _has(registry, "service_toggle")
    assert _has(dependency, "ServiceToggle")


# ===========================================================================
# billing: 3 submodules (Subscription / Invoice / Usage)
# ===========================================================================
BILLING_PUBLIC = [
    "BillingService", "BillingRepo", "CheckoutResult",
    "Plan", "PlanTier", "BillingInterval", "SubscriptionStatus",
    "list_plans", "get_plan", "format_cny",
]


@pytest.mark.parametrize("name", BILLING_PUBLIC)
def test_billing_public_surface_via_package(name):
    mod = importlib.import_module("services.billing")
    assert _has(mod, name), f"billing package missing {name}"


@pytest.mark.parametrize("name", BILLING_PUBLIC)
def test_billing_public_surface_via_billing_module(name):
    # legacy `services.billing.billing` entrypoint kept alive
    mod = importlib.import_module("services.billing.billing")
    assert _has(mod, name), f"billing.billing missing {name}"


@pytest.mark.parametrize("name", BILLING_PUBLIC)
def test_billing_public_surface_via_v5_shim(name):
    mod = importlib.import_module("services.billing")
    assert _has(mod, name)


def test_billing_submodules():
    from services.billing import subscription, invoice, usage
    for n in ("Plan", "PlanTier", "BillingInterval", "BillingService",
              "list_plans", "get_plan"):
        assert _has(subscription, n)
    assert _has(invoice, "BillingService")
    assert _has(usage, "BillingRepo")
    assert _has(usage, "format_cny")


# ===========================================================================
# behavioural parity — same object identity through the split
# ===========================================================================
class TestIdentityParity:
    def test_collab_post_message_is_same_callable(self):
        from services.integrations.collaboration_room import post_message as a
        from services.integrations.collaboration_room.thread import post_message as b
        from services.collaboration_room import post_message as c
        assert a is b is c

    def test_billing_service_is_same_callable(self):
        from services.billing import BillingService as a
        from services.billing.billing import BillingService as b
        from services.billing.subscription import BillingService as c
        assert a is b is c

    def test_predictive_attrition_model_is_same_callable(self):
        from services.platform.predictive import AttritionModel as a
        from services.platform.predictive.model import AttritionModel as b
        assert a is b

    def test_toggle_singleton_is_same_object(self):
        from services.platform.service_toggle import service_toggle as a
        from services.platform.service_toggle.gate import service_toggle as b
        assert a is b
