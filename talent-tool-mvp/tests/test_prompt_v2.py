"""T2704: Prompt v2 (Agenta vendor-in) tests — registry + A/B traffic + diff."""
from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.platform.prompt_v2 import (
    InMemoryPromptRegistry,
    METRIC_DIMENSIONS,
    PromptMetric,
    PromptRegistryError,
    PromptService,
    PromptStatus,
    PromptVersion,
    get_prompt_service,
    reset_prompt_service,
)


TENANT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _reset():
    reset_prompt_service()
    yield
    reset_prompt_service()


# =====================================================================
# InMemoryPromptRegistry CRUD
# =====================================================================

def test_create_version_increments_number():
    reg = InMemoryPromptRegistry()
    v1 = reg.create_version(tenant_id=TENANT, name="resume", content="hello")
    v2 = reg.create_version(tenant_id=TENANT, name="resume", content="world")
    assert v1.version == 1
    assert v2.version == 2


def test_create_version_validates_required_fields():
    svc = PromptService()
    with pytest.raises(PromptRegistryError):
        svc.create_version(tenant_id="", name="x", content="y")


def test_list_versions_sorted():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a")
    reg.create_version(tenant_id=TENANT, name="p", content="b")
    reg.create_version(tenant_id=TENANT, name="p", content="c")
    rows = reg.list_versions(TENANT, "p")
    assert [r.version for r in rows] == [1, 2, 3]


def test_get_active_prompt_returns_only_active():
    svc = PromptService()
    svc.create_version(tenant_id=TENANT, name="p", content="draft")
    active = svc.create_version(
        tenant_id=TENANT, name="p", content="live",
        traffic_pct=100, status=PromptStatus.ACTIVE,
    )
    got = svc.get_active_prompt(TENANT, "p")
    assert got is not None
    assert got.id == active.id


def test_get_active_prompt_falls_back_to_latest_non_retired():
    svc = PromptService()
    svc.create_version(tenant_id=TENANT, name="p", content="draft",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    svc.retire_version(TENANT, "p", "default", 1)
    fallback = svc.get_active_prompt(TENANT, "p")
    assert fallback is None  # only retired row exists
    # add a new draft row -> fallback returns that
    svc.create_version(tenant_id=TENANT, name="p", content="new draft",
                       status=PromptStatus.DRAFT)
    got = svc.get_active_prompt(TENANT, "p")
    assert got.status == PromptStatus.DRAFT


def test_get_active_prompt_respects_traffic_bucket():
    svc = PromptService()
    v1 = svc.create_version(tenant_id=TENANT, name="p", content="a",
                            traffic_pct=50, status=PromptStatus.ACTIVE)
    v2 = svc.create_version(tenant_id=TENANT, name="p", content="b",
                            traffic_pct=50, status=PromptStatus.ACTIVE)
    # buckets 0..49 -> v1; 50..99 -> v2
    samples = [svc.get_active_prompt(TENANT, "p", bucket=b).id
               for b in range(100)]
    assert v1.id in samples and v2.id in samples


def test_create_version_rejects_invalid_traffic_sum():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    with pytest.raises(PromptRegistryError):
        reg.create_version(tenant_id=TENANT, name="p", content="b",
                           status=PromptStatus.ACTIVE, traffic_pct=100)


def test_retire_version_marks_retired():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="x",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    row = reg.retire_version(TENANT, "p", "default", 1)
    assert row.status == PromptStatus.RETIRED
    assert row.retired_at is not None


def test_retire_unknown_version_raises():
    reg = InMemoryPromptRegistry()
    with pytest.raises(PromptRegistryError):
        reg.retire_version(TENANT, "p", "default", 99)


def test_retire_already_retired_raises():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="x",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    reg.retire_version(TENANT, "p", "default", 1)
    with pytest.raises(PromptRegistryError):
        reg.retire_version(TENANT, "p", "default", 1)


def test_retire_redistributes_traffic_to_active():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=60)
    reg.create_version(tenant_id=TENANT, name="p", content="b",
                       status=PromptStatus.ACTIVE, traffic_pct=40)
    reg.retire_version(TENANT, "p", "default", 1)
    actives = reg.list_active(TENANT, "p")
    assert sum(a.traffic_pct for a in actives) == 100


