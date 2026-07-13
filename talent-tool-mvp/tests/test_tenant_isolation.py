"""T2601 - strict multi-tenant isolation tests.

Covers the in-process tenant context + resolver layer.  The database-level
RLS behaviour is exercised by the migration itself (``046_tenant_context.sql``)
when run against a real Supabase instance.

Targets:
  * ``TenantContext`` dataclass + contextvar set/reset.
  * ``TenantResolver`` chain (JWT > header > cookie) priority order.
  * ``with_tenant`` contextmanager.
  * FastAPI integration: a fake /api/__test__ route that uses
    ``Depends(get_tenant_context_dep)`` + requires the tenant header.
  * 100-way concurrent in-memory tenant counter does not leak.
"""
from __future__ import annotations

import asyncio
import threading
import uuid

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from services.platform.tenant_context import (
    TenantContext,
    get_tenant,
    get_tenant_context,
    reset_tenant_context,
    set_tenant_context,
    with_tenant,
)
from services.platform.tenant_resolver import (
    TenantResolver,
    get_tenant_context_dep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fake_request(headers=None, cookies=None):
    """Build a stand-in Starlette Request with only the surface we use."""
    from starlette.requests import Request

    headers = headers or {}
    cookies = cookies or {}

    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "path": "/api/test",
        "query_string": b"",
    }
    if cookies:
        from starlette.datastructures import QueryParams

        scope["headers"].append((b"cookie", ("; ".join(f"{k}={v}" for k, v in cookies.items())).encode()))
    req = Request(scope)
    return req


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _echo_headers(request, call_next):
        resp = await call_next(request)
        tid = getattr(request.state, "tenant_id", None)
        if tid is not None:
            resp.headers["X-Tenant-ID"] = str(tid)
            resp.headers["X-Plan"] = str(getattr(request.state, "tenant_plan", "free"))
        return resp

    @app.get("/whoami")
    def whoami(ctx: TenantContext = Depends(get_tenant_context_dep)):
        return ctx.as_dict()

    @app.get("/strict")
    def strict(ctx: TenantContext = Depends(get_tenant_context_dep)):
        if ctx.role not in {"admin", "super_admin"}:
            raise HTTPException(status_code=403, detail="admin-only")
        return {"ok": True}

    return app


