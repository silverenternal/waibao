"""T2301 — 对比服务测试.

覆盖:
- 5 维度对齐
- top-3 差异高亮
- candidate / role 双模式
- 边界 (1 项/6 项/缺失维度)
- saved_comparisons 持久化
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict
from unittest.mock import MagicMock
from uuid import UUID

import pytest

# 允许直接 import services.matching.comparison
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.matching.comparison import (  # noqa: E402
    COMPARISON_DIMENSIONS,
    DIMENSION_LABELS,
    CompareItem,
    ComparisonService,
    DimensionScore,
    DiffResult,
    build_candidate_items,
    build_role_items,
    compute_diff,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_item(cid: str, dims: dict[str, float], name: str | None = None) -> CompareItem:
    return CompareItem(
        id=cid,
        name=name or cid,
        type="candidate",
        dimensions={
            k: DimensionScore(k, float(v)) for k, v in dims.items()
        },
        attributes={},
        overall_score=sum(dims.values()) / max(len(dims), 1),
    )


@pytest.fixture
def three_candidates():
    return [
        make_item("c1", {"skill": 90, "experience": 80, "education": 70, "culture": 75, "potential": 85}),
        make_item("c2", {"skill": 60, "experience": 65, "education": 80, "culture": 90, "potential": 70}),
        make_item("c3", {"skill": 75, "experience": 50, "education": 60, "culture": 60, "potential": 95}),
    ]


# ---------------------------------------------------------------------------
# 1. compute_diff 基础
# ---------------------------------------------------------------------------


def test_compute_diff_returns_all_5_dimensions(three_candidates):
    result = compute_diff(three_candidates)
    assert len(result.diff_dimensions) == 5
    dims = {d.dimension for d in result.diff_dimensions}
    assert dims == set(COMPARISON_DIMENSIONS)


def test_compute_diff_calculates_spread_correctly(three_candidates):
    result = compute_diff(three_candidates)
    skill = next(d for d in result.diff_dimensions if d.dimension == "skill")
    # skill: 90, 60, 75 → spread = 30
    assert skill.spread == pytest.approx(30.0)
    # values 顺序对齐输入顺序
    assert skill.values == [90.0, 60.0, 75.0]
    assert skill.items == ["c1", "c2", "c3"]


def test_compute_diff_highlights_top_3(three_candidates):
    result = compute_diff(three_candidates, top_n=3)
    assert len(result.highlights) == 3
    # highest spread first
    spreads = [h.spread for h in result.highlights]
    assert spreads == sorted(spreads, reverse=True)


def test_compute_diff_top_n_capped(three_candidates):
    result = compute_diff(three_candidates, top_n=5)
    assert len(result.highlights) == 5


def test_compute_diff_rejects_single_item():
    with pytest.raises(ValueError, match="至少 2"):
        compute_diff([make_item("c1", {"skill": 50})])


def test_compute_diff_rejects_too_many():
    items = [make_item(f"c{i}", {"skill": i * 10}) for i in range(6)]
    with pytest.raises(ValueError):
        compute_diff(items)


def test_compute_diff_handles_missing_dimensions():
    items = [
        CompareItem(id="c1", name="c1", type="candidate",
                    dimensions={"skill": DimensionScore("skill", 80)}),
        CompareItem(id="c2", name="c2", type="candidate",
                    dimensions={"skill": DimensionScore("skill", 60)}),
    ]
    result = compute_diff(items)
    # 缺失维度填 0
    skill = next(d for d in result.diff_dimensions if d.dimension == "skill")
    assert skill.values == [80.0, 60.0]
    # 缺失维度 (experience) 视为 0 vs 0,spread=0
    exp = next(d for d in result.diff_dimensions if d.dimension == "experience")
    assert exp.spread == 0.0


def test_diff_dimensions_ranked_in_order(three_candidates):
    result = compute_diff(three_candidates)
    ranks = [d.rank for d in result.diff_dimensions]
    assert ranks == list(range(1, 6))


def test_diff_dimensions_labels_localized():
    for d in COMPARISON_DIMENSIONS:
        assert d in DIMENSION_LABELS
    assert DIMENSION_LABELS["skill"] == "技能匹配"


def test_diff_result_serializable(three_candidates):
    result = compute_diff(three_candidates)
    d = result.to_dict()
    assert "items" in d and "diff_dimensions" in d and "highlights" in d
    assert "created_at" in d
    assert len(d["diff_dimensions"]) == 5


def test_stddev_calculation():
    items = [
        make_item("c1", {"skill": 100}),
        make_item("c2", {"skill": 50}),
        make_item("c3", {"skill": 50}),
    ]
    result = compute_diff(items)
    skill = next(d for d in result.diff_dimensions if d.dimension == "skill")
    # 100, 50, 50 → mean=66.67, sample stdev ≈ 28.87
    assert skill.stddev == pytest.approx(28.87, abs=0.1)


# ---------------------------------------------------------------------------
# 2. build_candidate_items
# ---------------------------------------------------------------------------


def test_build_candidate_items_basic():
    candidates = [
        {"id": "c1", "name": "Alice", "experience_years": 5,
         "education": [{"school": "MIT"}], "tags": ["potential_high"]},
        {"id": "c2", "name": "Bob", "experience_years": 2, "education": [],
         "tags": []},
    ]
    role = {"id": "r1", "min_experience_years": 3}
    matches = {
        "c1": {
            "overall_score": 0.85,
            "skill_overlap": [
                {"matched": True}, {"matched": True}, {"matched": False},
            ],
            "scoring_breakdown": {"skill": 0.8, "experience": 0.7, "culture": 0.6},
        },
        "c2": {
            "overall_score": 0.55,
            "skill_overlap": [
                {"matched": True}, {"matched": False},
            ],
            "scoring_breakdown": {"skill": 0.5, "experience": 0.4, "culture": 0.5},
        },
    }
    items = build_candidate_items(candidates, {"r1": role}, matches)
    assert len(items) == 2
    c1 = items[0]
    assert c1.id == "c1"
    assert c1.name == "Alice"
    # skill: 2/3 matched = 66.7%
    assert c1.dimensions["skill"].score == pytest.approx(66.7, abs=0.1)
    # potential_high tag
    assert c1.dimensions["potential"].score == 90.0
    # overall from match
    assert c1.overall_score == pytest.approx(85.0)


def test_build_candidate_items_without_role():
    candidates = [{"id": "c1", "name": "Alice", "experience_years": 0}]
    items = build_candidate_items(candidates)
    # 缺 role + match → experience fallback 70
    assert items[0].dimensions["experience"].score == 70.0


def test_build_candidate_items_preserves_order():
    candidates = [
        {"id": "c1", "name": "A"},
        {"id": "c2", "name": "B"},
        {"id": "c3", "name": "C"},
    ]
    items = build_candidate_items(candidates)
    assert [i.id for i in items] == ["c1", "c2", "c3"]


# ---------------------------------------------------------------------------
# 3. build_role_items
# ---------------------------------------------------------------------------


def test_build_role_items_5_dimensions():
    roles = [
        {"id": "r1", "title": "Backend", "seniority": "senior",
         "required_skills": ["py", "go", "k8s"], "nice_to_have_skills": ["rust"],
         "min_experience_years": 5},
        {"id": "r2", "title": "Frontend", "seniority": "mid",
         "required_skills": ["ts", "react"], "nice_to_have_skills": [],
         "min_experience_years": 2},
    ]
    items = build_role_items(roles)
    assert len(items) == 2
    for item in items:
        assert set(item.dimensions.keys()) == set(COMPARISON_DIMENSIONS)
        assert item.type == "role"


def test_build_role_items_seniority_potential_boost():
    senior = {"id": "r1", "title": "Staff", "seniority": "staff",
              "required_skills": [], "nice_to_have_skills": [], "min_experience_years": 8}
    junior = {"id": "r2", "title": "Jr", "seniority": "junior",
              "required_skills": [], "nice_to_have_skills": [], "min_experience_years": 1}
    items = build_role_items([senior, junior])
    assert items[0].dimensions["potential"].score > items[1].dimensions["potential"].score


def test_build_role_items_includes_match_score():
    roles = [{"id": "r1", "title": "X", "seniority": "senior",
              "required_skills": [], "nice_to_have_skills": [], "min_experience_years": 5}]
    matches = [{"overall_score": 0.8}, {"overall_score": 0.6}]
    items = build_role_items(roles, matches_by_role={"r1": matches})
    # avg = 0.7 → 70
    assert items[0].overall_score == 70.0


# ---------------------------------------------------------------------------
# 4. ComparisonService (mocked supabase)
# ---------------------------------------------------------------------------


def _mock_supabase(table_data: dict[str, list[dict]]):
    """构建 mock supabase,每个 table 返回预设 rows."""
    supabase = MagicMock()

    def table(name):
        t = MagicMock()
        t_data = table_data.get(name, [])

        # chainable
        for method in ("select", "eq", "in_", "order", "range", "single", "insert",
                       "update", "delete", "gte", "lte", "neq", "or_", "like"):
            getattr(t, method).return_value = t

        def execute():
            r = MagicMock()
            r.data = t_data
            r.count = len(t_data)
            return r

        t.execute = execute
        return t

    supabase.table = table
    return supabase


@pytest.mark.asyncio
async def test_compare_candidates_success():
    supabase = _mock_supabase({
        "candidates": [
            {"id": "c1", "name": "A", "experience_years": 5,
             "education": [{"s": "x"}], "tags": []},
            {"id": "c2", "name": "B", "experience_years": 3,
             "education": [], "tags": []},
        ],
        "matches": [
            {"candidate_id": "c1", "role_id": "r1",
             "overall_score": 0.8, "skill_overlap": [{"matched": True}],
             "scoring_breakdown": {}},
            {"candidate_id": "c2", "role_id": "r1",
             "overall_score": 0.6, "skill_overlap": [{"matched": False}],
             "scoring_breakdown": {}},
        ],
        "roles": [{"id": "r1", "min_experience_years": 3}],
    })
    service = ComparisonService(supabase)
    result = await service.compare_candidates(
        [UUID("00000000-0000-0000-0000-000000000001"),
         UUID("00000000-0000-0000-0000-000000000002")]
    )
    assert isinstance(result, DiffResult)
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_compare_candidates_missing_raises():
    supabase = _mock_supabase({"candidates": [{"id": "c1"}]})
    service = ComparisonService(supabase)
    with pytest.raises(ValueError, match="未找到"):
        await service.compare_candidates(
            [UUID("00000000-0000-0000-0000-000000000001"),
             UUID("00000000-0000-0000-0000-000000000002")]
        )


@pytest.mark.asyncio
async def test_compare_roles_success():
    supabase = _mock_supabase({
        "roles": [
            {"id": "r1", "title": "Backend", "seniority": "senior",
             "required_skills": ["py"], "nice_to_have_skills": [],
             "min_experience_years": 5},
            {"id": "r2", "title": "Frontend", "seniority": "mid",
             "required_skills": ["ts"], "nice_to_have_skills": [],
             "min_experience_years": 2},
        ],
        "matches": [],
    })
    service = ComparisonService(supabase)
    result = await service.compare_roles(
        [UUID("00000000-0000-0000-0000-000000000001"),
         UUID("00000000-0000-0000-0000-000000000002")]
    )
    assert len(result.items) == 2
    assert result.items[0].type == "role"


@pytest.mark.asyncio
async def test_save_comparison_persists():
    supabase = _mock_supabase({})
    service = ComparisonService(supabase)
    saved = await service.save_comparison(
        user_id=UUID("00000000-0000-0000-0000-000000000099"),
        item_type="candidate",
        item_ids=["c1", "c2"],
        payload={"highlights": []},
        title="My Compare",
    )
    assert saved["user_id"] == "00000000-0000-0000-0000-000000000099"
    assert saved["item_type"] == "candidate"


@pytest.mark.asyncio
async def test_list_saved_filters_by_user():
    supabase = _mock_supabase({
        "saved_comparisons": [{"id": "s1", "user_id": "u1"}]
    })
    service = ComparisonService(supabase)
    items = await service.list_saved(UUID("00000000-0000-0000-0000-000000000001"))
    assert len(items) == 1


@pytest.mark.asyncio
async def test_get_saved_returns_none_if_missing():
    supabase = MagicMock()
    empty_result = MagicMock()
    empty_result.data = None
    chain = MagicMock()
    chain.execute = MagicMock(return_value=empty_result)
    table_mock = MagicMock()
    table_mock.select.return_value.eq.return_value.eq.return_value.single.return_value = chain
    supabase.table.return_value = table_mock
    service = ComparisonService(supabase)
    saved = await service.get_saved(
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    )
    assert saved is None


# ---------------------------------------------------------------------------
# 5. 端点测试 (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """构建带 mock 的 FastAPI app."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.auth import CurrentUser, get_current_user
    from api.match_compare import (
        match_compare_router,
        roles_compare_router,
    )
    from contracts.shared import UserRole

    fake_user = CurrentUser(
        id=UUID("00000000-0000-0000-0000-000000000099"),
        email="test@example.com",
        role=UserRole.talent_partner,
        organisation_id=None,
    )

    # 注入 mock supabase
    supabase = _mock_supabase({
        "candidates": [
            {"id": "00000000-0000-0000-0000-000000000001",
             "name": "Alice", "experience_years": 5, "education": [], "tags": []},
            {"id": "00000000-0000-0000-0000-000000000002",
             "name": "Bob", "experience_years": 3, "education": [], "tags": []},
        ],
        "matches": [
            {"candidate_id": "00000000-0000-0000-0000-000000000001",
             "role_id": "00000000-0000-0000-0000-0000000000a1",
             "overall_score": 0.8, "skill_overlap": [{"matched": True}],
             "scoring_breakdown": {}},
            {"candidate_id": "00000000-0000-0000-0000-000000000002",
             "role_id": "00000000-0000-0000-0000-0000000000a1",
             "overall_score": 0.6, "skill_overlap": [{"matched": False}],
             "scoring_breakdown": {}},
        ],
        "roles": [{"id": "00000000-0000-0000-0000-0000000000a1",
                   "min_experience_years": 3}],
        "saved_comparisons": [],
    })

    async def override_user():
        return fake_user

    def override_supabase():
        return supabase

    app = FastAPI()
    app.include_router(match_compare_router)
    app.include_router(roles_compare_router)
    app.dependency_overrides[get_current_user] = override_user
    from api.deps import get_supabase
    app.dependency_overrides[get_supabase] = override_supabase
    return TestClient(app), supabase


