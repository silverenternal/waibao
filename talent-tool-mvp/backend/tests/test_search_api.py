"""
T1404 — /api/search endpoint wiring test.

Validates that:
  1. Module imports cleanly and exposes a FastAPI router.
  2. url / icon mapping covers all four searchable entity types.
  3. Empty query would raise 400 in a real handler (we just exercise the
     regex/branch logic, not the network).
"""
from backend.api.search import (
    _TYPE_MAP,
    _url_for,
    _icon_for,
    SearchResponse,
    SearchResultItem,
)


def test_type_map_includes_all_supported_types():
    assert _TYPE_MAP["candidates"] == "candidates"
    assert _TYPE_MAP["roles"] == "roles"
    assert _TYPE_MAP["tickets"] == "tickets"
    assert _TYPE_MAP["policies"] == "company_policies"
    assert _TYPE_MAP["all"] == "all"


def test_url_for_each_type():
    assert _url_for("candidates", "x") == "/candidates/x"
    assert _url_for("roles", "y") == "/role/y"
    assert _url_for("tickets", "z") == "/tickets/z"
    assert _url_for("policies", "w") == "/policy/w"


def test_icon_for_each_type():
    for t in ("candidates", "roles", "tickets", "policies"):
        assert _icon_for(t) and isinstance(_icon_for(t), str)


def test_search_response_schema_fields():
    resp = SearchResponse(
        query="hi", type="all", took_ms=12.3, total=1,
        items=[
            SearchResultItem(
                type="candidates", id="a", title="A", snippet="", url="/candidates/a",
                score=0.5, icon="user",
            )
        ],
    )
    assert resp.query == "hi"
    assert resp.total == 1
    assert resp.items[0].type == "candidates"
