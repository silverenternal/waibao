"""Tests for the API versioning facade — T2904.

Validates:
* v1 routers are mounted under ``/api/v1/*``.
* v2 routers are mounted under ``/api/v2/*``.
* Legacy ``/api/...`` paths 308 -> ``/api/v1/...`` (preserves query string).
* Deprecated endpoints emit ``X-API-Deprecated`` + ``Sunset`` + ``Link``.
* ``/api/v2/version`` returns the version manifest.
* Whitelisted system paths (``/api/health``, ``/api/v1/...``) are NOT redirected.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def versioned_app() -> FastAPI:
    app = FastAPI(title="recruittech-test", version="0.0.0")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/version-info")
    async def version_info():
        return {"service": "recruittech"}

    # v1-only synthetic endpoint
    @app.get("/api/v1/sample")
    async def v1_sample():
        return {"v": 1}

    # v2-only synthetic endpoint (mounted via versioning)
    from api.versioning import install_versioning

    install_versioning(app)
    return app


@pytest.fixture
def client(versioned_app):
    # follow_redirects=False: tests inspect 308 Location headers directly
    with TestClient(versioned_app, follow_redirects=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Legacy redirect (308)
# ---------------------------------------------------------------------------


def test_legacy_path_redirects_to_v1(client):
    r = client.get("/api/version-info", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "/api/v1/version-info"


def test_legacy_path_preserves_query_string(client):
    r = client.get("/api/version-info?foo=bar&x=1", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"].startswith("/api/v1/version-info?")
    assert "foo=bar" in r.headers["location"]
    assert "x=1" in r.headers["location"]


def test_already_versioned_path_is_not_redirected(client):
    r = client.get("/api/v1/sample", follow_redirects=False)
    assert r.status_code == 200
    assert r.json() == {"v": 1}


def test_health_endpoint_not_redirected(client):
    r = client.get("/api/health", follow_redirects=False)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Deprecation headers on v1
# ---------------------------------------------------------------------------


def test_v1_response_has_deprecation_headers(client):
    r = client.get("/api/v1/sample")
    assert r.status_code == 200
    assert r.headers.get("x-api-version") == "v1"
    assert r.headers.get("x-api-deprecated") == "true"
    # Sunset header is RFC 8594 / RFC 9745
    assert r.headers.get("sunset") is not None
    assert r.headers.get("deprecation") == "true"
    # Link should mention the successor version (v2)
    assert "v2" in r.headers.get("link", "")
    assert r.headers.get("x-api-successor-version") == "v2"


def test_v1_endpoint_still_returns_data(client):
    """Backwards compatibility: v1 body shape unchanged."""
    r = client.get("/api/v1/sample")
    assert r.status_code == 200
    assert r.json() == {"v": 1}


# ---------------------------------------------------------------------------
# v2 manifest
# ---------------------------------------------------------------------------


def test_v2_version_endpoint_manifest(client):
    r = client.get("/api/v2/version")
    assert r.status_code == 200
    data = r.json()
    assert data["recommended"] == "v2"
    assert "v1" in data["deprecated"]
    assert any(v["version"] == "v1" for v in data["versions"])
    assert any(v["version"] == "v2" for v in data["versions"])


def test_v2_response_is_not_deprecated(client):
    r = client.get("/api/v2/version")
    assert r.headers.get("x-api-version") == "v2"
    # v2 is current, so it must NOT carry deprecation markers
    assert r.headers.get("x-api-deprecated") is None
    assert r.headers.get("sunset") is None


# ---------------------------------------------------------------------------
# Version registry direct helpers
# ---------------------------------------------------------------------------


def test_version_registry_defaults():
    from api.versioning import VERSION_REGISTRY, current_version, get_version_for_path

    assert "v1" in VERSION_REGISTRY
    assert "v2" in VERSION_REGISTRY
    assert current_version() == "v2"
    assert get_version_for_path("/api/v1/foo") == "v1"
    assert get_version_for_path("/api/v2/bar") == "v2"
    assert get_version_for_path("/api/foo") is None
    assert get_version_for_path("/health") is None


def test_version_spec_headers_deprecated():
    from api.versioning import VERSION_REGISTRY

    spec = VERSION_REGISTRY["v1"]
    h = spec.headers()
    assert h["X-API-Deprecated"] == "true"
    assert h["Deprecation"] == "true"
    assert "Sunset" in h
    assert "Link" in h and "v2" in h["Link"]


def test_version_spec_headers_current():
    from api.versioning import VERSION_REGISTRY

    spec = VERSION_REGISTRY["v2"]
    h = spec.headers()
    assert h["X-API-Version"] == "v2"
    assert "X-API-Deprecated" not in h


def test_install_versioning_is_idempotent():
    """Calling ``install_versioning`` twice does not stack middlewares."""
    from api.versioning import install_versioning

    app = FastAPI()
    install_versioning(app)
    middlewares_after_first = len(app.user_middleware)
    install_versioning(app)
    middlewares_after_second = len(app.user_middleware)
    assert middlewares_after_first == middlewares_after_second


def test_v2_router_loaded():
    """V2 namespace module imports cleanly + has /version route."""
    from api.v2 import router
    from fastapi import APIRouter

    assert isinstance(router, APIRouter)
    paths = []
    for r in router.routes:
        # routes can be APIRoute or Include
        path_attr = getattr(r, "path", None)
        if path_attr is not None:
            paths.append(path_attr)
    assert "/version" in paths


def test_v1_router_loaded():
    from api.v1 import router

    assert isinstance(router, list)
    assert len(router) > 5  # we expect many canonical routers


def test_legacy_never_redirect_prefixes():
    """Authenticated system endpoints must never 308 to /api/v1."""
    from api.versioning import NEVER_REDIRECT_PREFIXES

    assert "/api/health" in NEVER_REDIRECT_PREFIXES
    assert "/api/developer" in NEVER_REDIRECT_PREFIXES
    assert "/api/docs" in NEVER_REDIRECT_PREFIXES


def test_segment_aware_never_redirect():
    """The check must use segment boundaries, not naive substring startswith."""
    from api.versioning import _is_never_redirect

    # Match the explicit list
    assert _is_never_redirect("/api/health") is True
    assert _is_never_redirect("/api/health/sub") is True
    # A path that *contains* but does not start with a prefix must not match.
    # E.g. "/api/v10/foo" must not be caught by the "/api/v1" rule.
    assert _is_never_redirect("/api/v10/foo") is False
    # A path that *starts with* a prefix character but not segment must not match.
    # E.g. "/api/v1ment/foo" must not be caught by the "/api/v1" rule.
    assert _is_never_redirect("/api/v1ment/foo") is False


# ---------------------------------------------------------------------------
# Round-trip: register a deprecated endpoint and verify legacy + versioned paths
# ---------------------------------------------------------------------------


def test_full_versioning_round_trip():
    app = FastAPI()

    @app.get("/api/candidates/foo")
    async def candidates_foo():
        return {"id": "foo"}

    from api.versioning import install_versioning

    install_versioning(app)

    with TestClient(app) as c:
        # Direct call (no version prefix) — should 308 redirect
        direct = c.get("/api/candidates/foo?x=1", follow_redirects=False)
        assert direct.status_code == 308
        # Follow the redirect manually (TestClient follows by default; use no follow + status)
        assert direct.headers["location"] == "/api/v1/candidates/foo?x=1"
