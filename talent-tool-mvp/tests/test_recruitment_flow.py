"""T6109 — Recruitment flow tests (contact logs + interview schedule).

Coverage:
* service: add_contact + list_contacts (org-scoped + filter + seed-on-empty)
* service: schedule_interview + list_interviews + update_interview_status
* service: kanban aggregation (per-candidate stage derivation contact →
  interview → result)
* API: POST /contact + GET /contacts (org-scoped, 403 without org)
* API: POST /interview + GET /interviews
* API: PATCH /interviews/{id}/status (404 unknown, cross-org guarded)
* API: GET /kanban

Entirely offline — the service runs against its in-memory fallback store
(Supabase probe fails in CI → memory mode). Auth is stubbed via
``app.dependency_overrides[get_current_user]`` and org_id is passed via the
``?org_id=`` query param (admin path).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from contracts.shared import UserRole  # noqa: E402
from services.matching.recruitment_flow import (  # noqa: E402
    RecruitmentFlowService,
    reset_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _User:
    def __init__(self, role: UserRole, user_id: str = "u-test"):
        self.id = user_id
        self.email = f"{role.value}@test.com"
        self.role = role


@pytest.fixture()
def svc() -> RecruitmentFlowService:
    # Force memory mode (no Supabase) for deterministic offline tests.
    return reset_service(supabase=None)


# ---------------------------------------------------------------------------
# service — contact logs
# ---------------------------------------------------------------------------

def test_add_contact_persists_and_lists_org_scoped(svc):
    async def run():
        c = await svc.add_contact(
            {
                "candidate_id": "c1",
                "org_id": "org_a",
                "candidate_name": "张*",
                "contact_method": "phone",
                "status": "interested",
                "notes": "沟通顺畅",
            }
        )
        assert c.id
        assert c.org_id == "org_a"
        assert c.status == "interested"

        own = await svc.list_contacts(org_id="org_a")
        other = await svc.list_contacts(org_id="org_b")
        assert any(x.id == c.id for x in own)
        assert all(x.org_id == "org_b" for x in other)

    asyncio.run(run())


def test_list_contacts_filters_by_status_and_candidate(svc):
    async def run():
        for st in ("reached", "interested", "no_answer"):
            await svc.add_contact(
                {"candidate_id": "c1", "org_id": "o", "status": st}
            )
        await svc.add_contact({"candidate_id": "c2", "org_id": "o"})

        only_interested = await svc.list_contacts(org_id="o", status="interested")
        assert len(only_interested) == 1 and only_interested[0].status == "interested"

        only_c1 = await svc.list_contacts(org_id="o", candidate_id="c1")
        assert all(x.candidate_id == "c1" for x in only_c1)
        assert len(only_c1) == 3

    asyncio.run(run())


def test_list_contacts_seeds_demo_when_empty(svc):
    async def run():
        rows = await svc.list_contacts(org_id="fresh_org")
        assert len(rows) >= 1
        assert all(r.org_id == "fresh_org" for r in rows)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# service — interview schedule
# ---------------------------------------------------------------------------

def test_schedule_and_update_interview(svc):
    async def run():
        slot = await svc.schedule_interview(
            {
                "candidate_id": "c1",
                "org_id": "o",
                "date": "2026-07-20",
                "time": "14:00",
                "format": "video",
                "location": "Zoom",
            }
        )
        assert slot.status == "scheduled"

        moved = await svc.update_interview_status(slot.id, "completed")
        assert moved is not None and moved.status == "completed"

        missing = await svc.update_interview_status("999999", "cancelled")
        assert missing is None

    asyncio.run(run())


def test_list_interviews_org_scoped(svc):
    async def run():
        await svc.schedule_interview(
            {"candidate_id": "c1", "org_id": "o1", "date": "2026-07-20", "time": "10:00"}
        )
        await svc.schedule_interview(
            {"candidate_id": "c2", "org_id": "o2", "date": "2026-07-21", "time": "11:00"}
        )
        own = await svc.list_interviews(org_id="o1")
        assert all(s.org_id == "o1" for s in own)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# service — kanban aggregation
# ---------------------------------------------------------------------------

def test_kanban_derives_stage(svc):
    async def run():
        # candidate contacted, no interview → contact stage
        await svc.add_contact(
            {"candidate_id": "c1", "org_id": "o", "status": "reached"}
        )
        # candidate contacted + scheduled interview → interview stage
        await svc.add_contact(
            {"candidate_id": "c2", "org_id": "o", "status": "interested"}
        )
        await svc.schedule_interview(
            {
                "candidate_id": "c2",
                "org_id": "o",
                "date": "2026-07-20",
                "time": "10:00",
                "status": "scheduled",
            }
        )
        # candidate with completed interview → result stage
        await svc.schedule_interview(
            {
                "candidate_id": "c3",
                "org_id": "o",
                "date": "2026-07-19",
                "time": "10:00",
                "status": "completed",
            }
        )
        kb = await svc.kanban(org_id="o")
        by_id = {c["candidate_id"]: c for c in kb["candidates"]}
        assert by_id["c1"]["stage"] == "contact"
        assert by_id["c2"]["stage"] == "interview"
        assert by_id["c3"]["stage"] == "result"
        assert kb["totals"]["contacted"] >= 1
        assert kb["totals"]["interviewing"] >= 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# API — auth stubbing helpers
# ---------------------------------------------------------------------------

def _client_with_user(role: UserRole):
    """Build a standalone FastAPI app with only the recruitment router.

    Mirrors the test_recommendations.py pattern: avoids importing the full
    backend.main (which uses package-relative imports) and stubs auth via
    dependency_overrides. org_id is supplied via the ``?org_id=`` query
    param (admin-style fallback) since there is no real JWT in tests.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import get_current_user
    from api.recruitment_flow import router

    app = FastAPI()
    app.include_router(router, prefix="/api/recruitment")
    app.dependency_overrides[get_current_user] = lambda: _User(role)
    return TestClient(app), app


