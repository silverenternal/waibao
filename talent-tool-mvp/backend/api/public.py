"""公开 API v1 (T803).

第三方开发者用 API Key (Bearer) 访问.

Endpoints:
  POST /api/public/v1/candidates          scope: candidates:write
  GET  /api/public/v1/candidates/{id}     scope: candidates:read
  GET  /api/public/v1/roles               scope: roles:read
  POST /api/public/v1/matches             scope: matches:write
  POST /api/public/v1/tickets             scope: tickets:write

所有端点:
- API Key 验证 + 速率限制 (RateLimitGuard)
- scope 检查
- 写审计到 api_key_usage
- 业务失败不影响计费/审计

错误:
  401 missing_key / invalid_key
  403 insufficient_scope
  429 rate_limited
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from pydantic import BaseModel, Field

from services.api_key import (
    RateLimitGuard,
    VerifiedKey as _VerifiedKey,
    check_scope,
    verify_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/v1", tags=["public-api"])

# 模块级 rate guard (注入 Redis 后可在 main 启动时替换)
_rate_guard = RateLimitGuard()


def set_rate_limiter(guard: RateLimitGuard) -> None:
    """测试/启动时注入. main.py 中可绑定到 Redis."""
    global _rate_guard
    _rate_guard = guard


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CandidateCreateIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    seniority: str | None = None
    skills: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    summary: str | None = None


class CandidateOut(BaseModel):
    id: str
    full_name: str
    email: str | None = None
    seniority: str | None = None
    skills: list[str] = Field(default_factory=list)
    created_at: str


class RoleOut(BaseModel):
    id: str
    title: str
    seniority: str | None = None
    location: str | None = None
    status: str | None = None
    created_at: str | None = None


class MatchCreateIn(BaseModel):
    role_id: str
    candidate_id: str
    note: str | None = None


class MatchOut(BaseModel):
    id: str
    role_id: str
    candidate_id: str
    status: str
    created_at: str


class TicketCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    priority: str = Field(default="P3")
    department: str | None = None


class TicketOut(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    created_at: str


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _resolve_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> _VerifiedKey:
    """API Key 认证 + 速率限制依赖."""
    # 1. 取明文
    plain = x_api_key or _resolve_bearer(authorization)
    if not plain:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_api_key",
        )

    # 2. 查 DB (在 endpoint 内部按 hash 检索;此处只解析明文)
    #    我们采用 lazy import supabase 避免循环
    from api.deps import get_supabase_admin

    sb = get_supabase_admin()
    # 先按 prefix 取小集合 (避免全表扫). prefix = 前 12 字符
    if len(plain) < 12:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    prefix = plain[:12]
    res = (
        sb.table("api_keys")
        .select("*")
        .eq("key_prefix", prefix)
        .is_("revoked_at", "null")
        .execute()
    )
    rows = res.data or []
    # 兜底:全表扫 (无 prefix index 时退化)
    if not rows:
        res2 = (
            sb.table("api_keys")
            .select("*")
            .is_("revoked_at", "null")
            .execute()
        )
        rows = [r for r in (res2.data or []) if r.get("key_prefix") == prefix]

    verified = None
    for r in rows:
        v = verify_key(plain, r)
        if v:
            verified = v
            break
    if not verified:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    # 3. 速率限制
    ok = await _rate_guard.allow(verified.id, verified.rate_limit_per_min)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="rate_limit_exceeded",
            headers={"Retry-After": "60"},
        )

    # 把 endpoint 路径写回 request state 以便审计
    request.state.api_key = verified
    return verified


def require_scope(scope: str) -> Callable[[_VerifiedKey], _VerifiedKey]:
    """scope 检查依赖工厂."""

    def _checker(v: _VerifiedKey = Depends(require_api_key)) -> _VerifiedKey:
        if not check_scope(v, scope):
            raise HTTPException(
                status_code=403,
                detail=f"insufficient_scope:{scope}",
            )
        return v

    return _checker


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


def _audit(
    request: Request,
    verified: _VerifiedKey,
    status_code: int,
    start: float,
) -> None:
    """异步审计落库. 失败不抛."""
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        endpoint = request.url.path
        sb.table("api_key_usage").insert(
            {
                "id": str(uuid.uuid4()),
                "api_key_id": verified.id,
                "endpoint": endpoint,
                "status_code": int(status_code),
                "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).execute()
        # 顺手更新 last_used_at (best-effort)
        sb.table("api_keys").update(
            {"last_used_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", verified.id).execute()
    except Exception:  # noqa: BLE001
        logger.exception("public_api.audit_failed key=%s", verified.id)
    finally:
        dur_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "public_api key=%s endpoint=%s status=%s dur_ms=%s",
            verified.id, request.url.path, status_code, dur_ms,
        )


def _audit_wrap(
    request: Request, verified: _VerifiedKey, start: float
) -> None:
    """外层 endpoint 异常时统一审计 500."""
    _audit(request, verified, 500, start)


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@router.post(
    "/candidates",
    response_model=CandidateOut,
    status_code=201,
    summary="Create candidate (scope: candidates:write)",
)
async def create_candidate(
    body: CandidateCreateIn,
    request: Request,
    verified: _VerifiedKey = Depends(require_scope("candidates:write")),
):
    start = time.monotonic()
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        record = {
            "id": str(uuid.uuid4()),
            "organisation_id": verified.organisation_id,
            "full_name": body.full_name,
            "email": body.email,
            "phone": body.phone,
            "location": body.location,
            "seniority": body.seniority,
            "skills": [{"name": s} for s in (body.skills or [])],
            "years_experience": body.years_experience,
            "summary": body.summary,
            "source": "public_api",
        }
        res = sb.table("candidates").insert(record).execute()
        if not res.data:
            raise HTTPException(500, "create_failed")
        row = res.data[0]
        out = CandidateOut(
            id=row["id"],
            full_name=row.get("full_name") or body.full_name,
            email=row.get("email"),
            seniority=row.get("seniority"),
            skills=[s.get("name") if isinstance(s, dict) else s for s in (row.get("skills") or [])],
            created_at=row.get("created_at") or datetime.now(tz=timezone.utc).isoformat(),
        )
        _audit(request, verified, 201, start)
        return out
    except HTTPException as e:
        _audit(request, verified, e.status_code, start)
        raise
    except Exception:
        _audit_wrap(request, verified, start)
        raise


@router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateOut,
    summary="Get candidate by id (scope: candidates:read)",
)
async def get_candidate(
    candidate_id: str = Path(..., min_length=1),
    request: Request = None,  # type: ignore[assignment]
    verified: _VerifiedKey = Depends(require_scope("candidates:read")),
):
    start = time.monotonic()
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        res = (
            sb.table("candidates")
            .select("*")
            .eq("id", candidate_id)
            .eq("organisation_id", verified.organisation_id)
            .single()
            .execute()
        )
        if not res.data:
            _audit(request, verified, 404, start)
            raise HTTPException(404, "candidate_not_found")
        row = res.data
        out = CandidateOut(
            id=row["id"],
            full_name=row.get("full_name", ""),
            email=row.get("email"),
            seniority=row.get("seniority"),
            skills=[
                s.get("name") if isinstance(s, dict) else s
                for s in (row.get("skills") or [])
            ],
            created_at=row.get("created_at")
            or datetime.now(tz=timezone.utc).isoformat(),
        )
        _audit(request, verified, 200, start)
        return out
    except HTTPException as e:
        _audit(request, verified, e.status_code, start)
        raise


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@router.get(
    "/roles",
    response_model=list[RoleOut],
    summary="List roles (scope: roles:read)",
)
async def list_roles(
    request: Request,
    limit: int = 50,
    verified: _VerifiedKey = Depends(require_scope("roles:read")),
):
    start = time.monotonic()
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        res = (
            sb.table("roles")
            .select("*")
            .eq("organisation_id", verified.organisation_id)
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 200))
            .execute()
        )
        items = [
            RoleOut(
                id=r["id"],
                title=r.get("title") or "",
                seniority=r.get("seniority"),
                location=r.get("location"),
                status=r.get("status"),
                created_at=r.get("created_at"),
            )
            for r in (res.data or [])
        ]
        _audit(request, verified, 200, start)
        return items
    except HTTPException as e:
        _audit(request, verified, e.status_code, start)
        raise


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


@router.post(
    "/matches",
    response_model=MatchOut,
    status_code=201,
    summary="Propose a match (scope: matches:write)",
)
async def propose_match(
    body: MatchCreateIn,
    request: Request,
    verified: _VerifiedKey = Depends(require_scope("matches:write")),
):
    start = time.monotonic()
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        record = {
            "id": str(uuid.uuid4()),
            "organisation_id": verified.organisation_id,
            "role_id": body.role_id,
            "candidate_id": body.candidate_id,
            "status": "proposed",
            "source": "public_api",
            "note": body.note or "",
        }
        res = sb.table("matches").insert(record).execute()
        if not res.data:
            raise HTTPException(500, "create_failed")
        row = res.data[0]
        out = MatchOut(
            id=row["id"],
            role_id=row.get("role_id") or body.role_id,
            candidate_id=row.get("candidate_id") or body.candidate_id,
            status=row.get("status") or "proposed",
            created_at=row.get("created_at")
            or datetime.now(tz=timezone.utc).isoformat(),
        )
        _audit(request, verified, 201, start)
        return out
    except HTTPException as e:
        _audit(request, verified, e.status_code, start)
        raise


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@router.post(
    "/tickets",
    response_model=TicketOut,
    status_code=201,
    summary="Create support ticket (scope: tickets:write)",
)
async def create_ticket(
    body: TicketCreateIn,
    request: Request,
    verified: _VerifiedKey = Depends(require_scope("tickets:write")),
):
    start = time.monotonic()
    try:
        from api.deps import get_supabase_admin

        sb = get_supabase_admin()
        record = {
            "id": str(uuid.uuid4()),
            "organisation_id": verified.organisation_id,
            "title": body.title,
            "description": body.description,
            "priority": body.priority,
            "department": body.department or "support",
            "status": "open",
            "source": "public_api",
            "created_by": "api_key",
        }
        res = sb.table("tickets").insert(record).execute()
        if not res.data:
            raise HTTPException(500, "create_failed")
        row = res.data[0]
        out = TicketOut(
            id=row["id"],
            title=row.get("title") or body.title,
            status=row.get("status") or "open",
            priority=row.get("priority") or body.priority,
            created_at=row.get("created_at")
            or datetime.now(tz=timezone.utc).isoformat(),
        )
        _audit(request, verified, 201, start)
        return out
    except HTTPException as e:
        _audit(request, verified, e.status_code, start)
        raise
