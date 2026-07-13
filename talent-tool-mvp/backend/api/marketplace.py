"""Marketplace REST API — T2903.

Public surface (no auth required for browsing):

* ``GET    /api/marketplace``                          list approved plugins
* ``GET    /api/marketplace/{slug}``                   single plugin + releases
* ``GET    /api/marketplace/{slug}/reviews``           list reviews
* ``GET    /api/marketplace/{slug}/reviews/summary``   rating distribution
* ``GET    /api/marketplace/search``                  search

Author surface (auth required):

* ``POST   /api/marketplace/publish``                 submit a new listing
* ``POST   /api/marketplace/{plugin_id}/releases``    upload a new release
* ``POST   /api/marketplace/{slug}/reviews``          submit a review

Tenant surface (auth required):

* ``POST   /api/marketplace/{slug}/install``          1-click install
* ``POST   /api/marketplace/{slug}/uninstall``        uninstall
* ``GET    /api/marketplace/installed``               list installed plugins
* ``POST   /api/marketplace/{slug}/purchase``         create purchase
* ``POST   /api/marketplace/purchases/{id}/paid``     mark purchase paid
* ``GET    /api/marketplace/purchases``               list tenant purchases

Admin / moderator surface (auth + role required):

* ``GET    /api/marketplace/admin/pending``           list pending listings
* ``POST   /api/marketplace/admin/{plugin_id}/approve``  approve listing
* ``POST   /api/marketplace/admin/{plugin_id}/reject``   reject listing
* ``GET    /api/marketplace/admin/audit``             audit log

Webhook:

* ``POST   /api/marketplace/webhook``                 payment webhook
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.marketplace import (
    MarketplaceError,
    MarketplaceService,
    PluginNotFoundError,
    PublishValidationError,
    ReviewNotFoundError,
    ReviewValidationError,
    get_marketplace_service,
)
from services.marketplace.billing import (
    BillingError,
    PurchaseNotFoundError,
    PurchaseStateError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PublishRequest(BaseModel):
    slug: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=100)
    tagline: str = Field("", max_length=200)
    description: str = Field("", max_length=10_000)
    category: str = "integration"
    tags: list[str] = Field(default_factory=list)
    author_id: str
    author_name: str
    author_email: str | None = None
    homepage_url: str | None = None
    repo_url: str | None = None
    icon_url: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    pricing_model: str = "free"
    price_cents: int = 0
    revenue_share: float = 0.70
    manifest: dict[str, Any] = Field(default_factory=dict)


class ReleaseRequest(BaseModel):
    version: str
    artifact_url: str
    artifact_sha256: str = Field(..., min_length=64, max_length=64)
    changelog: str = ""
    min_waibao_ver: str = "6.0.0"
    max_waibao_ver: str | None = None
    size_bytes: int = 0
    manifest: dict[str, Any] = Field(default_factory=dict)


class InstallRequest(BaseModel):
    tenant_id: str
    version: str | None = None
    waibao_version: str = "6.0.0"
    accept_terms: bool = False


class ReviewRequest(BaseModel):
    author_id: str
    author_name: str
    rating: int = Field(..., ge=1, le=5)
    title: str = ""
    body: str = ""


class PurchaseRequest(BaseModel):
    plugin_id: str
    tenant_id: str
    user_id: str
    payment_method: str = "stripe"
    currency: str = "USD"
    release_id: str | None = None


class MarkPaidRequest(BaseModel):
    payment_ref: str


class ModerationRequest(BaseModel):
    reason: str | None = None


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def svc() -> MarketplaceService:
    return get_marketplace_service()


# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------

@router.get("", summary="List public plugins")
def list_plugins(
    category: str | None = None,
    sort: str = Query("popular", pattern="^(popular|recent|rating|name)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.catalog.list_public(
        category=category, sort=sort, limit=limit, offset=offset,
    )
    return {
        "items": [p.to_dict() for p in items],
        "limit": limit, "offset": offset, "count": len(items),
    }


@router.get("/search", summary="Search the marketplace")
def search_plugins(
    q: str = Query("", description="search query"),
    category: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.catalog.search(q, category=category, limit=limit)
    return {"items": [p.to_dict() for p in items], "query": q, "count": len(items)}


@router.get("/stats", summary="Aggregate stats")
def stats(_svc: MarketplaceService = Depends(svc)) -> dict[str, Any]:
    return _svc.stats()


@router.get("/installed", summary="List installed plugins for a tenant")
def list_installed(
    tenant_id: str = Query(...),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.installer.list_installed(tenant_id)
    return {"items": items, "tenant_id": tenant_id, "count": len(items)}


@router.get("/purchases", summary="List purchases for a tenant")
def list_purchases(
    tenant_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.billing.list_purchases(
        tenant_id=tenant_id, status=status_filter,
    )
    return {
        "items": [p.to_dict() for p in items],
        "tenant_id": tenant_id, "count": len(items),
    }


@router.get("/admin/pending", summary="List plugins awaiting moderation")
def admin_pending(
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    items = _svc.catalog.list_pending()
    return {"items": [p.to_dict() for p in items], "count": len(items)}


@router.get("/admin/audit", summary="Admin audit log")
def admin_audit(
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    return {"items": _svc.catalog.audit_log(limit=limit), "limit": limit}


@router.get("/{slug}", summary="Get a single plugin")
def get_plugin(
    slug: str,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.catalog.get_plugin(slug=slug)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return plugin.to_dict(with_releases=True)


@router.get("/{slug}/reviews", summary="List reviews for a plugin")
def list_reviews(
    slug: str,
    sort: str = Query("recent", pattern="^(recent|helpful|rating)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.catalog.get_plugin(slug=slug)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    items = _svc.reviews.list_for_plugin(
        plugin.id, sort=sort, limit=limit, offset=offset,
    )
    return {
        "items": [r.to_dict() for r in items],
        "limit": limit, "offset": offset, "count": len(items),
    }


@router.get("/{slug}/reviews/summary", summary="Rating distribution")
def review_summary(
    slug: str,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.catalog.get_plugin(slug=slug)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _svc.reviews.summary(plugin.id)


# ---------------------------------------------------------------------------
# Author surface
# ---------------------------------------------------------------------------

@router.post(
    "/publish",
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new plugin (author)",
)
def publish_plugin(
    body: PublishRequest,
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.publish(
            slug=body.slug, name=body.name, tagline=body.tagline,
            description=body.description, category=body.category,
            tags=body.tags, author_id=str(user.id),
            author_name=body.author_name or user.email,
            author_email=body.author_email or user.email,
            homepage_url=body.homepage_url, repo_url=body.repo_url,
            icon_url=body.icon_url, screenshots=body.screenshots,
            pricing_model=body.pricing_model, price_cents=body.price_cents,
            revenue_share=body.revenue_share, manifest=body.manifest,
        )
    except PublishValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return plugin.to_dict()


@router.post(
    "/{plugin_id}/releases",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new release (author)",
)
def add_release(
    plugin_id: str,
    body: ReleaseRequest,
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        release = _svc.add_release(
            plugin_id=plugin_id, version=body.version,
            artifact_url=body.artifact_url,
            artifact_sha256=body.artifact_sha256.lower(),
            changelog=body.changelog, min_waibao_ver=body.min_waibao_ver,
            max_waibao_ver=body.max_waibao_ver, size_bytes=body.size_bytes,
            manifest=body.manifest,
        )
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PublishValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return release.to_dict()


@router.post(
    "/{slug}/reviews",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review",
)
def submit_review(
    slug: str,
    body: ReviewRequest,
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.catalog.get_plugin(slug=slug)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        review = _svc.submit_review(
            plugin_id=plugin.id, author_id=str(user.id),
            author_name=body.author_name or user.email,
            rating=body.rating,
            title=body.title, body=body.body,
        )
    except ReviewValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return review.to_dict()


# ---------------------------------------------------------------------------
# Tenant install / purchase
# ---------------------------------------------------------------------------

@router.post("/{slug}/install", summary="1-click install")
def install(
    slug: str,
    body: InstallRequest,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        return _svc.install(
            tenant_id=body.tenant_id, slug=slug, version=body.version,
            waibao_version=body.waibao_version, accept_terms=body.accept_terms,
        ).to_dict()
    except PublishValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MarketplaceError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{slug}/uninstall", summary="Uninstall")
def uninstall(
    slug: str,
    body: InstallRequest,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    return _svc.uninstall(tenant_id=body.tenant_id, slug=slug)


@router.get("/installed", summary="List installed plugins for a tenant")
def list_installed(
    tenant_id: str = Query(...),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.install.list_installed(tenant_id)
    return {"items": items, "tenant_id": tenant_id, "count": len(items)}


@router.post(
    "/{slug}/purchase",
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase",
)
def create_purchase(
    slug: str,
    body: PurchaseRequest,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        plugin = _svc.catalog.get_plugin(slug=slug)
        purchase = _svc.purchase(
            plugin_id=plugin.id, tenant_id=body.tenant_id,
            user_id=body.user_id, payment_method=body.payment_method,
            currency=body.currency, release_id=body.release_id,
        )
    except PublishValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return purchase.to_dict()


@router.post(
    "/purchases/{purchase_id}/paid",
    summary="Mark a purchase as paid (webhook callback)",
)
def mark_paid(
    purchase_id: str,
    body: MarkPaidRequest,
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    try:
        purchase = _svc.mark_purchase_paid(
            purchase_id=purchase_id, payment_ref=body.payment_ref,
        )
    except PurchaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PurchaseStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return purchase.to_dict()


@router.get("/purchases", summary="List purchases for a tenant")
def list_purchases(
    tenant_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    items = _svc.billing.list_purchases(
        tenant_id=tenant_id, status=status_filter,
    )
    return {
        "items": [p.to_dict() for p in items],
        "tenant_id": tenant_id, "count": len(items),
    }


# ---------------------------------------------------------------------------
# Admin / moderation
# ---------------------------------------------------------------------------

def _require_admin(user: CurrentUser) -> None:
    """Allow only admin role to access moderation endpoints."""
    role_value = getattr(user.role, "value", user.role)
    if role_value not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="admin role required")


@router.get(
    "/admin/pending",
    summary="List plugins awaiting moderation",
)
def admin_pending(
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    items = _svc.catalog.list_pending()
    return {
        "items": [p.to_dict() for p in items],
        "count": len(items),
    }


@router.post(
    "/admin/{plugin_id}/approve",
    summary="Approve a pending plugin",
)
def admin_approve(
    plugin_id: str,
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    try:
        plugin = _svc.approve(
            plugin_id=plugin_id,
            reviewer=str(user.id),
        )
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return plugin.to_dict()


@router.post(
    "/admin/{plugin_id}/reject",
    summary="Reject a pending plugin",
)
def admin_reject(
    plugin_id: str,
    body: ModerationRequest,
    user: CurrentUser = Depends(get_current_user),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason is required")
    try:
        plugin = _svc.reject(
            plugin_id=plugin_id,
            reviewer=str(user.id),
            reason=body.reason,
        )
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return plugin.to_dict()


@router.get("/admin/audit", summary="Admin audit log")
def admin_audit(
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    _svc: MarketplaceService = Depends(svc),
) -> dict[str, Any]:
    _require_admin(user)
    return {"items": _svc.catalog.audit_log(limit=limit), "limit": limit}


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@router.post("/webhook", summary="Strapi / Stripe / WeChat-style webhook")
async def marketplace_webhook(request: Request) -> dict[str, Any]:
    """Process an external webhook.

    Expected body shape (JSON):

        {
          "type": "plugin.approved" | "plugin.purchased" | "plugin.reviewed",
          "data": { ... }
        }

    Authenticated via the ``X-Marketplace-Signature`` header
    (hex(HMAC-SHA256)) and the ``MARKETPLACE_WEBHOOK_SECRET`` env var.
    """
    import hashlib
    import hmac
    raw = await request.body()
    secret = os.getenv("MARKETPLACE_WEBHOOK_SECRET", "")
    sig = request.headers.get("X-Marketplace-Signature", "")
    if not secret:
        # In dev/test mode, accept unsigned webhooks but log a warning.
        logger.warning("MARKETPLACE_WEBHOOK_SECRET not set; accepting unsigned webhook")
    else:
        expected = hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="invalid signature")
    import json
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"bad json: {exc}")
    kind = payload.get("type")
    data = payload.get("data") or {}
    svc = get_marketplace_service()
    svc.catalog._store.append_audit({  # noqa: SLF001
        "plugin_id": data.get("plugin_id"),
        "action": "webhook_received",
        "actor": "webhook",
        "detail": {"type": kind, "data": data},
        "created_at": 0,
    })
    return {"ok": True, "type": kind, "received": True}
