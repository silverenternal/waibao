"""T1106 — Pilot 邀请服务 (生成 token + 发邮件).

职责:
- ``create_invitation(program_id, email, role, invited_by)``  -> 邀请记录 + secure token
- ``build_invite_url(token, base_url)``  -> 给前端用的激活 URL
- ``send_invite_email``  -> 通过 ``services.notify`` 走 SMTP 通道发送邀请邮件

邮件发送失败不抛:邀请记录仍然写入 (管理员可在 mothership 后台重新触发).
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.services.pilot_invitation")

DEFAULT_TOKEN_BYTES = 32
DEFAULT_TTL_DAYS = 14


@dataclass(slots=True)
class Invitation:
    """邀请记录 (内存表示)."""

    id: str
    program_id: str
    email: str
    role: str
    token: str
    invited_by: Optional[str]
    invited_at: str
    expires_at: str
    status: str
    invite_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "program_id": self.program_id,
            "email": self.email,
            "role": self.role,
            "invited_by": self.invited_by,
            "invited_at": self.invited_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "invite_url": self.invite_url,
        }


def _base_url() -> str:
    """前端根 URL (用于邀请链接)."""
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


def generate_invite_token() -> str:
    """生成 URL-safe 邀请 token (默认 32 字节)."""
    return secrets.token_urlsafe(DEFAULT_TOKEN_BYTES)


def build_invite_url(token: str, base_url: str | None = None) -> str:
    """拼接邀请链接:  ``{base_url}/onboarding/accept?token={token}``."""
    base = (base_url or _base_url()).rstrip("/")
    return f"{base}/onboarding/accept?token={token}"


def _render_invite_email(*, program_name: str, invite_url: str, role: str, organisation_name: str | None) -> tuple[str, str, str]:
    """渲染邀请邮件 (subject, plain text, html).

    注意: 文案保持简洁,把"如何开始"放在 CTA 按钮上.
    """
    subject = f"邀请您试用 {program_name}"
    org_line = f"来自 {organisation_name}" if organisation_name else ""
    body_text = (
        f"您好,\n\n"
        f"我们邀请您试用 {program_name} ({role})。{org_line}\n\n"
        f"请于 14 天内点击以下链接开始试用:\n{invite_url}\n\n"
        f"如果链接无法点击,请复制到浏览器地址栏。\n\n"
        f"— waibao Pilot Team"
    )
    body_html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto;">
  <h2 style="color:#0f172a;">试用邀请:{program_name}</h2>
  <p style="color:#475569;">您被邀请以 <b>{role}</b> 身份参与本次试用 {('('+org_line+')') if org_line else ''}。</p>
  <p style="margin: 24px 0;">
    <a href="{invite_url}"
       style="background:#2563eb;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">
       开始试用
    </a>
  </p>
  <p style="color:#94a3b8;font-size:12px;">链接 14 天内有效。如果按钮无法点击,请复制以下地址到浏览器:<br>
    <span style="word-break:break-all;color:#475569;">{invite_url}</span>
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
  <p style="color:#94a3b8;font-size:12px;">waibao Pilot Team</p>
</div>
"""
    return subject, body_text, body_html


