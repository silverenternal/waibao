"""T1004 - Admin audit endpoints."""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.auth import CurrentUser, get_current_user, require_admin
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.admin_audit")
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("")
async def list_audit(
    user_id: Optional[str] = Query(None, description="按 PII subject user_id 过滤"),
    actor_user_id: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    since_days: int = Query(7, ge=1, le=365),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """列出审计日志 (admin-only)."""
    sb = get_supabase_admin()
    try:
        q = sb.table("audit_log").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        if actor_user_id:
            q = q.eq("actor_user_id", actor_user_id)
        if resource_type:
            q = q.eq("resource_type", resource_type)
        if action:
            q = q.eq("action", action)
        # since filter 通过 metadata 不可行,用 created_at
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        q = q.gte("created_at", since)
        q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = q.execute()
        return {"data": result.data or [], "limit": limit, "offset": offset}
    except Exception as exc:
        logger.exception("admin_audit.list_failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export")
async def export_audit(
    user_id: Optional[str] = Query(None),
    since_days: int = Query(30, ge=1, le=365),
):
    """导出审计日志为 CSV."""
    sb = get_supabase_admin()
    try:
        q = sb.table("audit_log").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        q = q.gte("created_at", since)
        result = q.order("created_at", desc=True).execute()
        rows = result.data or []

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "created_at",
                "actor_user_id",
                "user_id",
                "action",
                "resource_type",
                "resource_id",
                "ip_address",
                "user_agent",
                "metadata",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.get("id", ""),
                    r.get("created_at", ""),
                    r.get("actor_user_id", ""),
                    r.get("user_id", ""),
                    r.get("action", ""),
                    r.get("resource_type", ""),
                    r.get("resource_id", ""),
                    r.get("ip_address", ""),
                    r.get("user_agent", ""),
                    json_safe(r.get("metadata") or {}),
                ]
            )
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
        )
    except Exception as exc:
        logger.exception("admin_audit.export_failed")
        raise HTTPException(status_code=500, detail=str(exc))


def json_safe(obj):
    import json

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)