"""v10.0 T5003 — API tenant-isolation & contract tests.

Covers:
* the ``get_tenant_context`` dependency enforcing tenant presence,
* the explicit ``tenant_context(ctx)`` context-manager replacing implicit
  middleware binding,
* ``typed_router`` wiring the tenant/quota dependency chain,
* the canonical response envelopes (``ApiResponse``, ``PaginatedResponse``,
  ``ErrorEnvelope``),
* the ``openapi_diff`` drift gate detecting breaking changes.
"""
from __future__ import annotations

import os
import uuid

os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware import get_tenant_context, install_error_handlers
from contracts.api import (
    ApiResponse,
    ErrorEnvelope,
    PaginatedResponse,
    typed_router,
)
from services.platform.errors import ServiceError, ServiceErrorCode
from services.platform.tenant_context import (
    TenantContext,
    get_tenant_context as get_ctx,
    get_tenant,
    tenant_context,
    with_tenant,
)


def _tenant_dep():
    """The standard tenant dependency for use as a default arg."""
    return Depends(get_tenant_context)


# ===========================================================================
# tenant_context(ctx) explicit context manager
# ===========================================================================
class TestTenantContextManager:
    def test_binds_and_unbinds(self):
        assert get_ctx() is None
        tid = uuid.uuid4()
        with tenant_context(TenantContext(tenant_id=tid, role="admin")) as ctx:
            assert get_ctx() is ctx
            assert ctx.tenant_id == tid
            assert ctx.is_admin
        assert get_ctx() is None

    def test_get_tenant_strict_raises_outside_block(self):
        with pytest.raises(RuntimeError):
            get_tenant()

    def test_get_tenant_returns_inside_block(self):
        with with_tenant(uuid.uuid4(), role="talent_partner") as ctx:
            assert get_tenant() is ctx

    def test_with_tenant_accepts_string_ids(self):
        with with_tenant("11111111-1111-1111-1111-111111111111",
                         "22222222-2222-2222-2222-222222222222") as ctx:
            assert str(ctx.tenant_id) == "11111111-1111-1111-1111-111111111111"

    def test_isolation_between_concurrent_contexts(self):
        a = uuid.uuid4()
        b = uuid.uuid4()
        with tenant_context(TenantContext(tenant_id=a)):
            assert get_ctx().tenant_id == a
            with tenant_context(TenantContext(tenant_id=b)):
                assert get_ctx().tenant_id == b
            # restored after inner exit
            assert get_ctx().tenant_id == a


# ===========================================================================
# get_tenant_context dependency
# ===========================================================================
class TestGetTenantContextDependency:
    def test_missing_tenant_raises_service_error(self):
        app = FastAPI()
        install_error_handlers(app)

        @app.get("/x")
        async def x(ctx=_tenant_dep()):
            return {"t": str(ctx.tenant_id)}

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/x")
        assert r.status_code == 400  # AUTH_MISSING_TENANT
        body = r.json()["error"]
        assert body["code"] == "AUTH_MISSING_TENANT"
        assert "request_id" in body

    def test_present_tenant_passes_through(self):
        app = FastAPI()
        install_error_handlers(app)

        @app.get("/x")
        async def x(ctx=_tenant_dep()):
            return {"t": str(ctx.tenant_id)}

        tid = uuid.uuid4()
        client = TestClient(app, raise_server_exceptions=False)
        # emulate middleware binding through the dep's ContextVar fallback.
        from services.platform.tenant_context import (
            set_tenant_context, reset_tenant_context,
        )
        token = set_tenant_context(TenantContext(tenant_id=tid))
        try:
            r = client.get("/x")
        finally:
            reset_tenant_context(token)
        assert r.status_code == 200
        assert r.json()["t"] == str(tid)


# ===========================================================================
# typed_router
# ===========================================================================
class TestTypedRouter:
    def test_router_includes_tenant_dependency(self):
        router = typed_router(prefix="/api/widgets", tags=["widgets"])
        assert router.prefix == "/api/widgets"
        assert len(router.dependencies) >= 1

    def test_router_without_tenant(self):
        router = typed_router(prefix="/public", require_tenant=False, with_quota=False)
        assert router.dependencies == []

    def test_router_routes_work(self):
        router = typed_router(prefix="/api/items", require_tenant=False, with_quota=False)

        @router.get("/")
        async def list_items():
            return [{"id": 1}]

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.get("/api/items/")
        assert r.status_code == 200
        assert r.json() == [{"id": 1}]

    def test_router_enforces_tenant_when_required(self):
        router = typed_router(prefix="/api/secured")

        @router.get("/")
        async def list_secured(ctx=_tenant_dep()):
            return {"t": str(ctx.tenant_id)}

        app = FastAPI()
        install_error_handlers(app)
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/secured/")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "AUTH_MISSING_TENANT"


