"""Shared scenarios / payloads for Locust load tests (T1104 + T1105).

This module centralizes fake data generation so individual locustfile.py /
ws_locustfile.py stay slim. Faker is used to keep payloads realistic without
touching the real database.

Usage:
    from tests.load.scenarios import fake_resume_text, fake_user_id

    # or invoke directly:  python -m tests.load.scenarios
"""
from __future__ import annotations

import os
import random
import string
import uuid
from typing import Any

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    Faker = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Faker bootstrap (zh_CN + en_US)
# ---------------------------------------------------------------------------

if Faker is not None:
    _FAKER_ZH = Faker("zh_CN")
    _FAKER_EN = Faker("en_US")
    Faker.seed_instance(42)
else:  # pragma: no cover
    _FAKER_ZH = None
    _FAKER_EN = None


def _faker(locale: str = "en"):
    return _FAKER_ZH if locale == "zh" else _FAKER_EN


def _text_or_fallback(faker_attr: str, fallback: str, locale: str = "en") -> str:
    f = _faker(locale)
    if f is None:
        return fallback
    try:
        return str(getattr(f, faker_attr)())
    except Exception:  # pragma: no cover
        return fallback


# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------

DEMO_CANDIDATE_ID = "00000000-0000-0000-0000-000000000001"
DEMO_ROLE_ID = "00000000-0000-0000-0000-000000000002"
DEMO_ORG_ID = "00000000-0000-0000-0000-000000000003"


def fake_user_id() -> str:
    return str(uuid.uuid4())


def fake_org_id() -> str:
    return str(uuid.uuid4())


def fake_role_id() -> str:
    return str(uuid.uuid4())


def fake_ticket_id() -> str:
    return str(uuid.uuid4())


def fake_room_id() -> str:
    return str(uuid.uuid4())


def fake_short_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# User registration / resume / journal payloads
# ---------------------------------------------------------------------------

def fake_user_payload(role: str = "jobseeker", locale: str = "zh") -> dict[str, Any]:
    """Random registration payload for POST /api/auth/register (or seed)."""
    name = _text_or_fallback("name", "测试用户", locale)
    email = _text_or_fallback("email", f"user{uuid.uuid4().hex[:8]}@example.com", locale)
    return {
        "email": email,
        "password": "LoadTest!2026",
        "full_name": name,
        "role": role,
        "locale": locale,
    }


def fake_resume_text(locale: str = "zh") -> str:
    f = _faker(locale)
    if f is None:
        return f"{fake_user_id()} | 5 years Python | FastAPI / PostgreSQL"
    skills = ", ".join(f.random_elements(
        elements=[
            "Python", "FastAPI", "PostgreSQL", "Redis", "Docker",
            "Kubernetes", "LangChain", "OpenAI", "Vue", "React",
            "TypeScript", "Next.js", "Tailwind",
        ],
        length=5,
        unique=True,
    ))
    years = random.randint(1, 12)
    return (
        f"{f.name()} | {years} years experience | "
        f"Skills: {skills} | Email: {f.email()}"
    )


def fake_resume_upload_payload(locale: str = "zh") -> dict[str, Any]:
    """Metadata for resume upload (POST /api/uploads)."""
    return {
        "filename": f"resume_{fake_short_code()}.pdf",
        "content_type": "application/pdf",
        "size_bytes": random.randint(50_000, 2_000_000),
        "text": fake_resume_text(locale),
        "language": locale,
    }


def fake_journal_payload(locale: str = "zh") -> dict[str, Any]:
    f = _faker(locale)
    sentences = (
        f.sentence() if f is not None
        else "今天学了一个新框架,感觉有收获。"
    )
    return {
        "content": sentences,
        "mood_score": round(random.uniform(0.0, 1.0), 2),
        "tags": random.sample(
            ["growth", "challenge", "win", "blocker", "learning"],
            k=random.randint(0, 2),
        ),
    }


def fake_emotion_text(locale: str = "zh") -> str:
    return _text_or_fallback(
        "sentence",
        "I feel a bit stressed about tomorrow's interview.",
        locale,
    )


def fake_clarifier_text(locale: str = "zh") -> str:
    return (
        "Help me summarize my profile and identify my real needs. "
        + fake_resume_text(locale)
    )


# ---------------------------------------------------------------------------
# Employer payloads
# ---------------------------------------------------------------------------