@pytest.fixture()
def clean_overrides():
    # No global overrides leak across tests because each helper builds its
    # own app instance. This fixture exists for symmetry with the sibling
    # test suite and is a no-op.
    yield None


# ---------------------------------------------------------------------------
# API — contact + interview + kanban
# ---------------------------------------------------------------------------

def test_api_contact_and_interview_roundtrip(clean_overrides):
    client, app = _client_with_user(UserRole.client)

    # record a contact (admin path passes ?org_id= since no JWT claim in tests)
    r = client.post(
        "/api/recruitment/contact?org_id=org_x",
        json={
            "candidate_id": "c-api-1",
            "candidate_name": "李*",
            "contact_method": "wechat",
            "status": "interested",
            "notes": "对岗位感兴趣",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["org_id"] == "org_x"
    assert body["status"] == "interested"
    contact_id = body["id"]

    # schedule an interview
    r2 = client.post(
        "/api/recruitment/interview?org_id=org_x",
        json={
            "candidate_id": "c-api-1",
            "candidate_name": "李*",
            "date": "2026-07-25",
            "time": "15:00",
            "format": "video",
            "location": "腾讯会议",
        },
    )
    assert r2.status_code == 200, r2.text
    iv = r2.json()
    assert iv["status"] == "scheduled"
    interview_id = iv["id"]

    # contacts list returns the recorded log
    r3 = client.get("/api/recruitment/contacts?org_id=org_x")
    assert r3.status_code == 200
    assert any(c["id"] == contact_id for c in r3.json())

    # interviews list returns the scheduled slot
    r4 = client.get("/api/recruitment/interviews?org_id=org_x")
    assert r4.status_code == 200
    assert any(s["id"] == interview_id for s in r4.json())

    # move interview status forward
    r5 = client.patch(
        f"/api/recruitment/interviews/{interview_id}/status?org_id=org_x",
        json={"status": "completed"},
    )
    assert r5.status_code == 200, r5.text
    assert r5.json()["status"] == "completed"


def test_api_contact_403_without_org(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    r = client.post(
        "/api/recruitment/contact",
        json={"candidate_id": "c1"},
    )
    assert r.status_code == 403


def test_api_contact_rejects_invalid_method(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    r = client.post(
        "/api/recruitment/contact?org_id=o",
        json={"candidate_id": "c1", "contact_method": "carrier_pigeon"},
    )
    assert r.status_code == 400


def test_api_interview_status_404_unknown(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    r = client.patch(
        "/api/recruitment/interviews/999999/status?org_id=o",
        json={"status": "completed"},
    )
    assert r.status_code == 404


def test_api_interview_status_rejects_invalid(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    r = client.patch(
        "/api/recruitment/interviews/1/status?org_id=o",
        json={"status": "bogus"},
    )
    assert r.status_code == 400


def test_api_kanban_returns_board(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    # seed via a contact
    client.post(
        "/api/recruitment/contact?org_id=org_k",
        json={"candidate_id": "ck1", "candidate_name": "王*"},
    )
    r = client.get("/api/recruitment/kanban?org_id=org_k")
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == "org_k"
    assert "candidates" in body and "totals" in body


def test_api_kanban_empty_org(clean_overrides):
    client, app = _client_with_user(UserRole.client)
    r = client.get("/api/recruitment/kanban")
    assert r.status_code == 200
    assert r.json()["candidates"] == []


def test_routes_registered_on_full_app_not_redirected_to_404():
    """Regression guard: the legacy /api → /api/v1 redirect middleware must
    NOT swallow /api/recruitment and /api/hr-assistant (they are not in the
    curated v1 router). A missing NEVER_REDIRECT_PREFIXES entry makes them
    308→/api/v1/...→404."""
    import main

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    # unauthenticated: expect 401/403, NOT 404 (404 = middleware swallowed it)
    r1 = client.get("/api/recruitment/kanban", follow_redirects=True)
    assert r1.status_code != 404
    r2 = client.get(
        "/api/hr-assistant/compare/0/export?format=txt", follow_redirects=True
    )
    assert r2.status_code != 404