def test_retire_redistribute_to_specific_version():
    reg = InMemoryPromptRegistry()
    v1 = reg.create_version(tenant_id=TENANT, name="p", content="a",
                            status=PromptStatus.ACTIVE, traffic_pct=50)
    v2 = reg.create_version(tenant_id=TENANT, name="p", content="b",
                            status=PromptStatus.ACTIVE, traffic_pct=50)
    reg.retire_version(TENANT, "p", "default", 1, redistribute_to=v2.id)
    assert v2.traffic_pct == 100
    assert v1.status == PromptStatus.RETIRED


def test_activate_version_changes_status_and_traffic():
    svc = PromptService()
    svc.create_version(tenant_id=TENANT, name="p", content="x",
                       status=PromptStatus.DRAFT)
    svc.activate_version(TENANT, "p", "default", 1, traffic_pct=100)
    got = svc.get_active_prompt(TENANT, "p")
    assert got.status == PromptStatus.ACTIVE


def test_activate_with_wrong_traffic_raises():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    reg.create_version(tenant_id=TENANT, name="p", content="b",
                       status=PromptStatus.DRAFT)
    # activating draft v2 with traffic_pct=50 leaves total at 150 -> reject
    with pytest.raises(PromptRegistryError):
        reg.activate_version(TENANT, "p", "default", 2, traffic_pct=50)


def test_shift_traffic_moves_pct():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=80)
    reg.create_version(tenant_id=TENANT, name="p", content="b",
                       status=PromptStatus.ACTIVE, traffic_pct=20)
    src, dst = reg.shift_traffic(TENANT, "p", "default",
                                 from_version=1, to_version=2, shift_pct=30)
    assert src.traffic_pct == 50
    assert dst.traffic_pct == 50


def test_shift_traffic_rejects_nonpositive():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    with pytest.raises(PromptRegistryError):
        reg.shift_traffic(TENANT, "p", "default",
                          from_version=1, to_version=1, shift_pct=0)


def test_shift_traffic_rejects_overshift():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=80)
    reg.create_version(tenant_id=TENANT, name="p", content="b",
                       status=PromptStatus.ACTIVE, traffic_pct=20)
    with pytest.raises(PromptRegistryError):
        reg.shift_traffic(TENANT, "p", "default",
                          from_version=1, to_version=2, shift_pct=90)


def test_shift_traffic_requires_active_versions():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.DRAFT)
    reg.create_version(tenant_id=TENANT, name="p", content="b",
                       status=PromptStatus.ACTIVE, traffic_pct=100)
    with pytest.raises(PromptRegistryError):
        reg.shift_traffic(TENANT, "p", "default",
                          from_version=1, to_version=2, shift_pct=10)


# =====================================================================
# Render + diff
# =====================================================================

def test_render_substitutes_variables():
    svc = PromptService()
    v = svc.create_version(
        tenant_id=TENANT, name="p",
        content="Hello {{name}}, your role is {{role}}.",
        variables=["name", "role"],
    )
    out = svc.render(v, {"name": "Alice", "role": "PM"})
    assert out == "Hello Alice, your role is PM."


def test_render_leaves_unknown_placeholders():
    svc = PromptService()
    v = svc.create_version(
        tenant_id=TENANT, name="p", content="Hi {{name}}"
    )
    out = svc.render(v, {})
    assert out == "Hi {{name}}"


def test_diff_marks_unchanged():
    svc = PromptService()
    v1 = svc.create_version(tenant_id=TENANT, name="p", content="same")
    v2 = svc.create_version(tenant_id=TENANT, name="p", content="same")
    d = svc.diff(v1, v2)
    assert d["changed"] is False


def test_diff_marks_changed_and_returns_diff_text():
    svc = PromptService()
    v1 = svc.create_version(tenant_id=TENANT, name="p", content="alpha\nbeta")
    v2 = svc.create_version(tenant_id=TENANT, name="p", content="alpha\ngamma")
    d = svc.diff(v1, v2)
    assert d["changed"] is True
    assert "---" in d["diff"]
    assert "+gamma" in d["diff"]


# =====================================================================
# Metric constants
# =====================================================================

