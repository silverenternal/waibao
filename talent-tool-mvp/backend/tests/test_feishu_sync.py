"""T1204 — 飞书通讯录同步 + 审批 单测."""
from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services.corp_sync import CorpSyncService, CorpUser
from services.feishu_sync import FEISHU_API_BASE, FeishuApproval, FeishuCorpClient


class FakeHttp:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        self.calls.append(("GET", params or {}))
        return self.payload

    def post(self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        self.calls.append(("POST", json or {}))
        return self.payload


def make_dept(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"code": 0, "data": {"items": items}}


def make_user(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"code": 0, "data": {"items": items}}


class TestFeishuCorpClient:
    def test_fetch_departments_parses(self):
        http = FakeHttp(
            make_dept(
                [
                    {"open_department_id": "od-1", "name": "产品"},
                    {"open_department_id": "od-2", "name": "研发"},
                ]
            )
        )
        client = FeishuCorpClient(http, "tok")
        depts = client.fetch_departments()
        assert [d.id for d in depts] == ["od-1", "od-2"]

    def test_fetch_users_maps_fields(self):
        http = FakeHttp(
            make_user(
                [
                    {
                        "open_id": "ou-1",
                        "union_id": "on-1",
                        "name": "Alice",
                        "mobile": "13900000000",
                        "email": "a@x.com",
                        "is_tenant_manager": True,
                        "departments": [{"open_department_id": "od-1"}],
                        "status": {"is_active": True},
                    }
                ]
            )
        )
        client = FeishuCorpClient(http, "tok")
        users = client.fetch_users("od-1")
        assert len(users) == 1
        assert users[0].external_user_id == "ou-1"
        assert users[0].name == "Alice"
        assert users[0].is_admin is True
        assert users[0].active is True
        assert users[0].dept_ids == ["od-1"]

    def test_fetch_users_handles_error(self):
        http = FakeHttp({"code": 99991663, "msg": "token invalid"})
        client = FeishuCorpClient(http, "bad")
        assert client.fetch_users() == []


class TestFeishuApproval:
    def test_create_instance_returns_data(self):
        http = FakeHttp({"code": 0, "data": {"instance_id": "i-123"}})
        approval = FeishuApproval(http, "tok")
        data = approval.create_instance(
            approval_code="AC",
            user_id="ou-1",
            form_data=[[{"id": "title", "type": "input", "value": "X"}]],
        )
        assert data["instance_id"] == "i-123"

    def test_create_instance_raises_on_error(self):
        http = FakeHttp({"code": 99991663, "msg": "fail"})
        approval = FeishuApproval(http, "tok")
        with pytest.raises(RuntimeError):
            approval.create_instance(
                approval_code="AC", user_id="ou-1", form_data=[]
            )


class TestFeishuSyncAccuracy:
    def test_sync_accuracy_above_95(self):
        """100 用户,2 失败,准确率 98%."""
        from unittest.mock import MagicMock

        users = [
            CorpUser(
                external_user_id=f"u{i}",
                name=f"u{i}",
                dept_ids=["od-1"],
                active=True,
            )
            for i in range(100)
        ]

        class FakeClient:
            corp_type = "feishu"

            def fetch_departments(self):
                from services.corp_sync import CorpDept
                return [CorpDept(id="od-1", name="研发")]

            def fetch_users(self, dept_id=None):
                return users

        sb = MagicMock()
        # Patch on the underlying module where get_supabase_admin is imported from api.deps
        import services.employer.corp_sync as cs_mod

        original = cs_mod.get_supabase_admin
        cs_mod.get_supabase_admin = lambda: sb
        try:
            svc = CorpSyncService("b-1")
            orig = svc._upsert_user

            def flaky(u):
                if u.external_user_id in {"u3", "u7"}:
                    raise RuntimeError("dup key")

                orig(u)

            svc._upsert_user = flaky
            result = svc.sync_all(FakeClient())
        finally:
            cs_mod.get_supabase_admin = original

        assert result.total == 100
        assert result.succeeded == 98
        assert result.failed == 2
        assert result.accuracy == 0.98
        assert result.accuracy >= 0.95