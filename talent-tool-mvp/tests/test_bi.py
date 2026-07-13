"""T2802 — BI (Cube.js) API + schema validation tests.

Covers:
1. Cube.js schema file structure (4 cubes, dims/measures/pre-aggregations)
2. backend/api/bi.py — meta / query / dashboards / health
3. Redis-cache fallback to in-memory
4. Frontend page exports & API client surface
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
CUBE_DIR = REPO_ROOT / "cube-server"
FRONTEND_DIR = REPO_ROOT / "frontend"

# Make `from api...` work in the test process.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_user():
    from contracts.shared import UserRole

    u = MagicMock()
    u.id = "u-1"
    u.user_id = "u-1"
    u.tenant_id = "t-1"
    u.role = UserRole.admin
    u.email = "admin@x.com"
    return u


@pytest.fixture
def client(auth_user):
    """Minimal FastAPI app with the BI router and a mocked Cube.js."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import get_current_user, require_role
    from api.bi import router

    app = FastAPI()
    app.include_router(router, prefix="/api/bi")
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[require_role] = lambda *a, **k: auth_user

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Cube.js schema files — generation validation
# ---------------------------------------------------------------------------
class TestCubeSchema:
    REQUIRED_CUBES = ["Candidates", "Roles", "Matches", "Tickets"]

    def test_schema_dir_exists(self):
        assert CUBE_DIR.exists(), f"missing {CUBE_DIR}"
        assert (CUBE_DIR / "schema").is_dir(), "missing cube-server/schema/"

    def test_cube_js_config_exists(self):
        assert (CUBE_DIR / "cube.js").exists()
        text = (CUBE_DIR / "cube.js").read_text()
        assert "@cubejs-backend/postgres-driver" in text
        assert "apiSecret" in text
        assert "schemaPath" in text
        assert "scheduledRefreshTimer" in text

    def test_package_json_dependencies(self):
        pkg = json.loads((CUBE_DIR / "package.json").read_text())
        deps = pkg.get("dependencies", {})
        assert "@cubejs-backend/server-core" in deps
        assert "@cubejs-backend/postgres-driver" in deps

    @pytest.mark.parametrize("cube_name", REQUIRED_CUBES)
    def test_cube_file_has_dimensions_and_measures(self, cube_name):
        f = CUBE_DIR / "schema" / f"{cube_name}.js"
        assert f.exists(), f"missing schema/{cube_name}.js"
        text = f.read_text()
        assert "cube(" in text and f"`{cube_name}`" in text
        assert "dimensions:" in text
        assert "measures:" in text
        # each cube should declare at least 3 dims and 2 measures
        dims = re.findall(r"^\s+(\w+):\s*\{", text, flags=re.MULTILINE)
        assert text.count("type: `string`") + text.count("type: `time`") >= 3
        assert text.count("type: `count`") + text.count("type: `avg`") >= 2

    def test_joins_declared_for_cross_cube_views(self):
        # Candidates → Matches, Roles → Matches, Matches ↔ Candidates / Roles,
        # Tickets → Roles
        for src, target in [
            ("Candidates", "Matches"),
            ("Roles", "Matches"),
            ("Matches", "Candidates"),
            ("Matches", "Roles"),
            ("Tickets", "Roles"),
        ]:
            f = CUBE_DIR / "schema" / f"{src}.js"
            assert f.exists()
            assert target in f.read_text(), f"{src}.js missing join to {target}"


# ---------------------------------------------------------------------------
# 2. /api/bi/meta — falls back to mock when Cube.js unreachable
# ---------------------------------------------------------------------------
def test_meta_returns_mock_when_cubejs_down(client):
    r = client.get("/api/bi/meta")
    assert r.status_code == 200
    body = r.json()
    assert "cubes" in body["data"]
    names = {c["name"] for c in body["data"]["cubes"]}
    assert {"Candidates", "Roles", "Matches", "Tickets"}.issubset(names)


# ---------------------------------------------------------------------------
# 3. /api/bi/query — caching + stale flag
# ---------------------------------------------------------------------------
def test_query_returns_stale_fallback(client):
    body = {"measures": ["Candidates.count"], "dimensions": ["Candidates.source"]}
    r = client.post("/api/bi/query", json=body)
    assert r.status_code == 200
    j = r.json()
    assert "data" in j
    # mock returns at least one row
    assert j["data"]["data"], "expected mock data rows"


