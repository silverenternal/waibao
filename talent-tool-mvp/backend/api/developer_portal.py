"""Developer Portal REST endpoints — T2902.

Public-facing surface for third-party developers:

* ``POST   /api/developer/apps``                Register a new app (returns
                                                 ``client_secret`` once).
* ``GET    /api/developer/apps``                List apps owned by caller.
* ``GET    /api/developer/apps/{id}``           Get a single app.
* ``DELETE /api/developer/apps/{id}``           Revoke an app + its tokens.
* ``POST   /api/developer/apps/{id}/keys``      Mint a server-side API key
                                                 bound to the app.
* ``GET    /api/developer/apps/{id}/keys``      List keys for the app.
* ``DELETE /api/developer/apps/{id}/keys/{key_id}`` Revoke a key.
* ``POST   /api/developer/oauth/authorize``     Auth-code grant step 1.
* ``POST   /api/developer/oauth/token``         Auth-code grant step 2
                                                 (also handles refresh).
* ``POST   /api/developer/oauth/revoke``        RFC 7009 token revocation.
* ``POST   /api/developer/apps/{id}/webhooks``  Create webhook (returns
                                                 ``secret`` once).
* ``GET    /api/developer/apps/{id}/webhooks``  List webhooks.
* ``DELETE /api/developer/apps/{id}/webhooks/{wh_id}`` Delete a webhook.
* ``POST   /api/developer/apps/{id}/webhooks/{wh_id}/rotate`` Rotate secret.

All mutating endpoints require an authenticated ``CurrentUser``; the
OAuth endpoints validate ``client_id`` + ``client_secret`` themselves.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.platform.developer_portal import (
    DeveloperPortalError,
    DeveloperPortalService,
    InvalidClientError,
    InvalidGrantError,
    InvalidRequestError,
    InvalidScopeError,
    UnauthorizedClientError,
    compute_webhook_signature,
    get_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/developer", tags=["developer-portal"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AppCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    homepage_url: str = Field("", max_length=500)
    redirect_uris: list[str] = Field(..., min_length=1)
    scopes: list[str] = Field(default_factory=list)
    environment: str = Field("sandbox", pattern="^(sandbox|live)$")
    description: str = Field("", max_length=500)
    logo_url: str = Field("", max_length=500)

    @field_validator("redirect_uris")
    @classmethod
    def _abs(cls, v: list[str]) -> list[str]:
        for uri in v:
            if not uri.startswith(("http://", "https://")):
                raise ValueError(f"redirect_uri must be http(s): {uri}")
        return v


class AppOut(BaseModel):
    id: str
    name: str
    client_id: str
    organisation_id: str
    homepage_url: str
    redirect_uris: list[str]
    scopes: list[str]
    environment: str
    description: str
    logo_url: str
    created_at: str
    created_by: str


class AppCreatedOut(AppOut):
    """Returned once on creation — exposes ``client_secret``."""

    client_secret: str


class KeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_min: int = Field(default=60, ge=1, le=10_000)
    expires_at: str | None = None


class KeyOut(BaseModel):
    id: str
    app_id: str | None = None
    name: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_min: int
    expires_at: str | None
    revoked_at: str | None
    last_used_at: str | None
    created_at: str | None


class KeyCreatedOut(KeyOut):
    plaintext: str


class WebhookCreateIn(BaseModel):
    url: HttpUrl
    events: list[str] = Field(..., min_length=1)

    @field_validator("events")
    @classmethod
    def _no_dupes(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("events must be unique")
        return v


class WebhookOut(BaseModel):
    id: str
    app_id: str
    url: str
    events: list[str]
    secret_prefix: str
    created_at: str
    active: bool
    last_delivered_at: str | None
    last_status: int | None


class WebhookCreatedOut(WebhookOut):
    secret: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_id_for(user: CurrentUser) -> str:
    direct = getattr(user, "organisation_id", None)
    if direct:
        return str(direct)
    supabase = get_supabase_admin()
    try:
        res = (
            supabase.table("users")
            .select("organisation_id")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
        org = res.data.get("organisation_id") if res.data else None
    except Exception:  # noqa: BLE001
        org = None
    if not org:
        org = str(uuid.uuid4())
        try:
            supabase.table("users").update({"organisation_id": org}).eq(
                "id", str(user.id)
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.debug("auto-assign org failed: %s", exc)
    return str(org)


def _portal_error(exc: DeveloperPortalError) -> HTTPException:
    """Map service-layer error to HTTPException preserving OAuth code."""
    headers = {}
    return HTTPException(
        status_code=exc.status,
        detail={"error": exc.code, "error_description": str(exc)},
        headers=headers,
    )


def _serialize_key(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "app_id": row.get("app_id"),
        "name": row.get("name"),
        "key_prefix": row.get("key_prefix"),
        "scopes": list(row.get("scopes") or []),
        "rate_limit_per_min": int(row.get("rate_limit_per_min") or 60),
        "expires_at": row.get("expires_at"),
        "revoked_at": row.get("revoked_at"),
        "last_used_at": row.get("last_used_at"),
        "created_at": row.get("created_at"),
    }


# ---------------------------------------------------------------------------
# App CRUD
# ---------------------------------------------------------------------------


@router.post("/apps", response_model=AppCreatedOut, status_code=201)
async def register_app(
    body: AppCreateIn,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    try:
        created = svc.create_app(
            name=body.name,
            organisation_id=org,
            homepage_url=body.homepage_url,
            redirect_uris=list(body.redirect_uris),
            scopes=list(body.scopes),
            created_by=str(user.id),
            environment=body.environment,
            description=body.description,
            logo_url=body.logo_url,
        )
    except DeveloperPortalError as exc:
        raise _portal_error(exc) from exc

    public = created.app.to_public()
    return AppCreatedOut(**public, client_secret=created.client_secret)


@router.get("/apps", response_model=list[AppOut])
async def list_apps(user: CurrentUser = Depends(get_current_user)):
    org = _org_id_for(user)
    svc = get_service()
    return [AppOut(**a.to_public()) for a in svc.list_apps(organisation_id=org)]


@router.get("/apps/{app_id}", response_model=AppOut)
async def get_app(app_id: str, user: CurrentUser = Depends(get_current_user)):
    org = _org_id_for(user)
    svc = get_service()
    app = svc.get_app(app_id, organisation_id=org)
    if app is None:
        raise HTTPException(404, "not_found")
    return AppOut(**app.to_public())


@router.delete("/apps/{app_id}", status_code=204)
async def revoke_app(app_id: str, user: CurrentUser = Depends(get_current_user)):
    org = _org_id_for(user)
    svc = get_service()
    ok = svc.revoke_app(app_id, organisation_id=org)
    if not ok:
        raise HTTPException(404, "not_found")
    return None


# ---------------------------------------------------------------------------
# API Keys (per app)
# ---------------------------------------------------------------------------


@router.post("/apps/{app_id}/keys", response_model=KeyCreatedOut, status_code=201)
async def create_app_key(
    app_id: str,
    body: KeyCreateIn,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    app = svc.get_app(app_id, organisation_id=org)
    if app is None:
        raise HTTPException(404, "app_not_found")
    from services.integrations.api_key import generate_key

    gen = generate_key(body.name, organisation_id=org)
    record = {
        "id": gen.id,
        "organisation_id": org,
        "app_id": app.id,
        "name": body.name,
        "key_hash": gen.key_hash,
        "key_prefix": gen.key_prefix,
        "scopes": body.scopes or app.scopes,
        "rate_limit_per_min": body.rate_limit_per_min,
        "expires_at": body.expires_at,
        "created_by": str(user.id),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    try:
        get_supabase_admin().table("api_keys").insert(record).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("api_keys insert failed (offline OK): %s", exc)
    out = _serialize_key(record)
    return KeyCreatedOut(**out, plaintext=gen.plaintext)


@router.get("/apps/{app_id}/keys", response_model=list[KeyOut])
async def list_app_keys(
    app_id: str, user: CurrentUser = Depends(get_current_user)
):
    org = _org_id_for(user)
    svc = get_service()
    app = svc.get_app(app_id, organisation_id=org)
    if app is None:
        raise HTTPException(404, "app_not_found")
    try:
        res = (
            get_supabase_admin()
            .table("api_keys")
            .select("*")
            .eq("app_id", app.id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = res.data or []
    except Exception:  # noqa: BLE001
        rows = []
    return [KeyOut(**_serialize_key(r)) for r in rows]


@router.delete("/apps/{app_id}/keys/{key_id}", status_code=204)
async def revoke_app_key(
    app_id: str, key_id: str, user: CurrentUser = Depends(get_current_user)
):
    org = _org_id_for(user)
    svc = get_service()
    app = svc.get_app(app_id, organisation_id=org)
    if app is None:
        raise HTTPException(404, "app_not_found")
    now = datetime.now(tz=timezone.utc).isoformat()
    res = (
        get_supabase_admin()
        .table("api_keys")
        .update({"revoked_at": now})
        .eq("id", key_id)
        .eq("app_id", app.id)
        .is_("revoked_at", "null")
        .execute()
    )
    if not getattr(res, "data", None):
        raise HTTPException(404, "not_found_or_already_revoked")
    return None


# ---------------------------------------------------------------------------
# OAuth 2.0 — Authorization Code Grant
# ---------------------------------------------------------------------------


@router.post("/oauth/authorize")
async def oauth_authorize(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form(""),
    state: str = Form(""),
    code_challenge: str | None = Form(None),
    code_challenge_method: str | None = Form(None),
    user_id: str = Form(...),  # passed by the consent screen once user approves
    organisation_id: str = Form(...),
):
    """Step 1 of the auth-code flow.

    Returns ``{"code": ..., "state": ..., "redirect_uri": ...}`` so the
    client can perform its own redirect.  In a browser flow we return
    a 302 via :func:`oauth_authorize_redirect`.
    """
    svc = get_service()
    try:
        rec = svc.authorize(
            client_id=client_id,
            response_type=response_type,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            user_id=user_id,
            organisation_id=organisation_id,
        )
    except DeveloperPortalError as exc:
        raise _portal_error(exc) from exc
    return {
        "code": rec.code,
        "state": state,
        "redirect_uri": rec.redirect_uri,
        "expires_in": int(rec.expires_at - rec.created_at if hasattr(rec, "created_at") else 600),
    }


@router.post("/oauth/authorize/redirect")
async def oauth_authorize_redirect(
    request: Request,
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form(""),
    state: str = Form(""),
    user_id: str = Form(...),
    organisation_id: str = Form(...),
    code_challenge: str | None = Form(None),
    code_challenge_method: str | None = Form(None),
):
    """Browser-friendly version: 302 redirect back to ``redirect_uri``.

    Errors are appended as ``?error=...&state=...`` per RFC 6749 §4.1.2.1.
    """
    svc = get_service()
    try:
        rec = svc.authorize(
            client_id=client_id,
            response_type=response_type,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            user_id=user_id,
            organisation_id=organisation_id,
        )
    except DeveloperPortalError as exc:
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}error={exc.code}&error_description={exc}&state={state}"
        return RedirectResponse(url=url, status_code=302)

    sep = "&" if "?" in redirect_uri else "?"
    url = f"{redirect_uri}{sep}code={rec.code}&state={state}"
    return RedirectResponse(url=url, status_code=302)


@router.post("/oauth/token")
async def oauth_token(
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    scope: str | None = Form(None),
    token_type_hint: str | None = Form(None),
):
    """Step 2: exchange the code (or refresh token) for a token pair."""
    svc = get_service()
    try:
        if grant_type == "authorization_code":
            if not code or not redirect_uri:
                raise InvalidRequestError(
                    "code and redirect_uri are required for authorization_code grant"
                )
            tok = svc.exchange_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                raise InvalidRequestError("refresh_token is required")
            tok = svc.refresh(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
            )
        else:
            raise DeveloperPortalError(
                f"unsupported grant_type: {grant_type}",
                code="unsupported_grant_type",
                status=400,
            )
    except DeveloperPortalError as exc:
        raise _portal_error(exc) from exc
    payload = tok.to_dict()
    payload["expires_in"] = int(tok.expires_in)
    # Per RFC 6749 §5.1 the response must be application/json for CORS-friendly flows
    return payload


@router.post("/oauth/revoke", status_code=200)
async def oauth_revoke(
    token: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    token_type_hint: str | None = Form(None),
):
    """RFC 7009 §2.1 — always respond 200 (even on unknown token)."""
    svc = get_service()
    try:
        svc.revoke_token(
            token=token,
            client_id=client_id,
            client_secret=client_secret,
            token_type_hint=token_type_hint,
        )
    except DeveloperPortalError as exc:
        raise _portal_error(exc) from exc
    return {"revoked": True}


# ---------------------------------------------------------------------------
# Webhook subscription management
# ---------------------------------------------------------------------------


@router.post(
    "/apps/{app_id}/webhooks",
    response_model=WebhookCreatedOut,
    status_code=201,
)
async def create_webhook(
    app_id: str,
    body: WebhookCreateIn,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    try:
        sub, secret = svc.create_webhook(
            app_id=app_id,
            url=str(body.url),
            events=list(body.events),
            organisation_id=org,
        )
    except DeveloperPortalError as exc:
        raise _portal_error(exc) from exc
    return WebhookCreatedOut(**sub.to_public(), secret=secret)


@router.get(
    "/apps/{app_id}/webhooks",
    response_model=list[WebhookOut],
)
async def list_webhooks(
    app_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    return [
        WebhookOut(**w.to_public())
        for w in svc.list_webhooks(app_id=app_id, organisation_id=org)
    ]


@router.delete(
    "/apps/{app_id}/webhooks/{webhook_id}",
    status_code=204,
)
async def delete_webhook(
    app_id: str,
    webhook_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    ok = svc.delete_webhook(
        webhook_id=webhook_id, app_id=app_id, organisation_id=org
    )
    if not ok:
        raise HTTPException(404, "not_found")
    return None


@router.post(
    "/apps/{app_id}/webhooks/{webhook_id}/rotate",
    response_model=WebhookCreatedOut,
)
async def rotate_webhook_secret(
    app_id: str,
    webhook_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    org = _org_id_for(user)
    svc = get_service()
    res = svc.rotate_webhook_secret(
        webhook_id=webhook_id, app_id=app_id, organisation_id=org
    )
    if res is None:
        raise HTTPException(404, "not_found")
    sub, secret = res
    return WebhookCreatedOut(**sub.to_public(), secret=secret)


@router.get("/apps/{app_id}/webhooks/{webhook_id}/sign")
async def preview_webhook_signature(
    app_id: str,
    webhook_id: str,
    payload: str = Query(""),
    user: CurrentUser = Depends(get_current_user),
):
    """Tiny helper so the developer console can show the HMAC signing
    algorithm in action.  Returns ``{signature: <hex>}``.

    NOT a secret — for production delivery the signature is computed
    by the broker service using the plaintext secret held by the app
    owner. This endpoint exists for verification during integration.
    """
    org = _org_id_for(user)
    svc = get_service()
    sub = svc.list_webhooks(app_id=app_id, organisation_id=org)
    if not any(w.id == webhook_id for w in sub):
        raise HTTPException(404, "not_found")
    sig = compute_webhook_signature(payload.encode("utf-8"), secret=app_id)
    return {"signature": sig, "algo": "hmac-sha256"}


# ---------------------------------------------------------------------------
# OpenAPI doc helper
# ---------------------------------------------------------------------------


@router.get("/openapi.json", include_in_schema=False)
async def developer_openapi_proxy():
    """Return the live OpenAPI document so the developer portal page can
    embed Scalar / Swagger without needing a separate server-side export.

    FastAPI provides ``app.openapi()`` — we delegate there.
    """
    from fastapi import Request  # local import to avoid cycles

    # NB: We can't easily access the parent FastAPI app from a router
    # without wiring it explicitly, so we return a stub.  When mounted
    # via ``app.include_router(router)`` the framework already serves
    # /openapi.json at the root — this endpoint exists for clients
    # pinned to ``/api/developer/openapi.json``.
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "RecruitTech Developer API",
            "version": "v3.0",
            "description": "See /openapi.json for the canonical spec.",
        },
    }
