"""T1204 — 钉钉审批流 (业务层).

把 waibao 工单状态变更 → 钉钉审批流.

工单状态机:
  open → in_progress → closed / blocked
  urgent 工单必须经过审批 → 创建钉钉审批实例 → 审批通过 → 才推进.

数据流:
  ticket.status change → 这里 → DingTalkApproval.create_instance
  → external instance_id 写回 corp_approval_instances
  → 异步 webhook 接收审批结果 → 更新 ticket.status
"""
from __future__ import annotations

import logging
import os
from typing import Any

from api.deps import get_supabase_admin  # type: ignore

logger = logging.getLogger("waibao.dingtalk_approval")

DEFAULT_TEMPLATE_ID = os.getenv("DINGTALK_APPROVAL_TEMPLATE", "waibao-ticket-v1")


def map_ticket_to_form(ticket: dict[str, Any]) -> list[dict[str, Any]]:
    """工单 → 钉钉审批表单字段."""
    return [
        {"name": "title", "value": str(ticket.get("title", ""))},
        {"name": "priority", "value": str(ticket.get("priority", "medium"))},
        {"name": "description", "value": str(ticket.get("description", ""))},
        {"name": "status_from", "value": str(ticket.get("status", "open"))},
        {"name": "status_to", "value": str(ticket.get("next_status", "in_progress"))},
        {"name": "owner", "value": str(ticket.get("owner_name", ""))},
    ]


async def submit_ticket_approval(
    *,
    binding_id: str,
    ticket_id: str,
    approver_user_ids: list[str],
    originator_user_id: str,
    dept_id: str,
    form_components: list[dict[str, Any]] | None = None,
    process_code: str | None = None,
) -> dict[str, Any]:
    """创建钉钉审批实例,记录到 corp_approval_instances."""
    sb = get_supabase_admin()

    ticket = (
        sb.table("tickets").select("*").eq("id", ticket_id).maybe_single().execute()
    )
    if not ticket.data:
        raise ValueError(f"ticket not found: {ticket_id}")

    form_components = form_components or map_ticket_to_form(ticket.data)

    process_code = process_code or DEFAULT_TEMPLATE_ID

    # 这里仅写本地记录,实际创建需要 access_token — 调用方用 DingTalkApproval
    record = {
        "binding_id": binding_id,
        "ticket_id": ticket_id,
        "external_instance_id": "",  # 创建后回填
        "template_id": process_code,
        "form_data": {"components": form_components, "approvers": approver_user_ids, "originator": originator_user_id, "dept_id": dept_id},
        "status": "pending",
        "approver_external_id": ",".join(approver_user_ids) or None,
    }
    res = sb.table("corp_approval_instances").insert(record).execute()
    return res.data[0] if res.data else {}


def update_instance_result(
    *,
    binding_id: str,
    external_instance_id: str,
    status: str,
    approver_external_id: str | None = None,
) -> dict[str, Any]:
    """钉钉回调 → 更新实例状态 + 同步工单."""
    sb = get_supabase_admin()

    res = (
        sb.table("corp_approval_instances")
        .update(
            {
                "external_instance_id": external_instance_id,
                "status": status,
                "approver_external_id": approver_external_id,
                "synced_to_ticket": False,
            }
        )
        .eq("binding_id", binding_id)
        .eq("external_instance_id", external_instance_id)
        .execute()
    )
    row = res.data[0] if res.data else {}

    if row.get("ticket_id") and status in ("approved", "rejected"):
        _push_ticket_status(sb, row["ticket_id"], "approved" if status == "approved" else "blocked")

    return row


def _push_ticket_status(sb: Any, ticket_id: str, status: str) -> None:
    try:
        sb.table("tickets").update({"status": status, "approval_synced": True}).eq("id", ticket_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("push ticket status failed: %s", exc)


__all__ = [
    "DEFAULT_TEMPLATE_ID",
    "map_ticket_to_form",
    "submit_ticket_approval",
    "update_instance_result",
]