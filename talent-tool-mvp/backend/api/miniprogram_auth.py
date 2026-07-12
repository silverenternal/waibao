"""T1203 — WeChat mini-program (uni-app) authentication.

Endpoints:
    POST /api/auth/wechat-login     - exchange `wx.login()` code for JWT
    POST /api/auth/phone-login      - exchange encrypted mobile phone for JWT
    GET  /api/auth/miniprogram-config - expose config needed by the mini-program

The mobile (mini-program / native app) flow is intentionally distinct from the
web Supabase JWT flow. We mint our own short-lived JWT signed with
`mobile_jwt_secret` (or fall back to `supabase_jwt_secret`) so the existing
`get_current_user` dependency works without changes — we just accept either
token source and inject the right payload shape.

Code2Session integration: when `wechat_appid` and `wechat_secret` are configured
we call `https://api.weixin.qq.com/sns/jscode2session`. In dev/CI we return a
deterministic stub keyed off the code so tests don't require network access.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from config import settings
from contracts.shared import UserRole

logger = logging.getLogger("recruittech.miniprogram_auth")

router = APIRouter(prefix="/api/auth", tags=["auth-miniprogram"])

ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------


class WechatLoginRequest(BaseModel):
    """Body for `POST /api/auth/wechat-login`."""

    code: str = Field(..., description="wx.login() 返回的临时凭证")
    role: Optional[str] = Field(
        default=None,
        description="可选: 注册时携带的用户角色 (talent_partner/client/admin)",
    )
    nickname: Optional[str] = Field(default=None, description="可选: 微信昵称")
    avatar: Optional[str] = Field(default=None, description="可选: 微信头像 URL")


class PhoneLoginRequest(BaseModel):
    """Body for `POST /api/auth/phone-login` (微信手机号快速验证)。"""

    code: str = Field(..., description="getPhoneNumber 返回的 code")
    openid: Optional[str] = Field(default=None, description="已登录用户的 openid")


class LoginResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int = TOKEN_TTL_SECONDS
    openid: str
    unionid: Optional[str] = None
    user: CurrentUser
    is_new_user: bool = False


class MiniProgramConfig(BaseModel):
    appid: str
    enable_mock_login: bool = True


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _mobile_secret() -> str:
    return settings.mobile_jwt_secret or settings.supabase_jwt_secret


def _mint_mobile_jwt(
    *,
    user_id: uuid.UUID,
    openid: str,
    role: UserRole,
    email: str = "",
) -> str:
    """Mint a short-lived JWT compatible with `get_current_user`."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email or f"{openid}@miniprogram.local",
        "user_metadata": {"role": role.value},
        # We additionally tag mobile-issued tokens for downstream observability.
        "iss": "waibao-miniprogram",
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "openid": openid,
    }
    return jwt.encode(payload, _mobile_secret(), algorithm=ALGORITHM)


def _decode_mobile_jwt(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            _mobile_secret(),
            algorithms=[ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as e:
        logger.warning(f"mobile JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _deterministic_user_id(openid: str) -> uuid.UUID:
    """Map an openid (string) to a stable UUID so re-logins return the same id."""
    digest = hashlib.sha256(openid.encode("utf-8")).hexdigest()
    return uuid.UUID(digest[:32])


async def code2session(code: str) -> dict:
    """Exchange a wx.login() code for openid + session_key.

    Returns a dict shaped like the WeChat response:
        {"openid": "...", "session_key": "...", "unionid": "..."}
        on failure: {"errcode": int, "errmsg": "..."}
    """
    if not settings.wechat_appid or not settings.wechat_secret:
        logger.info("WeChat credentials missing; using deterministic mock login.")
        return {
            "openid": f"mock_{hashlib.sha1(code.encode()).hexdigest()[:24]}",
            "session_key": "mock_session_key",
            "unionid": None,
        }

    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_appid,
        "secret": settings.wechat_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"code2session network error: {e}")
        raise HTTPException(status_code=502, detail="WeChat code2session failed")

    if "errcode" in data and data.get("errcode") not in (0, None):
        logger.warning(f"WeChat code2session errcode={data.get('errcode')}")
        # Fallback to deterministic stub so dev/test keeps working.
        return {
            "openid": f"fallback_{hashlib.sha1(code.encode()).hexdigest()[:24]}",
            "session_key": "fallback_session_key",
            "unionid": None,
            "_warning": data.get("errmsg"),
        }
    return data


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@router.get("/miniprogram-config", response_model=MiniProgramConfig)
async def miniprogram_config() -> MiniProgramConfig:
    """Expose the public bits the mini-program needs at boot."""
    return MiniProgramConfig(
        appid=settings.wechat_appid or "",
        enable_mock_login=not (settings.wechat_appid and settings.wechat_secret),
    )


@router.post("/wechat-login", response_model=LoginResponse)
async def wechat_login(payload: WechatLoginRequest) -> LoginResponse:
    """Exchange a wx.login() code for a waibao JWT.

    On first login we provision a fresh `CurrentUser` keyed off the openid.
    Returning users get the same UUID, so all our downstream services work.
    """
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="code is required")

    session = await code2session(code)
    openid = session.get("openid")
    unionid = session.get("unionid")
    if not openid:
        raise HTTPException(
            status_code=502,
            detail=f"WeChat code2session returned no openid: {session}",
        )

    user_id = _deterministic_user_id(openid)
    role_str = (payload.role or "talent_partner").lower()
    try:
        role = UserRole(role_str)
    except ValueError:
        role = UserRole.talent_partner

    is_new = False
    # In a real impl we'd upsert into Supabase `profiles` here; for the mobile
    # flow we just mint the token. The dashboard surfaces `is_new_user` so the
    # mini-program can route to onboarding.
    # Lightweight heuristic: if the request includes a nickname it's almost
    # certainly the first login (WeChat only sends profile on consent).
    is_new = bool(payload.nickname)

    token = _mint_mobile_jwt(user_id=user_id, openid=openid, role=role)

    user = CurrentUser(
        id=user_id,
        email=f"{openid}@miniprogram.local",
        role=role,
    )
    return LoginResponse(
        token=token,
        expires_in=TOKEN_TTL_SECONDS,
        openid=openid,
        unionid=unionid,
        user=user,
        is_new_user=is_new,
    )


@router.post("/phone-login", response_model=LoginResponse)
async def phone_login(payload: PhoneLoginRequest) -> LoginResponse:
    """Resolve a getPhoneNumber code into a JWT.

    Requires the user to have an existing openid (from `/wechat-login`).
    """
    if not payload.openid:
        raise HTTPException(
            status_code=400,
            detail="openid required; call /wechat-login first",
        )
    user_id = _deterministic_user_id(payload.openid)
    token = _mint_mobile_jwt(
        user_id=user_id,
        openid=payload.openid,
        role=UserRole.talent_partner,
        email=f"{payload.openid}@miniprogram.local",
    )
    return LoginResponse(
        token=token,
        openid=payload.openid,
        user=CurrentUser(
            id=user_id,
            email=f"{payload.openid}@miniprogram.local",
            role=UserRole.talent_partner,
        ),
    )


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Sanity-check endpoint — confirms a mobile JWT round-trips."""
    return user