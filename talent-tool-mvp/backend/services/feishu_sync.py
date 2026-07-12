"""T1204 — 飞书企业通讯录 + 审批 client.

协议:
  - 通讯录 API: https://open.feishu.cn/open-apis/contact/v3/users 等
  - 审批 API:   https://open.feishu.cn/open-apis/approval/v4/instances

依赖: tenant_access_token (调用方传入).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Protocol

from services.corp_sync import CorpClient, CorpDept, CorpUser

logger = logging.getLogger("waibao.feishu_sync")

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class HttpClient(Protocol):
    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]: ...
    def post(self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]: ...


class FeishuCorpClient(CorpClient):
    corp_type = "feishu"

    def __init__(self, http: HttpClient, tenant_access_token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {tenant_access_token}"}

    def fetch_departments(self) -> list[CorpDept]:
        url = f"{FEISHU_API_BASE}/contact/v3/departments/0/children"
        data = self._http.get(url, params={"page_size": 50}, headers=self._headers)
        if data.get("code") != 0:
            logger.warning("feishu dept errcode=%s", data.get("code"))
            return []
        items = (data.get("data") or {}).get("items") or []
        return [
            CorpDept(id=d.get("open_department_id", ""), name=d.get("name", ""))
            for d in items
        ]

    def fetch_users(self, dept_id: str | None = None) -> list[CorpUser]:
        url = f"{FEISHU_API_BASE}/contact/v3/users"
        params: dict[str, Any] = {"page_size": 50}
        if dept_id:
            params["department_id"] = dept_id
        data = self._http.get(url, params=params, headers=self._headers)
        if data.get("code") != 0:
            logger.warning("feishu user errcode=%s", data.get("code"))
            return []
        items = (data.get("data") or {}).get("items") or []
        users: list[CorpUser] = []
        for u in items:
            users.append(
                CorpUser(
                    external_user_id=u.get("open_id", ""),
                    external_union_id=u.get("union_id"),
                    name=u.get("name", ""),
                    mobile=u.get("mobile"),
                    email=u.get("email"),
                    title=None,
                    dept_ids=[d.get("open_department_id") for d in (u.get("departments") or [])],
                    is_admin=bool(u.get("is_tenant_manager")),
                    is_boss=False,
                    is_hr=False,
                    is_dept_head=False,
                    active=u.get("status", {}).get("is_active", True),
                )
            )
        return users


class FeishuApproval:
    """飞书审批 v4 封装."""

    def __init__(self, http: HttpClient, tenant_access_token: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {tenant_access_token}"}

    def create_instance(
        self,
        *,
        approval_code: str,
        user_id: str,
        form_data: Iterable[list[dict[str, Any]]],
    ) -> dict[str, Any]:
        url = f"{FEISHU_API_BASE}/approval/v4/instances"
        body = {
            "approval_code": approval_code,
            "user_id": user_id,
            "form": list(form_data),
        }
        data = self._http.post(url, json=body, headers=self._headers)
        if data.get("code") != 0:
            raise RuntimeError(f"feishu approval failed: {data}")
        return data.get("data", {})

    def get_instance(self, instance_id: str, user_id: str) -> dict[str, Any]:
        url = f"{FEISHU_API_BASE}/approval/v4/instances/{instance_id}"
        data = self._http.get(url, params={"user_id": user_id}, headers=self._headers)
        if data.get("code") != 0:
            raise RuntimeError(f"feishu approval get failed: {data}")
        return data.get("data", {})


__all__ = ["FEISHU_API_BASE", "FeishuApproval", "FeishuCorpClient", "HttpClient"]