async def create_invitation(
    *,
    program_id: str,
    email: str,
    role: str = "jobseeker",
    invited_by: str | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    base_url: str | None = None,
    send_email: bool = True,
) -> Invitation:
    """创建一条 pilot 邀请记录 (可选择同步发邮件).

    Returns:
        ``Invitation`` 实例,含 invite_url.
    """
    if not email or "@" not in email:
        raise ValueError("invalid email")
    if role not in {"jobseeker", "employer", "observer", "talent_partner", "client", "admin"}:
        raise ValueError(f"invalid role: {role}")

    supabase = get_supabase_admin()
    token = generate_invite_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

    # 查 program 信息 (为了邮件渲染)
    program_name = "Pilot Program"
    organisation_name: str | None = None
    try:
        prog_resp = (
            supabase.table("pilot_programs")
            .select("name, organisation_id, organisations(name)")
            .eq("id", program_id)
            .single()
            .execute()
        )
        if prog_resp.data:
            program_name = prog_resp.data.get("name") or program_name
            org_obj = prog_resp.data.get("organisations")
            if isinstance(org_obj, dict):
                organisation_name = org_obj.get("name")
            elif isinstance(org_obj, list) and org_obj:
                organisation_name = org_obj[0].get("name")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pilot_invitation: failed to load program info: %s", exc)

    invite_url = build_invite_url(token, base_url)

    insert_payload = {
        "program_id": program_id,
        "email": email.lower().strip(),
        "role": role,
        "invite_token": token,
        "invited_by": invited_by,
        "status": "pending",
        "expires_at": expires_at,
        "metadata": {"invite_url": invite_url},
    }
    resp = supabase.table("pilot_invitations").insert(insert_payload).execute()
    rows = resp.data or []
    if not rows:
        raise RuntimeError("pilot_invitation: insert returned no rows")
    row = rows[0]

    invitation = Invitation(
        id=row["id"],
        program_id=row["program_id"],
        email=row["email"],
        role=row["role"],
        token=token,
        invited_by=row.get("invited_by"),
        invited_at=row["invited_at"],
        expires_at=row["expires_at"],
        status=row["status"],
        invite_url=invite_url,
    )

    if send_email:
        try:
            await _send_invite_email(
                email=email,
                role=role,
                program_name=program_name,
                organisation_name=organisation_name,
                invite_url=invite_url,
            )
        except Exception as exc:  # noqa: BLE001
            # 邮件失败不影响邀请记录;记录到 metadata 便于排障
            logger.warning(
                "pilot_invitation: email send failed for %s: %s", email, exc
            )
            supabase.table("pilot_invitations").update(
                {"metadata": {"invite_url": invite_url, "email_error": str(exc)}}
            ).eq("id", invitation.id).execute()

    return invitation


async def _send_invite_email(
    *,
    email: str,
    role: str,
    program_name: str,
    organisation_name: str | None,
    invite_url: str,
) -> bool:
    """通过 ``services.notify`` 推送 SMTP 邮件 (失败抛异常由调用方捕获)."""
    # 局部导入避免循环
    from services.notify import dispatch

    subject, body_text, body_html = _render_invite_email(
        program_name=program_name,
        invite_url=invite_url,
        role=role,
        organisation_name=organisation_name,
    )
    return await dispatch(
        channel="smtp",
        user_id=email,                 # pilot 邀请时 user 还没注册,先以 email 充作 user_id
        title=subject,
        content=body_text,
        payload={"html": body_html, "metadata": {"invite_url": invite_url}},
        recipients=[email],
    )


async def accept_invitation(*, token: str, user_id: str) -> dict[str, Any]:
    """接受邀请:把 ``pending`` -> ``accepted``,记录 ``accepted_at``.

    Returns:
        dict 含 program_id, role, status.
    """
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_invitations")
        .select("*")
        .eq("invite_token", token)
        .single()
        .execute()
    )
    if not resp.data:
        raise LookupError("invitation not found")
    inv = resp.data

    if inv["status"] != "pending":
        raise PermissionError(f"invitation is {inv['status']}")

    # 过期检查
    try:
        exp = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            supabase.table("pilot_invitations").update({"status": "expired"}).eq(
                "id", inv["id"]
            ).execute()
            raise PermissionError("invitation expired")
    except ValueError:
        pass

    update_resp = (
        supabase.table("pilot_invitations")
        .update({"status": "accepted", "accepted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", inv["id"])
        .execute()
    )
    if not update_resp.data:
        raise RuntimeError("failed to update invitation")

    return {
        "invitation_id": inv["id"],
        "program_id": inv["program_id"],
        "role": inv["role"],
        "status": "accepted",
        "user_id": user_id,
    }


__all__ = [
    "Invitation",
    "accept_invitation",
    "build_invite_url",
    "create_invitation",
    "generate_invite_token",
]