def test_api_compare_candidates_returns_5d(api_client):
    client, _ = api_client
    r = client.get(
        "/api/match/compare"
        "?ids=00000000-0000-0000-0000-000000000001,"
        "00000000-0000-0000-0000-000000000002"
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["diff_dimensions"]) == 5
    assert len(data["highlights"]) == 3


def test_api_compare_candidates_rejects_single(api_client):
    client, _ = api_client
    r = client.get(
        "/api/match/compare?ids=00000000-0000-0000-0000-000000000001"
    )
    assert r.status_code == 400


def test_api_compare_candidates_invalid_uuid(api_client):
    client, _ = api_client
    r = client.get("/api/match/compare?ids=not-a-uuid,c2")
    assert r.status_code == 400


def test_api_compare_roles(api_client):
    client, _ = api_client
    # 替换 supabase 为 role 数据
    role_supabase = _mock_supabase({
        "roles": [
            {"id": "00000000-0000-0000-0000-0000000000a1",
             "title": "Backend", "seniority": "senior",
             "required_skills": ["py"], "nice_to_have_skills": [],
             "min_experience_years": 5},
            {"id": "00000000-0000-0000-0000-0000000000a2",
             "title": "Frontend", "seniority": "mid",
             "required_skills": ["ts"], "nice_to_have_skills": [],
             "min_experience_years": 2},
        ],
        "matches": [],
    })
    from api.deps import get_supabase
    client.app.dependency_overrides[get_supabase] = lambda: role_supabase

    r = client.get(
        "/api/mothership/roles/compare"
        "?ids=00000000-0000-0000-0000-0000000000a1,"
        "00000000-0000-0000-0000-0000000000a2"
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["type"] == "role"


def test_api_save_comparison(api_client):
    client, _ = api_client
    r = client.post(
        "/api/match/compare/save",
        json={
            "item_type": "candidate",
            "item_ids": ["c1", "c2"],
            "payload": {"highlights": []},
            "title": "Test",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test"


def test_api_save_comparison_validates_count(api_client):
    client, _ = api_client
    r = client.post(
        "/api/match/compare/save",
        json={
            "item_type": "candidate",
            "item_ids": ["c1"],
            "payload": {},
        },
    )
    assert r.status_code == 400


def test_api_save_comparison_validates_type(api_client):
    client, _ = api_client
    r = client.post(
        "/api/match/compare/save",
        json={
            "item_type": "invalid",
            "item_ids": ["c1", "c2"],
            "payload": {},
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 6. 集成测试 — 对比服务的端到端数据流
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_candidate_compare_with_role():
    """带 role context 的候选人对比."""
    candidates = [
        {"id": "c1", "name": "Alice", "experience_years": 8,
         "education": [{"s": "X"}], "tags": ["potential_high"]},
        {"id": "c2", "name": "Bob", "experience_years": 4,
         "education": [], "tags": []},
    ]
    role = {"id": "r1", "min_experience_years": 5}
    matches = {
        "c1": {"overall_score": 0.9, "skill_overlap": [
            {"matched": True}, {"matched": True}],
            "scoring_breakdown": {"experience": 1.0}},
        "c2": {"overall_score": 0.5, "skill_overlap": [
            {"matched": False}],
            "scoring_breakdown": {"experience": 0.8}},
    }
    items = build_candidate_items(candidates, {"r1": role}, matches)
    result = compute_diff(items)
    exp = next(d for d in result.diff_dimensions if d.dimension == "experience")
    # scoring_breakdown 提供 1.0 / 0.8 → 100 / 80
    assert exp.values[0] == 100.0
    assert exp.values[1] == 80.0


@pytest.mark.asyncio
async def test_diff_highlights_consistency():
    """top-3 highlights 必须是 diff_dimensions 的子集."""
    items = [
        make_item("c1", {"skill": 95, "experience": 50, "education": 50,
                          "culture": 50, "potential": 50}),
        make_item("c2", {"skill": 50, "experience": 95, "education": 50,
                          "culture": 50, "potential": 50}),
    ]
    result = compute_diff(items)
    highlight_dims = {h.dimension for h in result.highlights}
    all_dims = {d.dimension for d in result.diff_dimensions}
    assert highlight_dims.issubset(all_dims)
    assert len(highlight_dims) == 3


def test_to_dict_contains_serializable_data():
    item = make_item("c1", {"skill": 80})
    d = item.to_dict()
    assert "id" in d
    assert "dimensions" in d
    assert "skill" in d["dimensions"]
    assert isinstance(d["dimensions"]["skill"]["score"], float)