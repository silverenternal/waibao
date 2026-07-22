import logging
from uuid import UUID

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings
from contracts.shared import UserRole

logger = logging.getLogger("recruittech.auth")

# Supabase JWTs are signed with the project's JWT secret (not the anon key).
# Set SUPABASE_JWT_SECRET in .env to match your Supabase project's JWT secret.
# Default matches the standard local Supabase dev JWT secret.
SUPABASE_JWT_SECRET = settings.supabase_jwt_secret
ALGORITHM = "HS256"

# Reuse the SSO/session block-list of known weak JWT secrets so the web auth
# path refuses to verify tokens signed with the well-known Supabase dev secret.
# The startup gate (compliance.security_startup) already aborts on a weak
# secret in strict mode; this is the defence-in-depth request-time check so a
# misconfigured (non-strict) deploy can still never accept a forged token.
try:
    from services.auth.session import WEAK_JWT_SECRETS as _WEAK_JWT_SECRETS
except Exception:  # pragma: no cover - import guard
    _WEAK_JWT_SECRETS = frozenset()


def _resolve_web_jwt_secret() -> str:
    """Return the JWT secret, refusing the well-known weak placeholders.

    If the configured secret is on the weak block-list (the literal Supabase
    dev default) we log loudly and raise 503 — accepting it would let any
    attacker forge an admin token. The local/CI default is intentionally kept
    importable so unit tests that override ``get_current_user`` still run.
    """
    secret = SUPABASE_JWT_SECRET or settings.mobile_jwt_secret
    if not secret or secret in _WEAK_JWT_SECRETS:
        logger.error(
            "JWT secret is missing or on the weak-secret block-list — refusing "
            "to verify tokens. Set SUPABASE_JWT_SECRET to a random 32+ char "
            "string (T5014 fail-fast)."
        )
        raise HTTPException(
            status_code=503,
            detail="Authentication is not properly configured (weak JWT secret).",
        )
    return secret


security = HTTPBearer()


class CurrentUser(BaseModel):
    """Represents the authenticated user extracted from JWT."""

    id: UUID
    email: str
    role: UserRole


def decode_supabase_jwt(token: str) -> dict:
    """Decode and validate a Supabase JWT token.

    Supabase JWTs contain:
    - sub: user UUID
    - email: user email
    - user_metadata: { role: "talent_partner" | "client" | "admin" }
    """
    try:
        payload = jwt.decode(
            token,
            _resolve_web_jwt_secret(),
            algorithms=[ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
        )


def decode_mobile_jwt(token: str) -> dict:
    """Decode a JWT minted by the mini-program (mobile) login flow.

    Tokens are signed with `mobile_jwt_secret` if configured, otherwise fall
    back to `supabase_jwt_secret` for dev. Issued by
    `api.miniprogram_auth._mint_mobile_jwt`.
    """
    secret = settings.mobile_jwt_secret or _resolve_web_jwt_secret()
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as e:
        logger.warning(f"mobile JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _payload_to_user(payload: dict) -> "CurrentUser":
    user_id = payload.get("sub")
    email = payload.get("email", "")
    user_metadata = payload.get("user_metadata", {}) or {}
    role_str = user_metadata.get("role", "talent_partner")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
    try:
        role = UserRole(role_str)
    except ValueError:
        raise HTTPException(status_code=401, detail=f"Invalid role: {role_str}")
    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        # Malformed sub claim — never surface a 500; reject the token.
        raise HTTPException(
            status_code=401, detail="Invalid token: malformed user ID"
        )
    return CurrentUser(id=user_uuid, email=email, role=role)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> CurrentUser:
    """FastAPI dependency: extract and validate current user from JWT.

    Accepts both Supabase web JWTs and mini-program (mobile) JWTs. Mobile
    tokens are tagged with `iss=waibao-miniprogram` and signed with
    `mobile_jwt_secret` (falling back to the Supabase secret in dev).
    """
    token = credentials.credentials

    # 1) Mobile tokens are explicitly tagged with `iss=waibao-miniprogram`.
    #    Only an explicit tag routes to the mobile decoder — never fall back
    #    to mobile based on token shape alone (that's how web/mobile paths
    #    got crossed previously and broke the test suite).
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        unverified = {}

    if unverified.get("iss") == "waibao-miniprogram":
        payload = decode_mobile_jwt(token)
    else:
        payload = decode_supabase_jwt(token)

    return _payload_to_user(payload)


def require_role(*allowed_roles: UserRole):
    """Dependency factory: restrict endpoint to specific roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            user: CurrentUser = Depends(require_role(UserRole.admin))
        ):
            ...

    Multiple roles:
        @router.get("/partners-and-admins")
        async def endpoint(
            user: CurrentUser = Depends(require_role(UserRole.talent_partner, UserRole.admin))
        ):
            ...
    """

    async def role_checker(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {', '.join(r.value for r in allowed_roles)}",
            )
        return user

    return role_checker


# Convenience dependencies for common role combinations.
# v11.3: boss / department_head 是企业方 (client 侧) 细分角色 (甲方合同 4 角色),
# 享有 client 同等权限 — 加入企业方依赖, 否则老板/部门负责人无法发起沟通等.
require_admin = require_role(UserRole.admin)
require_talent_partner = require_role(UserRole.talent_partner, UserRole.admin)
require_client = require_role(
    UserRole.client, UserRole.boss, UserRole.department_head, UserRole.admin
)
require_any_authenticated = require_role(
    UserRole.talent_partner, UserRole.client, UserRole.boss,
    UserRole.department_head, UserRole.admin,
)