def test_metric_dimensions_are_the_four():
    assert METRIC_DIMENSIONS == ("accuracy", "fluency", "safety", "bias")


def test_record_and_list_metric():
    reg = InMemoryPromptRegistry()
    p = reg.create_version(tenant_id=TENANT, name="p", content="x")
    reg.record_metric(PromptMetric(prompt_id=p.id, version=p.version,
                                   metric_name="accuracy", value=0.9,
                                   sample_size=10))
    rows = reg.list_metrics(p.id, metric_name="accuracy")
    assert len(rows) == 1
    assert rows[0].value == 0.9


def test_list_metrics_filters_by_name():
    reg = InMemoryPromptRegistry()
    p = reg.create_version(tenant_id=TENANT, name="p", content="x")
    reg.record_metric(PromptMetric(prompt_id=p.id, version=1,
                                   metric_name="accuracy", value=0.9))
    reg.record_metric(PromptMetric(prompt_id=p.id, version=1,
                                   metric_name="fluency", value=0.8))
    a = reg.list_metrics(p.id, metric_name="accuracy")
    f = reg.list_metrics(p.id, metric_name="fluency")
    assert len(a) == 1 and len(f) == 1


def test_list_metrics_respects_limit():
    reg = InMemoryPromptRegistry()
    p = reg.create_version(tenant_id=TENANT, name="p", content="x")
    for i in range(5):
        reg.record_metric(PromptMetric(prompt_id=p.id, version=1,
                                       metric_name="accuracy", value=0.5 + i * 0.01))
    rows = reg.list_metrics(p.id, limit=3)
    assert len(rows) == 3


# =====================================================================
# Singleton + dataclasses
# =====================================================================

def test_singleton_prompt_service():
    s1 = get_prompt_service()
    s2 = get_prompt_service()
    assert s1 is s2


def test_reset_prompt_service_clears():
    s1 = get_prompt_service()
    reset_prompt_service()
    s2 = get_prompt_service()
    assert s1 is not s2


def test_prompt_version_to_dict_includes_all_fields():
    v = PromptVersion(name="p", content="hi", version=3,
                      variables=["x"], tags=["a"])
    d = v.to_dict()
    assert d["name"] == "p"
    assert d["version"] == 3
    assert d["variables"] == ["x"]
    assert d["tags"] == ["a"]


def test_prompt_metric_to_dict_includes_all_fields():
    m = PromptMetric(prompt_id="abc", version=1, metric_name="x",
                     value=0.5, sample_size=10)
    d = m.to_dict()
    assert d["prompt_id"] == "abc"
    assert d["sample_size"] == 10


def test_prompt_status_enum_values():
    assert PromptStatus.DRAFT.value == "draft"
    assert PromptStatus.ACTIVE.value == "active"
    assert PromptStatus.RETIRED.value == "retired"


def test_create_version_with_metadata_and_tags():
    svc = PromptService()
    v = svc.create_version(
        tenant_id=TENANT, name="p", content="hi",
        tags=["experiment-2026Q3"],
        metadata={"owner": "alice"},
        created_by="alice",
    )
    assert v.created_by == "alice"
    assert "experiment-2026Q3" in v.tags


def test_create_version_with_parent_version():
    svc = PromptService()
    parent = svc.create_version(tenant_id=TENANT, name="p", content="v1")
    child = svc.create_version(tenant_id=TENANT, name="p", content="v2",
                                parent_version=parent.version)
    assert child.parent_version == 1
    assert child.version == 2


def test_list_versions_empty_for_unknown_prompt():
    svc = PromptService()
    assert svc.list_versions(TENANT, "unknown") == []


def test_active_traffic_must_sum_to_100_validator():
    reg = InMemoryPromptRegistry()
    reg.create_version(tenant_id=TENANT, name="p", content="a",
                       status=PromptStatus.ACTIVE, traffic_pct=60)
    # second active with 30 -> total 90 -> reject
    with pytest.raises(PromptRegistryError) as exc:
        reg.create_version(tenant_id=TENANT, name="p", content="b",
                           status=PromptStatus.ACTIVE, traffic_pct=30)
    assert exc.value.code == "traffic_invalid"