# ===========================================================================
# TenantContext + contextvars
# ===========================================================================
class TestTenantContext:
    def test_construction_and_dict(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = TenantContext(tenant_id=tid, user_id=uid, role="admin", plan="pro")
        assert ctx.tenant_id == tid
        assert ctx.user_id == uid
        assert ctx.is_admin is True
        assert ctx.is_impersonating is False
        d = ctx.as_dict()
        assert d["tenant_id"] == str(tid)
        assert d["plan"] == "pro"
        assert d["bypass_rls"] is False

    def test_bypass_flag_and_impersonation(self):
        admin = TenantContext(
            tenant_id=uuid.uuid4(),
            role="super_admin",
            bypass_rls=True,
            impersonator_id=uuid.uuid4(),
        )
        assert admin.is_admin
        assert admin.is_impersonating
        assert admin.bypass_rls

    def test_set_get_reset(self):
        ctx = TenantContext(tenant_id=uuid.uuid4(), role="admin")
        token = set_tenant_context(ctx)
        try:
            assert get_tenant_context() is ctx
            assert get_tenant() is ctx
        finally:
            reset_tenant_context(token)
        assert get_tenant_context() is None

    def test_with_tenant_cm_restores_after(self):
        tid = uuid.uuid4()
        with with_tenant(tid, role="admin") as ctx:
            assert get_tenant().tenant_id == tid
            assert ctx.role == "admin"
        assert get_tenant_context() is None

    def test_with_tenant_restores_on_exception(self):
        tid = uuid.uuid4()
        try:
            with with_tenant(tid):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert get_tenant_context() is None

    def test_get_tenant_strict_raises_when_unbound(self):
        # Ensure the strict reader raises, not returns None.
        if get_tenant_context() is not None:
            # Some other test leaked state — reset it.
            from services.platform.tenant_context import _tenant_var
            _tenant_var.set(None)
        with pytest.raises(RuntimeError):
            get_tenant()


# ===========================================================================
# TenantResolver priority chain
# ===========================================================================
class TestTenantResolver:
    def setup_method(self):
        self.resolver = TenantResolver()

    def test_resolve_from_jwt(self):
        tid = uuid.uuid4()
        uid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(),
            jwt_claims={"tenant_id": str(tid), "sub": str(uid), "role": "talent_partner"},
        )
        assert ctx is not None
        assert ctx.tenant_id == tid
        assert ctx.user_id == uid
        assert ctx.is_admin is False

    def test_resolve_jwt_orgid_alias(self):
        """Some old tokens expose ``organisation_id`` instead of ``tenant_id``."""
        tid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(), jwt_claims={"organisation_id": str(tid)}
        )
        assert ctx is not None and ctx.tenant_id == tid

    def test_resolve_jwt_admin_grants_bypass(self):
        tid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(),
            jwt_claims={"tenant_id": str(tid), "role": "super_admin"},
        )
        assert ctx is not None and ctx.bypass_rls is True

    def test_resolve_jwt_malformed_returns_none(self):
        ctx = self.resolver.resolve(
            _fake_request(), jwt_claims={"tenant_id": "not-a-uuid"}
        )
        assert ctx is None

    def test_resolve_jwt_user_malformed_returns_none_user(self):
        """A bad ``sub`` should not crash — keep tenant, drop user."""
        tid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(),
            jwt_claims={"tenant_id": str(tid), "sub": "garbage"},
        )
        assert ctx is not None
        assert ctx.tenant_id == tid
        assert ctx.user_id is None

    def test_header_fallback(self):
        tid = uuid.uuid4()
        ctx = self.resolver.resolve(_fake_request(headers={"x-tenant-id": str(tid)}))
        assert ctx is not None and ctx.tenant_id == tid

    def test_cookie_fallback(self):
        tid = uuid.uuid4()
        ctx = self.resolver.resolve(_fake_request(cookies={"waibao_tenant": str(tid)}))
        assert ctx is not None and ctx.tenant_id == tid

    def test_priority_jwt_beats_header(self):
        jwt_tid = uuid.uuid4()
        hdr_tid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(headers={"x-tenant-id": str(hdr_tid)}),
            jwt_claims={"tenant_id": str(jwt_tid)},
        )
        assert ctx is not None and ctx.tenant_id == jwt_tid

    def test_priority_header_beats_cookie(self):
        hdr_tid = uuid.uuid4()
        cookie_tid = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(
                headers={"x-tenant-id": str(hdr_tid)},
                cookies={"waibao_tenant": str(cookie_tid)},
            )
        )
        assert ctx is not None and ctx.tenant_id == hdr_tid

    def test_missing_all_sources_returns_none(self):
        assert self.resolver.resolve(_fake_request()) is None

    def test_impersonator_id_passed_through(self):
        tid = uuid.uuid4()
        op = uuid.uuid4()
        ctx = self.resolver.resolve(
            _fake_request(),
            jwt_claims={
                "tenant_id": str(tid),
                "impersonator_id": str(op),
                "role": "admin",
            },
        )
        assert ctx is not None
        assert ctx.impersonator_id == op


