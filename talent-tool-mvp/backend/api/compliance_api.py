"""Compliance API (T202)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.compliance")
router = APIRouter()


class CredentialUpload(BaseModel):
    file_url: str
    credential_type: str = "business_license"
    hint_company_name: str = ""
    hint_credit_code: str = ""


@router.post("/upload")
async def upload_credential(
    body: CredentialUpload,
    user: CurrentUser = Depends(get_current_user),
):
    """上传资质审核."""
    agent = registry.get_or_raise("compliance_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={
            "file_url": body.file_url,
            "credential_type": body.credential_type,
            "hint_company_name": body.hint_company_name,
            "hint_credit_code": body.hint_credit_code,
        },
    ))
    return {"text": out.text, "verdict": out.artifacts}


@router.get("/status")
async def get_compliance_status(
    organisation_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取组织资质状态."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("company_credentials")
        .select("*")
        .eq("organisation_id", organisation_id)
        .order("created_at", desc=True)
        .execute()
    )
    creds = result.data or []
    avg_trust = sum(c.get("trust_score", 0) or 0 for c in creds) / max(1, len(creds))
    return {
        "credentials": creds,
        "total": len(creds),
        "verified_count": sum(1 for c in creds if c.get("verified")),
        "average_trust_score": round(avg_trust, 2),
    }