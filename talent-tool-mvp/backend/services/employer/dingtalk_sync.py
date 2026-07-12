"""T1204 — 钉钉企业通讯录 + 审批 client.

协议:
  - 通讯录 API: https://oapi.dingtalk.com/topapi/v2/user/list 等
  - 审批 API:   https://oapi.dingtalk.com/topapi/processinstance/create

依赖: 需要 corp_bindings.access_token (由 corp_integrations 刷新).
这里只定义 client,网络层可由调用方注入 (便于测试 mock).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Protocol

from services.employer.corp_sync import CorpClient, CorpDept, CorpUser  # direct import — avoid circular via shim

logger = logging.getLogger("waibao.dingtalk_sync")

DINGTALK_API_BASE = "https://oapi.dingtalk.com"


class HttpClient(Protocol):
    """调用方注入 (httpx / 测试 fake)."""

    def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def post(self, url: str, json: dict[str, Any] | None = None) -> dict[str, Any]: ...


class DingTalkCorpClient(CorpClient):
    corp_type = "dingtalk"

    def __init__(self, http: HttpClient, access_token: str) -> None:
        self._http = http
        self._token = access_token

    # ------------------------------------------------------------------
    # 部门
    # ------------------------------------------------------------------
    def fetch_departments(self) -> list[CorpDept]:
        url = f"{DINGTALK_API_BASE}/topapi/v2/department/listsub"
        data = self._http.get(url, params={"access_token": self._token, "dept_id": 1})
        if data.get("errcode") != 0:
            logger.warning("dingtalk dept list errcode=%s", data.get("errcode"))
            return []
        depts: list[CorpDept] = []
        for d in data.get("result", []) or []:
            depts.append(CorpDept(id=str(d.get("dept_id")), name=d.get("name", ""), parent_id=str(d.get("parentid") or "") or None))
        return depts

    # ------------------------------------------------------------------
    # 成员
    # ------------------------------------------------------------------
    def fetch_users(self, dept_id: str | None = None) -> list[CorpUser]:
        url = f"{DINGTALK_API_BASE}/topapi/v2/user/list"
        offset, page_size = 0, 100
        out: list[CorpUser] = []
        while True:
            payload = {
                "access_token": self._token,
                "dept_id": dept_id or 1,
                "cursor": offset,
                "size": page_size,
                "order": "entry_asc",
            }
            data = self._http.post(url, json=payload)
            if data.get("errcode") != 0:
                logger.warning("dingtalk user list errcode=%s", data.get("errcode"))
                return out
            result = data.get("result", {}) or {}
            for u in result.get("list", []) or []:
                out.append(
                    CorpUser(
                        external_user_id=str(u.get("userid") or u.get("unionid") or ""),
                        external_union_id=u.get("unionid"),
                        name=u.get("name", ""),
                        mobile=u.get("mobile"),
                        email=None,
                        title=u.get("title"),
                        dept_ids=[str(d) for d in (u.get("dept_id_list") or [])],
                        is_admin=bool(u.get("admin")),
                        is_boss=bool(u.get("boss")),
                        is_hr=False,
                        is_dept_head=bool(u.get("leader")),
                        active=bool(u.get("active", True)),
                    )
                )
            if not result.get("has_more"):
                break
            offset = result.get("next_cursor", offset + page_size)
        return out


# ------------------------------------------------------------
# 审批 (T1204 — 工单状态变更 → 钉钉审批流)
# ------------------------------------------------------------

class DingTalkApproval:
    """钉钉工作流审批封装.

    仅封装结构,不直接发起网络调用 — 调用方通过 http 注入.
    """

    def __init__(self, http: HttpClient, access_token: str) -> None:
        self._http = http
        self._token = access_token

    def create_instance(
        self,
        *,
        process_code: str,
        originator_user_id: str,
        dept_id: str,
        form_components: Iterable[dict[str, Any]],
        approvers: Iterable[str],
        title: str = "工单审批",
    ) -> dict[str, Any]:
        url = f"{DINGTALK_API_BASE}/topapi/processinstance/create"
        body = {
            "process_code": process_code,
            "originator_user_id": originator_user_id,
            "dept_id": dept_id,
            "form_component_values": [
                {
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                }
                for c in form_components
            ],
            "approvers": list(approvers),
            "title": title,
        }
        data = self._http.post(
            url,
            json={**body, "access_token": self._token},
        )
        if data.get("errcode") != 0:
            raise RuntimeError(f"dingtalk approval failed: {data}")
        return data.get("result", {})

    def get_instance(self, process_instance_id: str) -> dict[str, Any]:
        url = f"{DINGTALK_API_BASE}/topapi/processinstance/get"
        data = self._http.get(
            url,
            params={
                "access_token": self._token,
                "process_instance_id": process_instance_id,
            },
        )
        if data.get("errcode") != 0:
            raise RuntimeError(f"dingtalk approval get failed: {data}")
        return data.get("process_instance", {})


__all__ = ["DINGTALK_API_BASE", "DingTalkApproval", "DingTalkCorpClient", "HttpClient"]