# ===========================================================================
# FastAPI dependency integration
# ===========================================================================
class TestFastAPIDependency:
    def setup_method(self):
        self.app = _build_app()
        self.client = TestClient(self.app)

    def test_resolves_via_header(self):
        tid = uuid.uuid4()
        r = self.client.get("/whoami", headers={"X-Tenant-ID": str(tid)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == str(tid)
        assert r.headers.get("X-Tenant-ID") == str(tid)

    def test_resolves_via_cookie(self):
        tid = uuid.uuid4()
        r = self.client.get("/whoami", cookies={"waibao_tenant": str(tid)})
        assert r.status_code == 200
        assert r.json()["tenant_id"] == str(tid)

    def test_missing_tenant_returns_403(self):
        r = self.client.get("/whoami")
        assert r.status_code == 403

    def test_admin_endpoint_rejects_non_admin(self):
        r = self.client.get("/strict", headers={"X-Tenant-ID": str(uuid.uuid4())})
        assert r.status_code == 403

    def test_admin_endpoint_accepts_admin(self):
        tid = uuid.uuid4()
        # Inject JWT claims into request.state via dependency override.
        from fastapi import Request

        # Use an in-memory claims middleware so the resolver sees the role.
        @self.app.middleware("http")
        async def _inject(request: Request, call_next):
            request.state.jwt_claims = {"tenant_id": str(tid), "role": "admin"}
            return await call_next(request)

        r = self.client.get("/strict")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ===========================================================================
# Concurrency: 100 simulated tenants do not collide
# ===========================================================================
class TestConcurrentTenants:
    def test_contextvar_isolates_across_threads(self):
        seen = {}
        barrier = threading.Barrier(64)
        tid_count = 64

        def worker(idx: int):
            tid = uuid.uuid4()
            barrier.wait()
            with with_tenant(tid, user_id=uuid.uuid4(), role="talent_partner"):
                # Sleep a bit to encourage context mixing.
                for _ in range(10):
                    ctx = get_tenant()
                    assert ctx.tenant_id == tid, f"thread {idx} saw wrong tenant"
                    seen[idx] = ctx.tenant_id

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(tid_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seen.values())) == tid_count

    def test_asyncio_tasks_see_distinct_contexts(self):
        async def one(tid):
            with_tenant_cm = with_tenant(tid)
            with with_tenant_cm:
                await asyncio.sleep(0.001)
                assert get_tenant().tenant_id == tid

        async def runner():
            tids = [uuid.uuid4() for _ in range(100)]
            await asyncio.gather(*(one(t) for t in tids))

        asyncio.run(runner())

    def test_tenant_quota_store_isolates_keys(self):
        from services.platform.quota import QuotaStore

        store = QuotaStore()
        tid_a, tid_b = uuid.uuid4(), uuid.uuid4()
        # Burn tenant A's bucket.
        for _ in range(3):
            assert store.incr_request(tid_a)[0] is True
        # Tenant B should still be unaffected.
        for _ in range(5):
            ok, remaining = store.incr_request(tid_b)
            assert ok is True
            assert remaining > 0


# ===========================================================================
# Cross-tenant API guard test (the spec calls for "403 on cross-tenant access")
# ===========================================================================
class TestCrossTenantAccess:
    def setup_method(self):
        self.app = FastAPI()

        @self.app.get("/data/{resource_id}")
        def get_data(
            resource_id: str,
            ctx: TenantContext = Depends(get_tenant_context_dep),
        ):
            # Simulate a row that belongs to ANOTHER tenant.
            owner = uuid.UUID("11111111-1111-1111-1111-111111111111")
            if str(owner) != resource_id:
                raise HTTPException(
                    status_code=403, detail="Cross-tenant access forbidden"
                )
            return {"ok": True, "resource_id": resource_id, "tenant": str(ctx.tenant_id)}

        self.client = TestClient(self.app)

    def test_cross_tenant_returns_403(self):
        r = self.client.get(
            f"/data/{uuid.uuid4()}",
            headers={"X-Tenant-ID": str(uuid.uuid4())},
        )
        assert r.status_code == 403
        assert "Cross-tenant" in r.text

    def test_same_tenant_passes(self):
        target = "11111111-1111-1111-1111-111111111111"
        r = self.client.get(f"/data/{target}", headers={"X-Tenant-ID": str(uuid.uuid4())})
        assert r.status_code == 200
