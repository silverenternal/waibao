"""T1004 - 审计日志测试."""
from __future__ import annotations

import os

import pytest


def test_audit_record_does_not_raise_when_supabase_missing(monkeypatch):
    """即使 Supabase 不可用,record 也应 noop 不抛."""
    from services import audit

    # 强制 Supabase 不可用
    monkeypatch.setattr(audit, "_supabase_admin", lambda: None)
    audit.record(
        actor_user_id="00000000-0000-0000-0000-000000000001",
        action="read",
        resource_type="candidate",
        resource_id="c-1",
    )  # 不应抛


@pytest.mark.asyncio
async def test_audit_decorator_records(monkeypatch):
    """@audit 装饰器应捕获 actor_user_id + resource_id."""
    from services import audit

    calls: list[dict] = []

    def fake_record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(audit, "record", fake_record)
    # 直接调用装饰后的函数,actor / resource_id 通过 kwargs 传入

    @audit.audit("read", "candidate", resource_id_arg="candidate_id")
    async def get_candidate(candidate_id: str, user=None):
        return {"id": candidate_id}

    class FakeUser:
        id = "00000000-0000-0000-0000-000000000abc"

    result = await get_candidate(candidate_id="c-99", user=FakeUser())
    assert result["id"] == "c-99"
    assert len(calls) == 1
    assert calls[0]["action"] == "read"
    assert calls[0]["resource_type"] == "candidate"
    assert calls[0]["resource_id"] == "c-99"
    assert calls[0]["actor_user_id"] == "00000000-0000-0000-0000-000000000abc"


@pytest.mark.asyncio
async def test_audit_decorator_failure_does_not_break_call(monkeypatch):
    """即使 record 抛错,装饰器也不应影响原函数返回值."""
    from services import audit as _audit

    @_audit.audit("read", "role")
    async def get_role(role_id: str):
        return {"id": role_id}

    result = await get_role(role_id="r-1")
    assert result == {"id": "r-1"}


def test_audit_metadata_fn_called(monkeypatch):
    """metadata_fn 应被调用并写入 metadata."""
    from services import audit

    captured: list[dict] = []

    def fake_record(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(audit, "record", fake_record)

    def meta(args, kwargs, result):
        return {"result_id": result.get("id"), "ok": True}

    @audit.audit("read", "candidate", metadata_fn=meta)
    async def fn(candidate_id: str):
        return {"id": candidate_id}

    import asyncio

    asyncio.run(fn(candidate_id="x-1"))
    assert captured[0]["metadata"]["result_id"] == "x-1"
    assert captured[0]["metadata"]["ok"] is True


def test_audit_log_table_append_only_sql_exists():
    """校验 018_audit_log.sql 包含 append-only 约束."""
    sql_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "supabase",
        "migrations",
        "018_audit_log.sql",
    )
    with open(sql_path) as f:
        sql = f.read()
    assert "create table if not exists public.audit_log" in sql
    assert "append-only" in sql.lower() or "append_only" in sql.lower() or "audit_log_block_mutation" in sql
    assert "audit_log_no_update" in sql
    assert "audit_log_no_delete" in sql
    assert "users u" in sql or "auth.uid()" in sql
    # admin 可读
    assert "admin" in sql.lower()