"""BackgroundCheck 集成测试 (T1307)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- helpers ---
class _TableRow:
    def __init__(self, name, store=None):
        self.name = name
        self.store = store if store is not None else {}
        self.filters = []
        self._op = "select"
        self._value = None
        self._single = False
        self._order = None
        self._limit_n = None

    def insert(self, v):
        self._op = "insert"; self._value = v; return self
    def update(self, v):
        self._op = "update"; self._value = v; return self
    def select(self, *_):
        self._op = "select"; return self
    def eq(self, c, v):
        self.filters.append((c, v)); return self
    def order(self, c, desc=False):
        self._order = (c, desc); return self
    def limit(self, n):
        self._limit_n = n; return self
    def single(self):
        self._single = True; return self

    def execute(self):
        rows = []
        if self._op == "insert":
            v = self._value
            if isinstance(v, dict):
                import uuid as _u
                if not v.get("id"):
                    v = {**v, "id": str(_u.uuid4())}
                self.store[v["id"]] = v
            rows = [v]
        elif self._op == "select":
            data = list(self.store.values())
            for c, val in self.filters:
                data = [r for r in data if r.get(c) == val]
            if self._order:
                c, d = self._order
                data.sort(key=lambda r: r.get(c) or "", reverse=d)
            if self._limit_n is not None:
                data = data[:self._limit_n]
            rows = data
        elif self._op == "update":
            rows = []
            for c, val in self.filters:
                for k, r in list(self.store.items()):
                    if r.get(c) == val:
                        self.store[k] = {**r, **(self._value or {})}
                        rows.append(self.store[k])
        return SimpleNamespace(data=rows)


class _FakeSupabase:
    def __init__(self):
        self.tables = {"background_checks": {}}

    def table(self, name):
        return _TableRow(name, self.tables.setdefault(name, {}))


def _make_resp(status, body):
    return SimpleNamespace(
        status_code=status,
        text=json.dumps(body) if isinstance(body, (dict, list)) else (body or ""),
        json=lambda: body,
    )


@pytest.fixture()
def sb():
    return _FakeSupabase()


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_provider_full_flow():
    from providers.background_check.mock import MockBackgroundCheckProvider
    from providers.background_check.types import CheckType

    p = MockBackgroundCheckProvider()
    chk = await p.initiate_check(
        candidate_id="c1",
        check_types=[CheckType(code="criminal")],
    )
    assert chk.check_id.startswith("chk_mock_")
    assert chk.status == "pending"

    st = await p.get_status(chk.check_id)
    assert st.status == "pending"

    p.seed_status(chk.check_id, status="clear", progress_pct=100.0)
    st2 = await p.get_status(chk.check_id)
    assert st2.status == "clear"
    assert st2.progress_pct == 100.0
    assert st2.report_url is not None


# ---------------------------------------------------------------------------
# Checkr provider
# ---------------------------------------------------------------------------
class _CheckrClient:
    def __init__(self, *a, **kw):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def request(self, method, url, **kw):
        if url.endswith("/candidates") and method == "POST":
            return _make_resp(200, {"id": "cand_xyz123"})
        if url.endswith("/reports") and method == "POST":
            return _make_resp(
                201,
                {
                    "id": "rep_abc456",
                    "status": "pending",
                    "report_url": "https://dashboard.checkr.com/reports/rep_abc456",
                    "created_at": "2026-07-12T10:00:00Z",
                },
            )
        if "/reports/" in url:
            return _make_resp(
                200,
                {
                    "id": "rep_abc456",
                    "candidate_id": "cand_xyz123",
                    "status": "clear",
                    "report_url": "https://dashboard.checkr.com/reports/rep_abc456",
                    "updated_at": "2026-07-12T11:00:00Z",
                    "records": [
                        {
                            "type": "criminal_record",
                            "category": "criminal",
                            "adjudication": "engaged",
                            "comment": "no records found",
                        },
                    ],
                },
            )
        return _make_resp(200, {"id": "x"})


@pytest.mark.asyncio
async def test_checkr_initiate_and_status(monkeypatch):
    from providers.background_check import checkr as ck_mod
    from providers.background_check.types import CheckType

    monkeypatch.setenv("CHECKR_API_KEY", "acct_test_key")
    monkeypatch.setattr(ck_mod.httpx, "AsyncClient", _CheckrClient)

    p = ck_mod.CheckrProvider()
    assert p._configured() is True

    chk = await p.initiate_check(
        candidate_id="cand_001",
        check_types=[CheckType(code="criminal")],
        candidate_email="c@x.com",
        candidate_name="Alice Bob",
    )
    assert chk.check_id == "rep_abc456"
    assert chk.provider == "checkr"
    assert chk.report_url and chk.report_url.startswith("https://dashboard")

    st = await p.get_status("rep_abc456")
    assert st.status == "clear"
    assert st.progress_pct == 100.0
    assert any(f.code == "criminal_record" for f in st.findings)


@pytest.mark.asyncio
async def test_checkr_status_404(monkeypatch):
    from providers.background_check import checkr as ck_mod

    class _NotFound(_CheckrClient):
        async def request(self, method, url, **kw):
            return _make_resp(404, None)

    monkeypatch.setenv("CHECKR_API_KEY", "acct_test_key")
    monkeypatch.setattr(ck_mod.httpx, "AsyncClient", _NotFound)
    p = ck_mod.CheckrProvider()
    st = await p.get_status("missing")
    assert st.status == "pending"


def test_checkr_unconfigured(monkeypatch):
    from providers.background_check import checkr as ck_mod
    monkeypatch.delenv("CHECKR_API_KEY", raising=False)
    p = ck_mod.CheckrProvider()
    assert p._configured() is False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_service_initiate_mock(sb):
    from services.background_check_service import BackgroundCheckService
    svc = BackgroundCheckService(supabase=sb)
    row = await svc.initiate(
        candidate_id="c1",
        candidate_email="c@x.com",
        candidate_name="C",
        offer_id=None,
        job_id="j1",
    )
    assert row["provider"] == "mock_bg_check"
    assert row["status"] == "pending"
    assert "criminal" in row["check_types"]


@pytest.mark.asyncio
async def test_service_get_status_with_seed(sb):
    from services.background_check_service import BackgroundCheckService
    svc = BackgroundCheckService(supabase=sb)
    row = await svc.initiate(
        candidate_id="c1", candidate_email="c@x.com",
        candidate_name="C", offer_id=None, job_id=None,
    )
    svc._mock_provider().seed_status(
        row["check_id"], status="clear", progress_pct=100,
    )
    out = await svc.get_status(row["check_id"])
    assert out["status"] == "clear"
    assert out["report_url"].startswith("https://mock-bgcheck.local")


@pytest.mark.asyncio
async def test_service_trigger_pre_offer_dedups(sb):
    """trigger_pre_offer 已有 running 时跳过."""
    from services.background_check_service import BackgroundCheckService
    svc = BackgroundCheckService(supabase=sb)

    out1 = await svc.trigger_pre_offer(
        candidate_id="c1", candidate_email=None,
        candidate_name="C", offer_id=None, job_id=None,
    )
    assert out1["skipped"] is False

    out2 = await svc.trigger_pre_offer(
        candidate_id="c1", candidate_email=None,
        candidate_name="C", offer_id=None, job_id=None,
    )
    assert out2["skipped"] is True
    assert out2["reason"] == "existing_check"


@pytest.mark.asyncio
async def test_service_real_provider_falls_back(sb, monkeypatch):
    """Checkr 凭证缺失 → service fallback mock,不抛错."""
    from services.background_check_service import BackgroundCheckService

    monkeypatch.setenv("BG_CHECK_PROVIDER", "checkr")
    monkeypatch.delenv("CHECKR_API_KEY", raising=False)

    from providers.background_check.registry import reset_cache
    reset_cache()

    svc = BackgroundCheckService(supabase=sb)
    row = await svc.initiate(
        candidate_id="c1", candidate_email=None, candidate_name=None,
        offer_id=None, job_id=None,
    )
    assert row["provider"] == "mock_bg_check"


# ---------------------------------------------------------------------------
# HR Service Agent hook
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hr_agent_triggers_pre_offer_on_recruiting_stage(monkeypatch):
    """HR agent 在 recruiting 阶段 + offer 关键词时触发 background check."""
    captured = {}

    class FakeBCService:
        def __init__(self, *a, **kw):
            pass

        async def trigger_pre_offer(self, **kw):
            captured.update(kw)
            return {"skipped": False, "data": {"check_id": "chk-1"}}

    # Patch 必须在 HR agent 模块首次导入 BackgroundCheckService 之前/之后都行
    # 因为 _maybe_trigger 函数中是延迟 import, 所以 patch 父模块即可.
    monkeypatch.setattr(
        "services.background_check_service.BackgroundCheckService",
        FakeBCService,
    )
    from agents.employer.hr_service_agent import (
        _maybe_trigger_pre_offer_background_check,
    )

    ctx = {
        "supabase": object(),
        "candidate_id": "cand-A",
        "candidate_email": "a@x.com",
        "candidate_name": "Alice",
        "offer_id": "offer-1",
    }
    result = {"stage": "recruiting"}
    await _maybe_trigger_pre_offer_background_check(
        text="候选人背景很合适,准备发offer,请安排背调",
        stage="recruiting",
        ctx=ctx,
        hr_user_id="hr-1",
        result=result,
    )
    assert "background_check" in result
    assert captured["candidate_id"] == "cand-A"


@pytest.mark.asyncio
async def test_hr_agent_skips_on_non_recruiting_stage():
    """非 recruiting 阶段或无 offer 关键词时,不触发."""
    from agents.employer.hr_service_agent import (
        _maybe_trigger_pre_offer_background_check,
    )

    ctx = {"supabase": object(), "candidate_id": "cand-A"}
    result: dict = {"stage": "general"}

    # 1) not recruiting → skip
    await _maybe_trigger_pre_offer_background_check(
        text="请问什么时候发 offer",
        stage="general",
        ctx=ctx,
        hr_user_id="hr-1",
        result=result,
    )
    assert "background_check" not in result

    # 2) recruiting but no offer keyword → skip
    await _maybe_trigger_pre_offer_background_check(
        text="面试安排什么时候?",
        stage="recruiting",
        ctx=ctx,
        hr_user_id="hr-1",
        result=result,
    )
    assert "background_check" not in result


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_registry_default_mock(monkeypatch):
    from providers.background_check.registry import (
        get_background_check_provider, reset_cache,
    )
    monkeypatch.delenv("BG_CHECK_PROVIDER", raising=False)
    reset_cache()
    p = get_background_check_provider()
    assert p.provider_name == "mock_bg_check"


def test_registry_checkr_missing_creds(monkeypatch):
    from providers.background_check.registry import (
        get_background_check_provider, reset_cache,
    )
    monkeypatch.setenv("BG_CHECK_PROVIDER", "checkr")
    monkeypatch.delenv("CHECKR_API_KEY", raising=False)
    reset_cache()
    p = get_background_check_provider()
    assert p.provider_name == "mock_bg_check"


def test_api_router_endpoints_present():
    from api.background_check import router
    methods = sorted(
        f"{list(getattr(r, 'methods', set()))[0]} {r.path}"
        for r in router.routes
        if hasattr(r, "methods") and getattr(r, "methods", None)
    )
    assert any("POST /api/background-checks" in m for m in methods)
    assert any(
        "GET /api/background-checks/{check_id}/status" in m
        for m in methods
    )
    assert any(
        "POST /api/background-checks/trigger-pre-offer" in m
        for m in methods
    )