# ===========================================================================
# Response envelopes
# ===========================================================================
class TestResponseEnvelopes:
    def test_api_response_wraps_data(self):
        r = ApiResponse[dict](data={"id": 1}, request_id="r1")
        assert r.data == {"id": 1}
        assert r.request_id == "r1"
        assert r.model_dump()["data"] == {"id": 1}

    def test_paginated_response(self):
        r = PaginatedResponse[dict](data=[{"id": 1}], total=100, limit=10, offset=0,
                                    next_cursor="abc")
        assert r.total == 100
        assert r.next_cursor == "abc"

    def test_error_envelope_round_trip(self):
        e = ErrorEnvelope(code="NOT_FOUND", message="x", retryable=False,
                          request_id="r1")
        d = e.model_dump()
        assert d["code"] == "NOT_FOUND"
        assert d["retryable"] is False
        assert d["request_id"] == "r1"

    def test_api_response_as_response_model(self):
        app = FastAPI()

        @app.get("/p", response_model=ApiResponse[dict])
        async def p():
            return ApiResponse[dict](data={"v": 1})

        client = TestClient(app)
        r = client.get("/p")
        assert r.status_code == 200
        assert r.json()["data"] == {"v": 1}

    def test_paginated_as_response_model(self):
        app = FastAPI()

        @app.get("/list", response_model=PaginatedResponse[dict])
        async def lst():
            return PaginatedResponse[dict](data=[{"id": 1}, {"id": 2}], total=2)

        client = TestClient(app)
        body = client.get("/list").json()
        assert body["total"] == 2
        assert len(body["data"]) == 2


# ===========================================================================
# openapi-diff drift gate
# ===========================================================================
class TestOpenApiDiff:
    def _run(self, *args):
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import importlib
        mod = importlib.import_module("scripts.openapi_diff")
        importlib.reload(mod)
        return mod

    def test_diff_detects_removed_path(self, tmp_path, monkeypatch):
        mod = self._run()
        old = {"paths": {"/a": {"get": {"responses": {"200": {}}}},
                          "/b": {"get": {"responses": {"200": {}}}}}}
        new = {"paths": {"/a": {"get": {"responses": {"200": {}}}}}}  # /b removed
        breaking = mod._diff_breaking(old, new)
        assert any("path removed" in b for b in breaking)

    def test_diff_detects_removed_response_code(self, tmp_path):
        mod = self._run()
        old = {"paths": {"/a": {"get": {"responses": {"200": {}, "404": {}}}}}}
        new = {"paths": {"/a": {"get": {"responses": {"200": {}}}}}}
        breaking = mod._diff_breaking(old, new)
        assert any("response 404 removed" in b for b in breaking)

    def test_diff_detects_required_param_tightening(self, tmp_path):
        mod = self._run()
        old = {"paths": {"/a": {"get": {
            "parameters": [{"name": "q", "required": False}],
            "responses": {"200": {}},
        }}}}
        new = {"paths": {"/a": {"get": {
            "parameters": [{"name": "q", "required": True}],
            "responses": {"200": {}},
        }}}}
        breaking = mod._diff_breaking(old, new)
        assert any("became required" in b for b in breaking)

    def test_diff_clean_on_additive_change(self, tmp_path):
        mod = self._run()
        old = {"paths": {"/a": {"get": {"responses": {"200": {}}}}}}
        new = {"paths": {"/a": {"get": {"responses": {"200": {}, "201": {}}}},
                          "/new": {"get": {"responses": {"200": {}}}}}}
        assert mod._diff_breaking(old, new) == []

    def test_diff_detects_required_body_tightening(self, tmp_path):
        mod = self._run()
        old = {"paths": {"/a": {"post": {
            "requestBody": {"required": False},
            "responses": {"200": {}},
        }}}}
        new = {"paths": {"/a": {"post": {
            "requestBody": {"required": True},
            "responses": {"200": {}},
        }}}}
        breaking = mod._diff_breaking(old, new)
        assert any("requestBody became required" in b for b in breaking)