def fake_org_payload(locale: str = "zh") -> dict[str, Any]:
    f = _faker(locale)
    name = f.company() if f is not None else f"Org-{fake_short_code()}"
    return {
        "name": name,
        "industry": random.choice(
            ["SaaS", "FinTech", "EdTech", "HealthTech", "Manufacturing"]
        ),
        "size": random.choice(["1-10", "11-50", "51-200", "201-500", "500+"]),
        "country": "CN" if locale == "zh" else "US",
        "credit_code": "".join(random.choices(string.digits, k=18)),
    }


def fake_role_payload(org_id: str | None = None, locale: str = "zh") -> dict[str, Any]:
    f = _faker(locale)
    title = f.job() if f is not None else "Senior Backend Engineer"
    return {
        "organisation_id": org_id or fake_org_id(),
        "title": title,
        "department": random.choice(["Engineering", "Product", "Design", "Ops"]),
        "location": "Shanghai" if locale == "zh" else "Remote",
        "seniority": random.choice(["junior", "mid", "senior", "staff"]),
        "salary_min": random.randint(20, 60) * 1000,
        "salary_max": random.randint(60, 120) * 1000,
        "description": fake_resume_text(locale),
        "status": "open",
    }


def fake_vision_payload(locale: str = "zh") -> dict[str, Any]:
    return {
        "text": (
            "我们希望 3 年内成为 SaaS 行业 TOP 3,以客户成功为核心。"
            if locale == "zh"
            else "We aim to be a TOP-3 SaaS in 3 years, customer success first."
        )
    }


def fake_brief_payload(role_id: str | None = None, locale: str = "zh") -> dict[str, Any]:
    return {
        "role_id": role_id or fake_role_id(),
        "summary": _text_or_fallback("bs", "Looking for senior engineers.", locale),
        "must_haves": ["Python", "PostgreSQL", "Distributed systems"],
        "nice_to_haves": ["Kubernetes", "LangChain"],
        "culture_notes": _text_or_fallback("catch_phrase", "move fast.", locale),
    }


def fake_jd_payload(role_id: str | None = None, locale: str = "zh") -> dict[str, Any]:
    return {
        "role_id": role_id or fake_role_id(),
        "responsibilities": [
            "Design and implement backend services in Python/FastAPI",
            "Own PostgreSQL schema and performance tuning",
            "Mentor junior engineers and review PRs",
        ],
        "requirements": [
            "5+ years Python experience",
            "Strong SQL and database fundamentals",
            "Excellent written communication",
        ],
    }


def fake_ticket_payload(role_id: str | None = None, locale: str = "zh") -> dict[str, Any]:
    return {
        "role_id": role_id or fake_role_id(),
        "subject": _text_or_fallback("sentence", "Need help with interview feedback.", locale),
        "body": fake_resume_text(locale),
        "priority": random.choice(["low", "medium", "high", "urgent"]),
    }


# ---------------------------------------------------------------------------
# Matching payloads
# ---------------------------------------------------------------------------

def fake_two_way_match_payload(candidate_id: str | None = None, role_id: str | None = None) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id or DEMO_CANDIDATE_ID,
        "role_id": role_id or DEMO_ROLE_ID,
        "compute_explanations": random.random() < 0.3,  # only ~30% expensive
    }


# ---------------------------------------------------------------------------
# WebSocket payloads
# ---------------------------------------------------------------------------

def fake_room_message(room_id: str | None = None, locale: str = "zh") -> dict[str, Any]:
    return {
        "type": "publish",
        "delivery_id": fake_short_code(12),
        "payload": {
            "text": _text_or_fallback("sentence", "Hello room", locale),
            "ts": 0,
        },
    }


def fake_ws_invoke_payload(locale: str = "zh") -> dict[str, Any]:
    return {
        "type": "message",
        "text": fake_emotion_text(locale),
        "context": {},
    }


# ---------------------------------------------------------------------------
# CLI sanity check
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import json
    samples = {
        "user": fake_user_payload(),
        "resume": fake_resume_upload_payload(),
        "journal": fake_journal_payload(),
        "org": fake_org_payload(),
        "role": fake_role_payload(),
        "brief": fake_brief_payload(),
        "jd": fake_jd_payload(),
        "ticket": fake_ticket_payload(),
        "match": fake_two_way_match_payload(),
        "ws_message": fake_room_message(),
    }
    print(json.dumps(samples, ensure_ascii=False, indent=2))