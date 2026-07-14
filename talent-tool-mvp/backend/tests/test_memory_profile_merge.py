"""v10.0 T5029 — profile_updated merge into Mem0 tests."""
from __future__ import annotations

import uuid

import pytest

from eventbus.base import InMemoryEventBus
from services.memory.memory_v2 import (
    PROFILE_FIELDS,
    ProfileMemoryMerger,
    get_profile_memory_merger,
    reset_profile_memory_merger,
)
from services.memory.store import MemoryStore


@pytest.fixture
def merger():
    return ProfileMemoryMerger(store=MemoryStore())


def test_apply_update_creates_one_fact_per_field(merger):
    user = uuid.uuid4()
    touched = merger.apply_update(
        user_id=user,
        fields={"current_role": "Senior Engineer", "location": "Shanghai"},
    )
    assert len(touched) == 2
    facts = merger.profile_facts(user)
    assert len(facts) == 2
    fields = {f.metadata["profile_field"] for f in facts}
    assert fields == {"current_role", "location"}


def test_apply_update_merges_existing_field_no_duplicate(merger):
    user = uuid.uuid4()
    merger.apply_update(user_id=user, fields={"current_role": "Engineer"})
    merger.apply_update(user_id=user, fields={"current_role": "Senior Engineer"})
    facts = merger.profile_facts(user)
    assert len(facts) == 1  # merged, not duplicated
    assert facts[0].metadata["profile_value"] == "Senior Engineer"
    assert facts[0].content == "profile.current_role = Senior Engineer"
    # prior value retained for audit
    assert facts[0].metadata.get("prior_values") == ["Engineer"]


def test_apply_update_idempotent_same_value(merger):
    user = uuid.uuid4()
    merger.apply_update(user_id=user, fields={"location": "Beijing"})
    merger.apply_update(user_id=user, fields={"location": "Beijing"})
    facts = merger.profile_facts(user)
    assert len(facts) == 1
    # no prior values recorded (value unchanged)
    assert facts[0].metadata.get("prior_values", []) == []


def test_apply_update_ignores_non_profile_fields(merger):
    user = uuid.uuid4()
    touched = merger.apply_update(
        user_id=user,
        fields={"current_role": "Engineer", "transient_flag": "x", "session_id": 123},
    )
    assert len(touched) == 1
    assert touched[0].metadata["profile_field"] == "current_role"


def test_apply_update_ignores_empty_values(merger):
    user = uuid.uuid4()
    touched = merger.apply_update(
        user_id=user,
        fields={"current_role": "", "location": None, "seniority": "senior"},
    )
    assert len(touched) == 1
    assert touched[0].metadata["profile_field"] == "seniority"


def test_list_value_rendered_as_csv(merger):
    user = uuid.uuid4()
    merger.apply_update(user_id=user, fields={"skills": ["python", "fastapi", "redis"]})
    facts = merger.profile_facts(user)
    assert len(facts) == 1
    assert facts[0].metadata["profile_value"] == "python, fastapi, redis"


def test_sync_agent_context_builds_prompt_block(merger):
    user = uuid.uuid4()
    merger.apply_update(user_id=user,
                        fields={"current_role": "Engineer", "location": "Shanghai"})
    block = merger.sync_agent_context(user)
    assert block.startswith("[PROFILE — merged from profile.updated events]")
    assert "current_role: Engineer" in block
    assert "location: Shanghai" in block


def test_sync_agent_context_empty_when_no_facts(merger):
    block = merger.sync_agent_context(uuid.uuid4())
    assert block == ""


def test_event_driven_apply_via_bus():
    bus = InMemoryEventBus()
    merger = ProfileMemoryMerger(store=MemoryStore())
    merger.start(bus=bus)
    user = uuid.uuid4()
    bus.emit("profile.updated", {
        "user_id": str(user),
        "fields": {"current_role": "Engineer", "location": "Hangzhou"},
        "tenant_id": None,
    }, source="profile_agent")
    facts = merger.profile_facts(user)
    assert len(facts) == 2


def test_profile_fields_whitelist_includes_core():
    for f in ("current_role", "location", "skills", "seniority", "years_experience"):
        assert f in PROFILE_FIELDS


def test_singleton_get_and_reset():
    reset_profile_memory_merger()
    m1 = get_profile_memory_merger(store=MemoryStore())
    m2 = get_profile_memory_merger()
    assert m1 is m2
    reset_profile_memory_merger()
