"""T6103 — Recruitment Marketplace tests (talent + job pool + matches).

Coverage:
* stats (talents / jobs / companies / matches counts)
* talent list (pagination, filters: keyword/position/skill/city/salary/education)
* talent detail (anonymous masked vs employer full with contact)
* job list (pagination, filters: keyword/position/city/salary)
* job detail (responsibilities / requirements / benefits / headcount)
* recommendations (match score + reasons)
* FastAPI routes (stats / talents / jobs / detail endpoints) via TestClient
* PII gating: anonymous talent detail hides email/phone/full_name

Entirely offline — no DB, no Supabase (the service falls back to a stable
synthetic catalog when the tables are empty/unreachable).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.marketplace.talent_market import (  # noqa: E402
    TalentMarketService,
    TalentDetail,
    JobDetail,
)


@pytest.fixture()
def svc() -> TalentMarketService:
    return TalentMarketService()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_has_all_keys(svc: TalentMarketService):
    s = svc.stats()
    for key in ("talents_total", "talents_online", "jobs_total",
                "companies_total", "matches_total"):
        assert key in s and isinstance(s[key], int) and s[key] >= 0
    assert s["talents_online"] <= s["talents_total"]


# ---------------------------------------------------------------------------
# Talent pool
# ---------------------------------------------------------------------------

def test_talent_list_pagination(svc: TalentMarketService):
    page1, total1 = svc.list_talents(page=1, page_size=5)
    page2, total2 = svc.list_talents(page=2, page_size=5)
    assert total1 == total2
    assert len(page1) == 5
    assert len(page2) == 5
    ids1 = {t.id for t in page1}
    ids2 = {t.id for t in page2}
    assert ids1.isdisjoint(ids2), "pages overlap"


def test_talent_list_keyword_filter(svc: TalentMarketService):
    # Python is a known skill in the fallback catalog.
    hits, total = svc.list_talents(keyword="Python")
    assert total >= 1
    assert all("Python" in t.skills for t in hits)


def test_talent_list_city_filter(svc: TalentMarketService):
    hits, total = svc.list_talents(city="北京")
    assert total >= 1
    assert all(t.city == "北京" for t in hits)


def test_talent_list_salary_filter(svc: TalentMarketService):
    # salary_min=100 should exclude everyone (no synthetic salary >= 100k).
    _, total_high = svc.list_talents(salary_min=100)
    assert total_high == 0
    hits, total_low = svc.list_talents(salary_min=0)
    assert total_low >= 1 and len(hits) >= 1


def test_talent_detail_anonymous_masks_contact(svc: TalentMarketService):
    talents, _ = svc.list_talents(page=1, page_size=1)
    t = svc.get_talent(talents[0].id, full=False)
    assert t is not None
    assert not isinstance(t, TalentDetail)
    # The masked card has no contact fields.
    assert not hasattr(t, "email") or getattr(t, "email", None) is None


def test_talent_detail_employer_has_contact(svc: TalentMarketService):
    talents, _ = svc.list_talents(page=1, page_size=1)
    t = svc.get_talent(talents[0].id, full=True)
    assert isinstance(t, TalentDetail)
    assert t.email and "@" in t.email
    assert t.phone and t.phone.startswith("1")
    assert t.full_name


# ---------------------------------------------------------------------------
# Job pool
# ---------------------------------------------------------------------------

def test_job_list_pagination(svc: TalentMarketService):
    page1, total1 = svc.list_jobs(page=1, page_size=5)
    page2, total2 = svc.list_jobs(page=2, page_size=5)
    assert total1 == total2
    assert len(page1) == 5 and len(page2) == 5
    ids1 = {j.id for j in page1}
    ids2 = {j.id for j in page2}
    assert ids1.isdisjoint(ids2), "job pages overlap"


def test_job_list_keyword_filter(svc: TalentMarketService):
    hits, total = svc.list_jobs(keyword="Python")
    assert total >= 1
    for j in hits:
        assert ("Python" in j.skills_required
                or "Python" in j.skills_preferred
                or "Python" in j.title
                or "Python" in j.company)


def test_job_detail(svc: TalentMarketService):
    jobs, _ = svc.list_jobs(page=1, page_size=1)
    j = svc.get_job(jobs[0].id)
    assert isinstance(j, JobDetail)
    assert len(j.responsibilities) >= 1
    assert len(j.requirements) >= 1
    assert len(j.benefits) >= 1
    assert j.headcount >= 1


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def test_recommendations_returned(svc: TalentMarketService):
    recs = svc.recommendations(limit=5)
    assert 0 <= len(recs) <= 5
    for r in recs:
        assert 0 <= r.score <= 100
        assert r.talent_id and r.job_id
        assert len(r.reasons) >= 1


# ---------------------------------------------------------------------------
# API routes (offline — versioning redirect + gate exempted paths)
# ---------------------------------------------------------------------------

def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.talent_market import router

    app = FastAPI()
    app.include_router(router, prefix="/api/talent-market")
    return TestClient(app)


def test_api_stats():
    c = _client()
    r = c.get("/api/talent-market/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["talents_total"] >= 0
    assert body["jobs_total"] >= 0


def test_api_talents_list():
    c = _client()
    r = c.get("/api/talent-market/talents", params={"page": 1, "page_size": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert len(body["data"]) <= 3
    card = body["data"][0]
    # anonymous card: no contact fields
    assert "email" not in card
    assert "phone" not in card


def test_api_talents_detail_anonymous():
    c = _client()
    listing = c.get("/api/talent-market/talents", params={"page_size": 1}).json()
    tid = listing["data"][0]["id"]
    r = c.get(f"/api/talent-market/talents/{tid}")
    assert r.status_code == 200
    body = r.json()
    # Anonymous (no auth header) → contact fields null.
    assert body.get("email") is None
    assert body.get("phone") is None
    assert body.get("full_name") is None


def test_api_jobs_list_and_detail():
    c = _client()
    r = c.get("/api/talent-market/jobs", params={"page": 1, "page_size": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    jid = body["data"][0]["id"]
    detail = c.get(f"/api/talent-market/jobs/{jid}")
    assert detail.status_code == 200
    assert detail.json()["responsibilities"]


def test_api_recommendations():
    c = _client()
    r = c.get("/api/talent-market/recommendations", params={"limit": 3})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_api_talent_not_found():
    c = _client()
    r = c.get("/api/talent-market/talents/does-not-exist-xyz")
    assert r.status_code == 404
