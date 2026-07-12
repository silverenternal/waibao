"""Tests for T1106 — Pilot program + invitation."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Mock Supabase client (chainable + stateful)
# ---------------------------------------------------------------------------


class FakeQuery:
    """链式查询 stub,支持 eq / insert / update / single / execute."""

    def __init__(self, store: "FakeStore", table: str):
        self.store = store
        self.table = table
        self._filters: dict = {}
        self._single = False
        self._update_payload: dict | None = None
        self._inserted_rows: list[dict] | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def order(self, _key, **_kwargs):
        return self

    def limit(self, _n):
        return self

    def in_(self, _key, _values):
        return self

    def gte(self, _key, _value):
        return self

    def ilike(self, _key, _value):
        return self

    def or_(self, _expr):
        return self

    def insert(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        inserted = []
        for r in rows:
            row = dict(r)
            existing = self.store.tables.setdefault(self.table, [])
            row.setdefault("id", f"uuid-{len(existing) + 1}")
            # DB 自动填充字段,这里 mock 一下,让 service 层的 row[...] 不抛 KeyError
            row.setdefault("invited_at", "2026-07-01T00:00:00+00:00")
            row.setdefault("created_at", "2026-07-01T00:00:00+00:00")
            existing.append(row)
            inserted.append(row)
        self._inserted_rows = inserted
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        # insert 优先返回刚插入的行
        if self._inserted_rows is not None:
            rows = self._inserted_rows
            return _Result(rows if not self._single else (rows[0] if rows else None))
        rows = self.store.tables.get(self.table, [])
        out = [
            r for r in rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]
        if self._update_payload is not None:
            updated = []
            for r in out:
                r.update(self._update_payload)
                updated.append(r)
            return _Result(updated if not self._single else (updated[0] if updated else None))
        if self._single:
            return _Result(out[0] if out else None)
        return _Result(out)


class _Chain:
    def __init__(self, query: FakeQuery, result: "_Result"):
        self._q = query
        self._r = result

    def execute(self):
        return self._r


class _Result:
    def __init__(self, data):
        self.data = data


class FakeStore:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_supabase(monkeypatch):
    store = FakeStore()
    # 注意: 各模块在 import 时已经把 get_supabase_admin 引用到自己的命名空间,
    # 必须 patch 它们各自命名空间下的引用,而不是只 patch api.deps.
    monkeypatch.setattr("api.deps.get_supabase_admin", lambda: store)
    monkeypatch.setattr("services.pilot_invitation.get_supabase_admin", lambda: store)
    monkeypatch.setattr("api.pilot.get_supabase_admin", lambda: store)
    monkeypatch.setattr("api.feedback.get_supabase_admin", lambda: store)
    return store


@pytest.fixture
def fake_dispatch(monkeypatch):
    """替换 SMTP 邮件发送."""
    calls: list[dict] = []

    async def _dispatch(*, channel, user_id, title, content, payload=None, recipients=None):
        calls.append(
            {
                "channel": channel,
                "user_id": user_id,
                "title": title,
                "content": content,
                "payload": payload or {},
                "recipients": recipients or [],
            }
        )
        return True

    monkeypatch.setattr("services.notify.dispatch", _dispatch)
    return calls


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_generate_invite_token_is_unique():
    from services.pilot_invitation import generate_invite_token

    a = generate_invite_token()
    b = generate_invite_token()
    assert a != b
    assert len(a) >= 30  # url-safe b64 of 32 random bytes


def test_build_invite_url_strips_trailing_slash():
    from services.pilot_invitation import build_invite_url

    url = build_invite_url("abc123", base_url="https://app.example.com/")
    assert url == "https://app.example.com/onboarding/accept?token=abc123"


def test_compute_nps_classic_formula():
    """3 promoter - 2 detractor / 7 total = +14.3."""
    from api.pilot import _compute_nps

    rows = [{"score": 10}, {"score": 9}, {"score": 9}, {"score": 8}, {"score": 7}, {"score": 3}, {"score": 0}]
    out = _compute_nps(rows)
    assert out["promoters"] == 3
    assert out["passives"] == 2
    assert out["detractors"] == 2
    assert out["responses"] == 7
    # (3 - 2) / 7 * 100 = 14.2857... → 14.3
    assert out["nps"] == 14.3


def test_compute_nps_handles_empty():
    from api.pilot import _compute_nps

    assert _compute_nps([]) == {"nps": None, "promoters": 0, "passives": 0, "detractors": 0, "responses": 0}


def test_compute_nps_ignores_non_nps_rows():
    from api.pilot import _compute_nps

    # _compute_nps 接受任何行,只关心 score 非空 (上层 API 已过滤 category='nps')
    rows = [{"score": 10}, {"score": None}]
    out = _compute_nps(rows)
    assert out["promoters"] == 1
    # 只有 score != None 才计入 responses
    assert out["responses"] == 1
    assert out["nps"] == 100.0  # 100% promoter


@pytest.mark.asyncio
async def test_create_invitation_writes_row_and_sends_email(fake_supabase, fake_dispatch):
    """完整路径:program 已存在 -> 创建邀请 -> 发邮件."""
    # 预先植入 program + org
    fake_supabase.tables["organisations"] = [
        {"id": "org-1", "name": "Acme"},
    ]
    fake_supabase.tables["pilot_programs"] = [
        {
            "id": "prog-1",
            "name": "Acme Pilot",
            "organisation_id": "org-1",
        },
    ]

    from services.pilot_invitation import create_invitation

    inv = await create_invitation(
        program_id="prog-1",
        email="alice@acme.com",
        role="employer",
        invited_by="user-1",
        send_email=True,
    )

    # 1. row 写入
    rows = fake_supabase.tables["pilot_invitations"]
    assert len(rows) == 1
    row = rows[0]
    assert row["email"] == "alice@acme.com"
    assert row["role"] == "employer"
    assert row["status"] == "pending"
    assert row["invite_token"] == inv.token

    # 2. 邮件被发出
    assert len(fake_dispatch) == 1
    sent = fake_dispatch[0]
    assert sent["channel"] == "smtp"
    assert sent["recipients"] == ["alice@acme.com"]
    assert "Acme Pilot" in sent["title"]
    assert inv.invite_url in sent["content"]


@pytest.mark.asyncio
async def test_create_invitation_invalid_email_raises(fake_supabase, fake_dispatch):
    from services.pilot_invitation import create_invitation

    with pytest.raises(ValueError):
        await create_invitation(program_id="prog-1", email="not-an-email")


@pytest.mark.asyncio
async def test_create_invitation_invalid_role_raises(fake_supabase, fake_dispatch):
    from services.pilot_invitation import create_invitation

    with pytest.raises(ValueError):
        await create_invitation(program_id="prog-1", email="a@b.com", role="hacker")


@pytest.mark.asyncio
async def test_create_invitation_email_failure_records_metadata(fake_supabase, monkeypatch):
    """邮件发送失败不抛,但 metadata 记录错误."""
    fake_supabase.tables["pilot_programs"] = [{"id": "prog-1", "name": "P", "organisation_id": "org-1"}]

    async def _fail(*_a, **_kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("services.notify.dispatch", _fail)

    from services.pilot_invitation import create_invitation

    inv = await create_invitation(program_id="prog-1", email="a@b.com")
    # invitation 仍然返回,row 仍然写入
    assert inv.email == "a@b.com"
    row = fake_supabase.tables["pilot_invitations"][0]
    assert "email_error" in row["metadata"]
    assert "smtp down" in row["metadata"]["email_error"]


@pytest.mark.asyncio
async def test_accept_invitation_marks_accepted(fake_supabase):
    fake_supabase.tables["pilot_invitations"] = [
        {
            "id": "inv-1",
            "program_id": "prog-1",
            "email": "a@b.com",
            "role": "jobseeker",
            "invite_token": "tok-xyz",
            "status": "pending",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    ]

    from services.pilot_invitation import accept_invitation

    res = await accept_invitation(token="tok-xyz", user_id="user-1")
    assert res["status"] == "accepted"
    assert res["user_id"] == "user-1"
    # row 被更新
    row = fake_supabase.tables["pilot_invitations"][0]
    assert row["status"] == "accepted"
    assert row["accepted_at"] is not None


@pytest.mark.asyncio
async def test_accept_invitation_rejects_expired(fake_supabase):
    fake_supabase.tables["pilot_invitations"] = [
        {
            "id": "inv-1",
            "program_id": "prog-1",
            "email": "a@b.com",
            "role": "jobseeker",
            "invite_token": "tok-xyz",
            "status": "pending",
            "expires_at": "2000-01-01T00:00:00+00:00",  # 已过期
        },
    ]
    from services.pilot_invitation import accept_invitation

    with pytest.raises(PermissionError):
        await accept_invitation(token="tok-xyz", user_id="u")


@pytest.mark.asyncio
async def test_accept_invitation_rejects_already_accepted(fake_supabase):
    fake_supabase.tables["pilot_invitations"] = [
        {
            "id": "inv-1",
            "program_id": "prog-1",
            "email": "a@b.com",
            "role": "jobseeker",
            "invite_token": "tok-xyz",
            "status": "accepted",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    ]
    from services.pilot_invitation import accept_invitation

    with pytest.raises(PermissionError):
        await accept_invitation(token="tok-xyz", user_id="u")


@pytest.mark.asyncio
async def test_accept_invitation_not_found(fake_supabase):
    from services.pilot_invitation import accept_invitation

    with pytest.raises(LookupError):
        await accept_invitation(token="nope", user_id="u")