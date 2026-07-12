"""Assessment 集成测试 (T1306)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- helpers (same shape as video interview tests) ---
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
            if self._single:
                rows = data[0] if data else None
                return SimpleNamespace(data=rows)
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
        self.tables = {
            "assessment_invitations": {},
            "candidates": {
                "c1": {
                    "id": "c1",
                    "name": "Cand",
                    "assessment_score": None,
                    "assessment_confidence": None,
                },
            },
        }
    def table(self, name):
        return _TableRow(name, self.tables.setdefault(name, {}))


def _make_resp(status, body):
    return SimpleNamespace(
        status_code=status,
        text=json.dumps(body) if isinstance(body, (dict, list)) else str(body or ""),
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
    from providers.assessment.mock import MockAssessmentProvider

    p = MockAssessmentProvider()
    inv = await p.send_invitation(
        candidate_id="c1",
        assessment_id="assess_001",
        candidate_email="c@x.com",
        candidate_name="C",
        expires_in_hours=24,
    )
    assert inv.invitation_id.startswith("inv_mock_")
    assert inv.status == "pending"

    res = await p.get_results(inv.invitation_id)
    assert res.status == "pending"

    p.seed_result(inv.invitation_id, overall_score=88.5, percentile=92)
    res2 = await p.get_results(inv.invitation_id)
    assert res2.status == "scored"
    assert res2.overall_score == 88.5
    assert res2.percentile == 92
    assert res2.passed is True


@pytest.mark.asyncio
async def test_mock_provider_validation():
    from providers.assessment.mock import MockAssessmentProvider
    p = MockAssessmentProvider()
    with pytest.raises(Exception):
        await p.send_invitation(
            candidate_id="", assessment_id="", candidate_email=None,
        )


# ---------------------------------------------------------------------------
# Beisen provider
# ---------------------------------------------------------------------------
class _BeisenClient:
    def __init__(self, *a, **kw):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def post(self, url, **kw):
        if url.endswith("/oauth2/token"):
            return _make_resp(
                200, {"accessToken": "tok", "expiresIn": 7200, "errorCode": 0},
            )
        # invitation/create (POST path)
        return _make_resp(
            200,
            {
                "errorCode": 0,
                "invitationId": "INV-BEISEN-001",
                "inviteId": "INV-BEISEN-001",
                "url": "https://exam.beisen.com/take/INV-BEISEN-001",
                "inviteUrl": "https://exam.beisen.com/take/INV-BEISEN-001",
            },
        )

    async def request(self, method, url, **kw):
        # invitation/result (GET)
        if "result" in url:
            return _make_resp(
                200,
                {
                    "errorCode": 0,
                    "candidateId": "c1",
                    "assessmentId": "a1",
                    "status": "1",
                    "overallScore": 87.5,
                    "totalScore": 87.5,
                    "percentile": 80,
                    "passed": True,
                    "completedAt": "2026-07-12T10:00:00Z",
                    "reportUrl": "https://exam.beisen.com/report/INV-001",
                    "scoreList": [
                        {"name": "logical", "value": 90, "max": 100, "band": "high"},
                        {"name": "coding", "value": 85, "max": 100, "band": "high"},
                    ],
                },
            )
        # invitation/create (POST)
        if "invitation/create" in url:
            return _make_resp(
                200,
                {
                    "errorCode": 0,
                    "invitationId": "INV-BEISEN-001",
                    "inviteId": "INV-BEISEN-001",
                    "url": "https://exam.beisen.com/take/INV-BEISEN-001",
                    "inviteUrl": "https://exam.beisen.com/take/INV-BEISEN-001",
                },
            )
        # default
        return _make_resp(200, {"errorCode": 0, "status": "1"})


@pytest.mark.asyncio
async def test_beisen_send_invite(monkeypatch):
    from providers.assessment import beisen as be_mod
    monkeypatch.setenv("BEISEN_APP_ID", "app")
    monkeypatch.setenv("BEISEN_APP_SECRET", "sec")
    monkeypatch.setattr(be_mod.httpx, "AsyncClient", _BeisenClient)

    p = be_mod.BeisenProvider()
    inv = await p.send_invitation(
        candidate_id="c1", assessment_id="a1",
        candidate_email="c@x.com", candidate_name="C",
        expires_in_hours=48,
    )
    assert inv.invitation_id == "INV-BEISEN-001"
    assert inv.invite_url.startswith("https://exam.beisen.com/")
    assert inv.provider == "beisen"


@pytest.mark.asyncio
async def test_beisen_get_results(monkeypatch):
    from providers.assessment import beisen as be_mod
    monkeypatch.setenv("BEISEN_APP_ID", "app")
    monkeypatch.setenv("BEISEN_APP_SECRET", "sec")
    monkeypatch.setattr(be_mod.httpx, "AsyncClient", _BeisenClient)

    p = be_mod.BeisenProvider()
    res = await p.get_results("INV-BEISEN-001")
    assert res.status == "scored"
    assert res.overall_score == 87.5
    assert res.percentile == 80
    assert res.passed is True
    assert len(res.scores) == 2
    assert any(s.name == "logical" for s in res.scores)


@pytest.mark.asyncio
async def test_beisen_pending_status(monkeypatch):
    """北森 pending 状态 → AssessmentResult.pending."""
    from providers.assessment import beisen as be_mod

    class _Pending(_BeisenClient):
        async def request(self, method, url, **kw):
            return _make_resp(
                200,
                {
                    "errorCode": 0,
                    "candidateId": "",
                    "assessmentId": "",
                    "status": "0",  # pending
                },
            )

    monkeypatch.setenv("BEISEN_APP_ID", "a")
    monkeypatch.setenv("BEISEN_APP_SECRET", "b")
    monkeypatch.setattr(be_mod.httpx, "AsyncClient", _Pending)
    p = be_mod.BeisenProvider()
    res = await p.get_results("x")
    assert res.status == "submitted"


@pytest.mark.asyncio
async def test_beisen_unconfigured(monkeypatch):
    from providers.assessment import beisen as be_mod
    monkeypatch.delenv("BEISEN_APP_ID", raising=False)
    monkeypatch.delenv("BEISEN_APP_SECRET", raising=False)
    p = be_mod.BeisenProvider()
    assert p._configured() is False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_service_send_invite(sb):
    from services.assessment_service import AssessmentService
    svc = AssessmentService(supabase=sb)
    row = await svc.send_invite(
        candidate_id="c1", assessment_id="a1",
        candidate_email="c@x.com", candidate_name="C",
        expires_in_hours=24,
    )
    assert row["provider"] == "mock_assessment"
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_service_get_result_persists_score(sb):
    from services.assessment_service import AssessmentService
    from providers.assessment.mock import MockAssessmentProvider

    svc = AssessmentService(supabase=sb)
    row = await svc.send_invite(
        candidate_id="c1",
        assessment_id="a1",
        candidate_email="c@x.com",
        candidate_name="C",
        expires_in_hours=24,
    )
    # seed mock result
    mock = svc._mock_provider()
    mock.seed_result(row["invitation_id"], overall_score=90, percentile=80)

    result = await svc.get_result(row["invitation_id"])
    assert result["status"] == "scored"
    assert result["overall_score"] == 90
    assert result["confidence"] == "very_high"

    # 检查 candidates.assessment_score 已更新
    cand = sb.table("candidates").select("*").eq("id", "c1").execute()
    assert cand.data[0]["assessment_score"] == 90


@pytest.mark.asyncio
async def test_service_get_result_unknown_invite(sb):
    """DB 没有 invitation → 直接 mock.get_results 兜底."""
    from services.assessment_service import AssessmentService
    svc = AssessmentService(supabase=sb)
    out = await svc.get_result("inv_does_not_exist")
    assert out["invitation_id"] == "inv_does_not_exist"
    assert out["status"] == "pending"


# ---------------------------------------------------------------------------
# Matching engine score integration
# ---------------------------------------------------------------------------
def test_matching_scorer_with_assessment():
    from matching.scorer import CompositeScorer
    from contracts.shared import ExtractedSkill, RequiredSkill

    scorer = CompositeScorer()
    score_with = scorer.score(
        candidate_skills=[
            ExtractedSkill(name="python", years=3.0),
        ],
        candidate_seniority=None,
        candidate_experience_months=36,
        role_required_skills=[
            RequiredSkill(name="python", min_years=2),
        ],
        role_preferred_skills=[],
        role_seniority=None,
        semantic_similarity=0.8,
        assessment_score=85,
    )
    score_without = scorer.score(
        candidate_skills=[
            ExtractedSkill(name="python", years=3.0),
        ],
        candidate_seniority=None,
        candidate_experience_months=36,
        role_required_skills=[
            RequiredSkill(name="python", min_years=2),
        ],
        role_preferred_skills=[],
        role_seniority=None,
        semantic_similarity=0.8,
    )
    # 总分归一都在 0-1
    assert 0 <= score_with["overall_score"] <= 1
    assert 0 <= score_without["overall_score"] <= 1
    # 启用了 assessment,应该有非零权重
    bd = score_with["scoring_breakdown"]["weights"]
    assert bd["assessment"] == pytest.approx(0.15, abs=0.001)
    # 不启用 assessment,总权重为 0
    assert score_without["scoring_breakdown"]["weights"]["assessment"] == 0.0


def test_matching_scorer_assessment_normalization():
    from matching.scorer import CompositeScorer
    from contracts.shared import ExtractedSkill, RequiredSkill

    scorer = CompositeScorer()
    s = scorer.score(
        candidate_skills=[
            ExtractedSkill(name="python", years=5.0),
        ],
        candidate_seniority=None,
        candidate_experience_months=60,
        role_required_skills=[
            RequiredSkill(name="python", min_years=3),
        ],
        role_preferred_skills=[],
        role_seniority=None,
        semantic_similarity=0.9,
        assessment_score=150,  # 越界
    )
    # 150 应被 clip 到 1.0
    assert s["assessment_score"] == 1.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_registry_default_mock(monkeypatch):
    from providers.assessment.registry import (
        get_assessment_provider, reset_cache,
    )
    monkeypatch.delenv("ASSESSMENT_PROVIDER", raising=False)
    reset_cache()
    p = get_assessment_provider()
    assert p.provider_name == "mock_assessment"


def test_registry_beisen_missing_creds(monkeypatch):
    from providers.assessment.registry import (
        get_assessment_provider, reset_cache,
    )
    monkeypatch.setenv("ASSESSMENT_PROVIDER", "beisen")
    monkeypatch.delenv("BEISEN_APP_ID", raising=False)
    monkeypatch.delenv("BEISEN_APP_SECRET", raising=False)
    reset_cache()
    p = get_assessment_provider()
    assert p.provider_name == "mock_assessment"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
def test_api_router_endpoints_present():
    from api.assessments import router
    methods = sorted(
        f"{list(getattr(r, 'methods', set()))[0]} {r.path}"
        for r in router.routes
        if hasattr(r, "methods") and getattr(r, "methods", None)
    )
    assert any("POST /api/assessments/invite" in m for m in methods)
    assert any(
        "GET /api/assessments/{invitation_id}/result" in m
        for m in methods
    )
    assert any("GET /api/assessments" in m for m in methods)
