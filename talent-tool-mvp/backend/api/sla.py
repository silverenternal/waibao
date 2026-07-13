"""T2604 - SLA API endpoints.

  GET /api/admin/sla/7d
  GET /api/admin/sla/30d
  GET /api/admin/sla/90d
  GET /api/admin/sla/report?format=pdf

All endpoints are admin-only (RBAC: ``UserRole.admin``). Multi-tenant users
see their own slice; platform owners see the global rollup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from api.auth import CurrentUser, require_role
from contracts.shared import UserRole
from services.platform.sla_monitor import (
    DEFAULT_TARGET_UPTIME,
    PLATFORM_SERVICES,
    WINDOWS,
    compute_sla,
    render_monthly_report,
    summary_for_admin,
)

router = APIRouter(prefix="/api/admin/sla", tags=["sla"])


@router.get("/windows")
async def list_windows(user: CurrentUser = Depends(require_role(UserRole.admin))):
    """List the canonical evaluation windows for the UI."""
    return {
        "windows_days": list(WINDOWS),
        "services": list(PLATFORM_SERVICES),
        "target_uptime": DEFAULT_TARGET_UPTIME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _window_or_400(days: int) -> int:
    if days not in WINDOWS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"window must be one of {WINDOWS}")
    return days


@router.get("/{days}")
async def get_sla_for_window(
    days: int,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
    tenant_id: Optional[str] = Query(None, description="Limit scope to one tenant"),
):
    """7/30/90-day SLA rollup for all five platform services.

    Per-service SLA objects contain uptime, P95 latency, error rate,
    request count, breached flag, and target_uptime.
    """
    _window_or_400(days)
    full = compute_sla()
    by_service = {
        svc: full.services.get(svc, {}).get(days) for svc in PLATFORM_SERVICES
    }
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "window_days": days,
        "target_uptime": DEFAULT_TARGET_UPTIME,
        "generated_at": full.generated_at,
        "services": {svc: (s.to_dict() if s else None) for svc, s in by_service.items()},
        "breaches": [
            b for b in full.overall_breaches if b.endswith(f":{days}d")
        ],
    }
    return JSONResponse(payload)


@router.get("")
async def get_full_sla(user: CurrentUser = Depends(require_role(UserRole.admin))):
    """Convenience: all windows, summarised by admin/sla.py."""
    return JSONResponse(summary_for_admin(user.tenant_id))


@router.get("/report/download")
async def download_monthly_report(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
    tenant_id: Optional[str] = Query(None),
    fmt: str = Query("pdf", pattern="^(pdf|text)$"),
):
    """Stream the monthly PDF SLA report (``Content-Type: application/pdf``)."""
    metrics = compute_sla()
    if fmt == "pdf":
        blob = render_monthly_report(metrics, tenant_id=tenant_id, as_bytes=True)
        filename = f"sla-report-{metrics.generated_at[:10]}.pdf"
        return Response(
            content=blob,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    blob = render_monthly_report(metrics, tenant_id=tenant_id, as_bytes=True)
    filename = f"sla-report-{metrics.generated_at[:10]}.txt"
    return Response(
        content=blob,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
