"""T6104 — Recommendation records tests (push talent to employer).

Coverage:
* service: create_recommendation (snapshot + score clamp + reasons/gaps/risks)
* service: lifecycle pending → viewed → accepted/rejected
* service: list_for_org scoping + status filter + seed-on-empty
* service: render_resume_text (download payload)
* API: list (org-scoped, no PII in list)
* API: detail (full resume + contact + auto viewed)
* API: status PATCH (accept / reject)
* API: download — ADMIN ONLY (client gets 403)
* API: cross-org 404 (employer cannot see another org's recommendation)
* notify dispatcher integration (push called on create)

Entirely offline — the service runs against its in-memory fallback store
(Supabase probe fails in CI → memory mode). Auth is stubbed via
``app.dependency_overrides[get_current_user]``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from contracts.shared import UserRole  # noqa: E402
import services.notify  # noqa: E402,F401  ensure package attr exists for patching
from services.matching.recommendation import (  # noqa: E402
    RecommendationService,
    build_contact_info,
    build_resume_snapshot,
    reset_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _User:
    def __init__(self, role: UserRole, org_id: str | None = None):
        self.id = "u-" + role.value
        self.email = f"{role.value}@test.com"
        self.role = role
        self.org_id = org_id


@pytest.fixture()
def svc() -> RecommendationService:
    # Force memory mode (no Supabase) for deterministic offline tests.
    s = reset_service(supabase=None)
    return s


def _candidate(**overrides):
    base = {
        "id": "c1",
        "full_name": "测试候选人",
        "title": "后端工程师",
        "city": "北京",
        "skills": ["Python", "Go", "Redis"],
        "seniority": "高级",
        "education": "硕士",
        "experience_years": 6,
        "email": "talent@example.com",
        "phone": "13800000000",
        "linkedin_url": "https://linkedin.com/in/x",
        "summary": "6年后端经验",
    }
    base.update(overrides)
    return base


def _role(**overrides):
    base = {"id": "r1", "title": "资深后端", "company": "ACME", "org_id": "org_acme"}
    base.update(overrides)
    return base


def _match(**overrides):
    base = {
        "match_score": 88,
        "match_reasons": ["技能匹配 5/5", "同城"],
        "skill_gaps": ["缺 K8s 经验"],
        "risks": ["薪资偏高"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------------

def test_resume_snapshot_captures_core_fields():
    snap = build_resume_snapshot(_candidate())
    assert snap["full_name"] == "测试候选人"
    assert snap["skills"] == ["Python", "Go", "Redis"]
    assert snap["education"] == "硕士"
    assert "captured_at" in snap


def test_contact_info_captures_pii():
    contact = build_contact_info(_candidate())
    assert contact["email"] == "talent@example.com"
    assert contact["phone"] == "13800000000"
    assert contact["linkedin_url"].endswith("/in/x")


# ---------------------------------------------------------------------------
# create_recommendation
# ---------------------------------------------------------------------------

def test_create_clamps_score_and_extracts_lists(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(),
            role=_role(),
            match_result=_match(match_score=150),  # out of range
            notify=False,
        )
    )
    assert rec.match_score == 100  # clamped
    assert rec.match_reasons == ["技能匹配 5/5", "同城"]
    assert rec.skill_gaps == ["缺 K8s 经验"]
    assert rec.risks == ["薪资偏高"]
    assert rec.status == "pending"
    assert rec.org_id == "org_acme"
    assert rec.resume_snapshot["skills"] == ["Python", "Go", "Redis"]
    assert rec.contact_info["email"] == "talent@example.com"
    assert rec.candidate_name == "测试候选人"
    assert rec.role_title == "资深后端"
    assert rec.company_name == "ACME"


def test_create_accepts_object_match_result(svc):
    class MR:
        match_score = 77
        reasons = ["技能契合"]
        skill_gaps = []
        risks = ["到岗不确定"]

    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(),
            role=_role(),
            match_result=MR(),
            notify=False,
        )
    )
    assert rec.match_score == 77
    assert rec.match_reasons == ["技能契合"]
    assert rec.risks == ["到岗不确定"]


def test_create_org_id_fallback_from_role_then_candidate(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(org_id="org_c"),
            role={"id": "r", "title": "t"},  # no org on role
            match_result=_match(),
            notify=False,
        )
    )
    assert rec.org_id == "org_c"


def test_create_invokes_notify_dispatcher(svc):
    with patch("services.notify.dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = True
        rec = asyncio.run(
            svc.create_recommendation(
                candidate=_candidate(),
                role=_role(),
                match_result=_match(),
                notify=True,
                hr_user_id="hr-1",
            )
        )
        assert mock_dispatch.await_count == 1
        _, kwargs = mock_dispatch.call_args
        assert kwargs["user_id"] == "hr-1"
        assert kwargs["channel"] == "in_app"
        assert kwargs["payload"]["recommendation_id"] == rec.id
        assert kwargs["payload"]["type"] == "talent_recommendation"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_lifecycle_viewed_accepted_rejected(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(), match_result=_match(), notify=False
        )
    )
    rid = rec.id

    viewed = asyncio.run(svc.mark_viewed(rid))
    assert viewed.status == "viewed"
    assert viewed.viewed_at is not None

    accepted = asyncio.run(svc.accept(rid))
    assert accepted.status == "accepted"
    assert accepted.accepted_at is not None


def test_reject_records_reason(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(), match_result=_match(), notify=False
        )
    )
    rejected = asyncio.run(svc.reject(rec.id, reason="薪资不匹配"))
    assert rejected.status == "rejected"
    assert rejected.rejected_reason == "薪资不匹配"
    assert rejected.rejected_at is not None


def test_update_status_rejects_invalid_status(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(), match_result=_match(), notify=False
        )
    )
    with pytest.raises(ValueError):
        asyncio.run(svc._update_status(rec.id, "bogus"))


def test_get_missing_returns_none(svc):
    assert asyncio.run(svc.get("nope")) is None


# ---------------------------------------------------------------------------
# list_for_org + scoping + seed
# ---------------------------------------------------------------------------

def test_list_scoped_to_org(svc):
    asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(org_id="org_a"),
            match_result=_match(), notify=False,
        )
    )
    asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(id="c2"), role=_role(org_id="org_b"),
            match_result=_match(), notify=False,
        )
    )
    a = asyncio.run(svc.list_for_org(org_id="org_a"))
    b = asyncio.run(svc.list_for_org(org_id="org_b"))
    assert len(a) == 1 and a[0].org_id == "org_a"
    assert len(b) == 1 and b[0].org_id == "org_b"


def test_list_status_filter(svc):
    r1 = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(), match_result=_match(), notify=False
        )
    )
    r2 = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(id="c2"), role=_role(),
            match_result=_match(), notify=False,
        )
    )
    asyncio.run(svc.accept(r2.id))
    pending = asyncio.run(svc.list_for_org(org_id="org_acme", status="pending"))
    accepted = asyncio.run(svc.list_for_org(org_id="org_acme", status="accepted"))
    assert all(r.status == "pending" for r in pending)
    assert all(r.status == "accepted" for r in accepted)
    assert any(r.id == r1.id for r in pending)
    assert any(r.id == r2.id for r in accepted)


def test_list_seeds_demo_when_empty(svc):
    recs = asyncio.run(svc.list_for_org(org_id="org_demo"))
    assert len(recs) >= 1
    assert all(r.org_id == "org_demo" for r in recs)


# ---------------------------------------------------------------------------
# render_resume_text (download)
# ---------------------------------------------------------------------------

def test_render_resume_text_includes_contact_and_match(svc):
    rec = asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(), role=_role(), match_result=_match(), notify=False
        )
    )
    text = asyncio.run(svc.render_resume_text(rec.id))
    assert text is not None
    assert "测试候选人" in text
    assert "talent@example.com" in text
    assert "88" in text  # score
    assert "技能匹配 5/5" in text
    assert "缺 K8s 经验" in text


def test_render_resume_text_missing(svc):
    assert asyncio.run(svc.render_resume_text("nope")) is None


# ===========================================================================
# API tests
# ===========================================================================

@pytest.fixture()
def app():
    from fastapi import FastAPI
    from api.recommendation_records import router
    from api.auth import get_current_user

    application = FastAPI()
    application.include_router(router, prefix="/api/recommendations")
    # default user: employer (client) of org_acme
    application.dependency_overrides[get_current_user] = lambda: _User(
        UserRole.client, org_id="org_acme"
    )
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_service():
    # isolate the singleton used by the API's get_service() dependency
    reset_service(supabase=None)
    yield
    reset_service(supabase=None)


def _seed_one(svc: RecommendationService, org_id: str = "org_acme"):
    return asyncio.run(
        svc.create_recommendation(
            candidate=_candidate(),
            role=_role(org_id=org_id),
            match_result=_match(),
            notify=False,
        )
    )


def test_api_list_returns_summaries_without_pii(client, svc):
    _seed_one(svc, "org_acme")
    # employer passes org_id via query (no real JWT in tests)
    r = client.get("/api/recommendations?org_id=org_acme")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    # list must NOT include resume_snapshot / contact_info
    assert "resume_snapshot" not in data[0]
    assert "contact_info" not in data[0]
    assert data[0]["match_score"] == 88


def test_api_detail_returns_resume_and_contact_and_marks_viewed(client, svc):
    rec = _seed_one(svc, "org_acme")
    r = client.get(f"/api/recommendations/{rec.id}?org_id=org_acme")
    assert r.status_code == 200
    body = r.json()
    assert body["resume_snapshot"]["skills"] == ["Python", "Go", "Redis"]
    assert body["contact_info"]["email"] == "talent@example.com"
    assert body["can_download"] is False  # client, not admin
    assert body["status"] == "viewed"  # auto-advanced from pending


def test_api_status_accept(client, svc):
    rec = _seed_one(svc, "org_acme")
    r = client.patch(
        f"/api/recommendations/{rec.id}/status?org_id=org_acme",
        json={"status": "accepted"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


def test_api_status_reject_with_reason(client, svc):
    rec = _seed_one(svc, "org_acme")
    r = client.patch(
        f"/api/recommendations/{rec.id}/status?org_id=org_acme",
        json={"status": "rejected", "reason": "薪资不匹配"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["rejected_reason"] == "薪资不匹配"


def test_api_status_invalid_value_422(client, svc):
    rec = _seed_one(svc, "org_acme")
    r = client.patch(
        f"/api/recommendations/{rec.id}/status?org_id=org_acme",
        json={"status": "bogus"},
    )
    assert r.status_code == 422


def test_api_download_admin_only_for_client(client, svc):
    """甲方合同: 资料查看下载导出权限仅平台管理员 — client gets 403."""
    rec = _seed_one(svc, "org_acme")
    r = client.get(f"/api/recommendations/{rec.id}/download")
    assert r.status_code == 403


def test_api_download_succeeds_for_admin(client, app, svc):
    """Admin can download the resume text."""
    from api.auth import get_current_user

    rec = _seed_one(svc, "org_acme")
    app.dependency_overrides[get_current_user] = lambda: _User(UserRole.admin)
    r = client.get(f"/api/recommendations/{rec.id}/download")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "测试候选人" in r.text
    assert "talent@example.com" in r.text


def test_api_download_admin_404_for_missing(client, app):
    from api.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _User(UserRole.admin)
    r = client.get("/api/recommendations/999999/download")
    assert r.status_code == 404


def test_api_cross_org_detail_404(client, svc):
    """Employer of org_acme cannot see org_other's recommendation (no leak)."""
    rec = _seed_one(svc, "org_other")
    r = client.get(f"/api/recommendations/{rec.id}?org_id=org_acme")
    assert r.status_code == 404


def test_api_admin_can_view_any_org(client, app, svc):
    from api.auth import get_current_user

    rec = _seed_one(svc, "org_other")
    app.dependency_overrides[get_current_user] = lambda: _User(UserRole.admin)
    r = client.get(f"/api/recommendations/{rec.id}?org_id=org_other")
    assert r.status_code == 200
    assert r.json()["can_download"] is True


def test_api_list_empty_when_no_org_claim(client):
    # employer with no org_id claim and no ?org_id= sees nothing
    r = client.get("/api/recommendations")
    assert r.status_code == 200
    assert r.json() == []


def test_api_list_invalid_status_422(client):
    r = client.get("/api/recommendations?org_id=org_acme&status=bogus")
    assert r.status_code == 422
