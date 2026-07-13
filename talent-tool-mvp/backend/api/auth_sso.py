"""T2901 — SSO/SAML API endpoints.

Exposes three small surfaces:

* ``GET /api/auth/sso/providers`` — list providers the deployment
  is willing to serve.
* ``GET /api/auth/sso/{provider}/login`` — begin an SSO flow, returns
  a JSON body with the IdP redirect URL (the frontend can either
  ``window.location = url`` or do an auto-form-POST for SAML).
* ``POST /api/auth/sso/{provider}/callback`` — IdP posts the user back
  here; we verify the response, run JIT provisioning, mint a session
  and return the access + refresh tokens.

The session is also set as an HttpOnly cookie (``rt`` for the refresh
token, ``at`` for the access token) so the frontend can stay stateless
and the user keeps their session across page reloads.

A separate ``POST /api/auth/sso/refresh`` endpoint rotates the access
token using the refresh token.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from services.auth.jit import JITProvisioner, get_jit_provisioner
from services.auth.session import SessionManager, get_session_manager
from services.auth.sso import (
    SSOLoginError,
    SSOLoginRedirect,
    SSOService,
    get_sso_service,
)

logger = logging.getLogger("recruittech.api.auth_sso")

router = APIRouter(prefix="/api/auth/sso", tags=["auth-sso"])


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

ACCESS_COOKIE = "at"
REFRESH_COOKIE = "rt"


def _set_session_cookies(response: Response, *, access: str, refresh: str, ttl: int) -> None:
    secure = os.getenv("SSO_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=ttl,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CallbackBody(BaseModel):
    """Body posted to the callback by the IdP (or by the frontend)."""

    code: Optional[str] = None
    id_token: Optional[str] = None
    saml_response: Optional[str] = Field(default=None, alias="SAMLResponse")
    state: Optional[str] = None
    nonce: Optional[str] = None
    relay_state: Optional[str] = None
    code_verifier: Optional[str] = None

    class Config:
        populate_by_name = True
        extra = "ignore"


class SessionResponse(BaseModel):
    user: Dict[str, Any]
    organisation: Optional[Dict[str, Any]] = None
    access_token: str
    access_token_expires_at: float
    refresh_token: str
    refresh_token_expires_at: float
    session_id: str
    provider: str
    role: str
    groups: list[str] = []
    created: bool = False
    linked_by_email: bool = False


class RefreshResponse(BaseModel):
    access_token: str
    access_token_expires_at: float
    refresh_token: str
    refresh_token_expires_at: float
    session_id: str


# ---------------------------------------------------------------------------
# Dependency overrides (handy in tests)
# ---------------------------------------------------------------------------

def sso_service_dep() -> SSOService:
    return get_sso_service()


def session_manager_dep() -> SessionManager:
    return get_session_manager()


def jit_provisioner_dep() -> JITProvisioner:
    return get_jit_provisioner()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/providers")
async def list_providers(svc: SSOService = Depends(sso_service_dep)) -> Dict[str, Any]:
    """List the SSO providers this deployment is configured to serve."""
    providers = svc.list_providers()
    return {
        "providers": providers,
        "count": len(providers),
    }


@router.get("/{provider}/login")
async def begin_login(
    provider: str,
    relay_state: Optional[str] = Query(default=None),
    svc: SSOService = Depends(sso_service_dep),
) -> Dict[str, Any]:
    """Return the IdP redirect URL for a given provider.

    Frontends typically use this as:

        const { url } = await fetch(`/api/auth/sso/${slug}/login`).then(r => r.json());
        window.location.href = url;
    """
    try:
        redirect: SSOLoginRedirect = svc.begin_login(provider, relay_state=relay_state)
    except SSOLoginError as exc:
        msg = str(exc)
        if "Unknown SSO provider" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider!r}")
    return {
        "provider": redirect.provider,
        "url": redirect.url,
        "state": redirect.state,
        "method": redirect.method,
        "relay_state": relay_state,
    }


@router.post("/{provider}/callback", response_model=SessionResponse)
async def callback(
    provider: str,
    body: CallbackBody = Body(default_factory=CallbackBody),
    request: Request = None,
    response: Response = None,
    svc: SSOService = Depends(sso_service_dep),
    sessions: SessionManager = Depends(session_manager_dep),
    jit: JITProvisioner = Depends(jit_provisioner_dep),
) -> SessionResponse:
    """Handle an IdP callback.

    The same endpoint accepts:

      * JSON bodies (NextAuth / SPAs)
      * application/x-www-form-urlencoded bodies (SAML POST binding)

    For OIDC flows, the frontend can also forward the raw ``id_token``
    to skip the code-exchange round trip (handy in tests).
    """
    # Some SAML IdPs post form-encoded; FastAPI doesn't auto-parse them
    # into our Pydantic body, so we also look at the raw form if needed.
    saml_response = body.saml_response
    if saml_response is None and request is not None:
        try:
            form = await request.form()
            saml_response = form.get("SAMLResponse") or form.get("saml_response")
            if body.state is None:
                object.__setattr__(body, "state", form.get("state"))
            if body.relay_state is None:
                object.__setattr__(body, "relay_state", form.get("RelayState"))
        except Exception:
            pass

    try:
        claims = svc.handle_callback(
            provider,
            code=body.code,
            id_token=body.id_token,
            saml_response=saml_response,
            state=body.state,
            nonce=body.nonce,
            relay_state=body.relay_state,
        )
    except SSOLoginError as exc:
        msg = str(exc)
        if "Unknown SSO provider" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider!r}")

    # JIT provisioning
    result = jit.provision(claims)

    # Mint a session
    session = sessions.create(
        user_id=result.user["id"],
        email=result.user["email"],
        provider=provider,
        role=result.user.get("role", "member"),
        groups=result.groups,
        organisation_id=result.organisation.get("id"),
    )

    if response is not None:
        _set_session_cookies(
            response,
            access=session.access_token,
            refresh=session.refresh_token,
            ttl=int(session.access_token_expires_at - session.issued_at),
        )

    return SessionResponse(
        user=result.user,
        organisation=result.organisation,
        access_token=session.access_token,
        access_token_expires_at=session.access_token_expires_at,
        refresh_token=session.refresh_token,
        refresh_token_expires_at=session.refresh_token_expires_at,
        session_id=session.session_id,
        provider=provider,
        role=session.role,
        groups=session.groups,
        created=result.created,
        linked_by_email=result.linked_by_email,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    response: Response,
    rt: Optional[str] = Cookie(default=None),
    body: Optional[Dict[str, Any]] = Body(default=None),
    sessions: SessionManager = Depends(session_manager_dep),
) -> RefreshResponse:
    """Rotate the access token using a refresh token (cookie or body)."""
    refresh_token = rt or (body or {}).get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    new = sessions.refresh(refresh_token)
    if not new:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    _set_session_cookies(
        response,
        access=new.access_token,
        refresh=new.refresh_token,
        ttl=int(new.access_token_expires_at - new.issued_at),
    )
    return RefreshResponse(
        access_token=new.access_token,
        access_token_expires_at=new.access_token_expires_at,
        refresh_token=new.refresh_token,
        refresh_token_expires_at=new.refresh_token_expires_at,
        session_id=new.session_id,
    )


@router.post("/logout")
async def logout(
    response: Response,
    rt: Optional[str] = Cookie(default=None),
    body: Optional[Dict[str, Any]] = Body(default=None),
    sessions: SessionManager = Depends(session_manager_dep),
) -> Dict[str, Any]:
    """Revoke a refresh token (logout)."""
    refresh_token = rt or (body or {}).get("refresh_token")
    if refresh_token:
        sessions.revoke(refresh_token)
    _clear_session_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(
    at: Optional[str] = Cookie(default=None),
    sessions: SessionManager = Depends(session_manager_dep),
) -> Dict[str, Any]:
    """Return the current session info, or 401 if not logged in."""
    if not at:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = sessions.verify_access_token(at)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return {
        "user_id": claims.get("sub"),
        "email": claims.get("email"),
        "provider": claims.get("provider"),
        "role": claims.get("role"),
        "organisation_id": claims.get("organisation_id"),
        "expires_at": claims.get("exp"),
    }


# Convenience route: 302 the browser straight to the IdP. This is what
# the SSOButton on the login page hits by default.
@router.get("/{provider}/redirect")
async def redirect_to_idp(
    provider: str,
    relay_state: Optional[str] = Query(default=None),
    svc: SSOService = Depends(sso_service_dep),
) -> RedirectResponse:
    """Server-side 302 to the IdP. Use this for a "click to login" UX."""
    try:
        r = svc.begin_login(provider, relay_state=relay_state)
    except SSOLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider!r}")
    return RedirectResponse(r.url, status_code=302)


__all__ = ["router"]
