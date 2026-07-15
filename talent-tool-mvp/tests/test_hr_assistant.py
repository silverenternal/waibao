"""T6108 — HR Assistant tests (interview questions + compare export).

Coverage:
* API: POST /interview-questions (role + count + difficulty → 5-10 shaped
  questions from the static question bank, with prompt / expected points /
  skills / difficulty / type / duration / weights)
* API: GET /compare/{id}/export?format=txt — renders a compare report text
  blob (the always-available fallback; docx/pdf require optional deps)

The compare endpoint itself delegates to ComparisonService over Supabase
candidates, which is not available offline, so we exercise the offline
interview-questions + export paths and the request validation paths.

Entirely offline — auth is stubbed via ``app.dependency_overrides``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from contracts.shared import UserRole  # noqa: E402


class _User:
    def __init__(self, role: UserRole, user_id: str = "u-test"):
        self.id = user_id
        self.email = f"{role.value}@test.com"
        self.role = role


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import get_current_user
    from api.hr_assistant import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User(UserRole.client)
    return TestClient(app)


# ---------------------------------------------------------------------------
# interview questions
# ---------------------------------------------------------------------------

def test_interview_questions_returns_shaped_template(client):
    r = client.post(
        "/api/hr-assistant/interview-questions",
        json={"role": "backend_engineer", "count": 8, "difficulty": "mid"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "backend_engineer"
    assert 1 <= body["count"] <= 8
    assert body["estimated_minutes"] > 0
    qs = body["questions"]
    assert len(qs) >= 1
    q = qs[0]
    for key in (
        "id",
        "title",
        "prompt",
        "expected_points",
        "skills",
        "difficulty",
        "type",
        "duration_sec",
        "weights",
    ):
        assert key in q


def test_interview_questions_unknown_role_falls_back(client):
    # question bank falls back to backend_engineer for unknown categories
    r = client.post(
        "/api/hr-assistant/interview-questions",
        json={"role": "totally_unknown_role", "count": 5},
    )
    assert r.status_code == 200
    assert len(r.json()["questions"]) >= 1


def test_interview_questions_rejects_invalid_difficulty(client):
    r = client.post(
        "/api/hr-assistant/interview-questions",
        json={"role": "product_manager", "count": 5, "difficulty": "bogus"},
    )
    assert r.status_code == 400


def test_interview_questions_requires_role(client):
    r = client.post(
        "/api/hr-assistant/interview-questions",
        json={"count": 5},
    )
    assert r.status_code == 422  # missing required field


# ---------------------------------------------------------------------------
# compare export (txt fallback, always available)
# ---------------------------------------------------------------------------

def test_compare_export_txt(client):
    r = client.get("/api/hr-assistant/compare/0/export?format=txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.content.decode("utf-8")
    assert "简历对比报告" in body


def test_compare_export_rejects_bad_format(client):
    r = client.get("/api/hr-assistant/compare/0/export?format=csv")
    assert r.status_code == 422