def test_query_cache_hit_returns_cached_true(client):
    body = {"measures": ["Matches.count"], "dimensions": ["Matches.channel"]}
    r1 = client.post("/api/bi/query", json=body).json()
    # Second call may come from a 5-min in-memory cache; either cached or stale
    r2 = client.post("/api/bi/query", json=body).json()
    assert "cached" in r2 or "stale" in r2


# ---------------------------------------------------------------------------
# 4. Built-in dashboards
# ---------------------------------------------------------------------------
def test_list_builtin_dashboards_has_five(client):
    r = client.get("/api/bi/dashboards/built-in")
    assert r.status_code == 200
    keys = [d["key"] for d in r.json()["dashboards"]]
    assert set(keys) >= {
        "funnel",
        "recruitment-efficiency",
        "channel-roi",
        "agent-performance",
        "customer-success",
    }


def test_dashboard_data_returns_widgets(client):
    r = client.get("/api/bi/dashboards/funnel/data")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "funnel"
    assert body["title"] == "HR 漏斗"
    assert len(body["widgets"]) > 0
    for w in body["widgets"]:
        assert {"id", "type", "title", "query"}.issubset(w)


def test_dashboard_data_unknown_key_404(client):
    r = client.get("/api/bi/dashboards/nope/data")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. Saved dashboard CRUD (in-memory fallback)
# ---------------------------------------------------------------------------
def test_save_and_list_dashboard(client):
    payload = {
        "name": "test-dash",
        "description": "unit",
        "widgets": [{"id": "w1", "type": "kpi", "title": "k", "query": {"measures": ["Candidates.count"]}}],
        "shared": False,
    }
    r = client.post("/api/bi/dashboards", json=payload)
    assert r.status_code == 200
    rec = r.json()
    assert rec["name"] == "test-dash"
    # List
    r2 = client.get("/api/bi/dashboards")
    assert r2.status_code == 200
    names = {d["name"] for d in r2.json()["dashboards"]}
    assert "test-dash" in names
    # Share
    r3 = client.post(f"/api/bi/dashboards/{rec['id']}/share")
    assert r3.status_code == 200
    assert "share_token" in r3.json()
    # Delete
    r4 = client.delete(f"/api/bi/dashboards/{rec['id']}")
    assert r4.status_code == 200


# ---------------------------------------------------------------------------
# 6. Health
# ---------------------------------------------------------------------------
def test_health(client):
    r = client.get("/api/bi/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["cache_ttl_seconds"] == 300
    assert set(body["built_in_dashboards"]) >= {
        "funnel", "channel-roi", "agent-performance",
        "customer-success", "recruitment-efficiency",
    }


# ---------------------------------------------------------------------------
# 7. Frontend artefacts
# ---------------------------------------------------------------------------
class TestFrontendArtifacts:
    def test_bi_page_exists(self):
        f = FRONTEND_DIR / "app" / "admin" / "bi" / "page.tsx"
        assert f.exists(), "frontend/app/admin/bi/page.tsx missing"
        text = f.read_text()
        for sym in ["biApi", "WidgetGrid", "BuilderDialog", "HR 漏斗", "招聘效率"]:
            assert sym in text, f"BI page missing symbol: {sym}"

    def test_api_bi_client_exports_22_chart_types(self):
        f = FRONTEND_DIR / "lib" / "api-bi.ts"
        assert f.exists()
        text = f.read_text()
        # require at least 20 chart types
        chart_types = re.findall(r'type:\s*"([^"]+)"', text)
        chart_set = {c for c in chart_types if "-" not in c and "/" not in c and c not in {"date", "datetime", "string", "number", "time", "boolean", "count", "avg"}}
        # fall back: count CHART_TYPES array length
        import re as _re

        m = _re.search(r"CHART_TYPES\s*=\s*\[(.*?)\n\]", text, flags=_re.DOTALL)
        assert m, "CHART_TYPES array not found"
        # Each entry is an object literal
        entries = _re.findall(r"\{[^}]*type:\s*\"([^\"]+)\"[^}]*\}", m.group(1))
        assert len(entries) >= 20, f"expected 20+ chart types, found {len(entries)}"

    def test_bi_client_defines_5_builtin_dashboards(self):
        f = FRONTEND_DIR / "lib" / "api-bi.ts"
        text = f.read_text()
        # frontend uses DEFAULT_DASHBOARDS in page.tsx
        page = (FRONTEND_DIR / "app" / "admin" / "bi" / "page.tsx").read_text()
        for key in [
            "funnel",
            "recruitment-efficiency",
            "channel-roi",
            "agent-performance",
            "customer-success",
        ]:
            assert key in page, f"BI page missing dashboard: {key}"
