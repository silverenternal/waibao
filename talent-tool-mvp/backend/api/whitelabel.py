"""White-label + private deployment branding API — T3003.

Endpoints (mounted at ``/api/whitelabel``):

Public surface:
    GET    /api/whitelabel/{tenant_id}                  tenant branding + css variables
    GET    /api/whitelabel/{tenant_id}/email-preview    preview rendered email
    GET    /api/whitelabel/{tenant_id}/pdf-brand        report brand metadata

Admin surface (header ``x-actor``):
    PUT    /api/whitelabel/{tenant_id}                  full upsert
    PATCH  /api/whitelabel/{tenant_id}                  partial update
    DELETE /api/whitelabel/{tenant_id}                  remove branding

All endpoints degrade to safe defaults if the Supabase table is empty.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from services.platform.whitelabel import (
    Branding,
    BrandingNotFoundError,
    BrandingValidationError,
    WhitelabelError,
    get_whitelabel_service,
    render_email_html,
    render_pdf_report_brand,
    to_css_variables,
)

logger = logging.getLogger("recruittech.api.whitelabel")
router = APIRouter(prefix="/api/whitelabel", tags=["whitelabel"])


def _actor(x_actor: Optional[str] = Header(default=None)) -> str:
    return x_actor or "admin"


# ---------------------------------------------------------------------------
# Public surface — any tenant client can read its own branding
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}", summary="Get tenant branding + CSS variables")
async def get_branding(tenant_id: str) -> dict:
    svc = get_whitelabel_service()
    branding = svc.get(tenant_id)
    return {
        "branding": branding.to_dict(),
        "css_variables": to_css_variables(branding),
    }


@router.get("/{tenant_id}/email-preview", summary="Preview the rendered email header/footer")
async def email_preview(
    tenant_id: str,
    template: str = Query("transactional"),
    subject: str = Query("预览邮件"),
) -> dict:
    svc = get_whitelabel_service()
    branding = svc.get(tenant_id)
    return {
        "template": template,
        **render_email_html(
            branding,
            body_html="<p>这是邮件正文预览。</p>",
            subject=subject,
        ),
    }


@router.get("/{tenant_id}/pdf-brand", summary="PDF report brand metadata")
async def pdf_brand(tenant_id: str) -> dict:
    svc = get_whitelabel_service()
    branding = svc.get(tenant_id)
    return render_pdf_report_brand(branding)


# ---------------------------------------------------------------------------
# Admin surface
# ---------------------------------------------------------------------------


@router.put("/{tenant_id}", summary="Upsert tenant branding")
async def upsert_branding(
    tenant_id: str,
    payload: dict,
    actor: str = Depends(_actor),
) -> dict:
    payload = dict(payload or {})
    payload["tenant_id"] = tenant_id
    try:
        branding = get_whitelabel_service().upsert(payload, actor=actor)
    except BrandingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WhitelabelError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return branding.to_dict()


@router.patch("/{tenant_id}", summary="Partial update of tenant branding")
async def patch_branding(
    tenant_id: str,
    payload: dict,
    actor: str = Depends(_actor),
) -> dict:
    payload = dict(payload or {})
    try:
        branding = get_whitelabel_service().patch(tenant_id, payload, actor=actor)
    except BrandingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WhitelabelError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return branding.to_dict()


@router.delete("/{tenant_id}", summary="Delete tenant branding")
async def delete_branding(
    tenant_id: str,
    actor: str = Depends(_actor),
) -> dict:
    ok = get_whitelabel_service().delete(tenant_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="branding not found")
    return {"deleted": True}


@router.get("/", summary="List all tenant brandings (admin only)")
async def list_branding() -> dict:
    items = [b.to_dict() for b in get_whitelabel_service().list_all()]
    return {"items": items, "count": len(items)}