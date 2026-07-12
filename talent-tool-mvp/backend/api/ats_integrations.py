"""T1501 — ATS 集成 & 双向同步管理 API.

Endpoints:
  GET    /api/ats/integrations                  列表
  POST   /api/ats/integrations                  新建
  GET    /api/ats/integrations/{id}             详情
  PATCH  /api/ats/integrations/{id}             更新
  DELETE /api/ats/integrations/{id}             删除
  POST   /api/ats/integrations/{id}/sync-now    手动触发双向同步
  GET    /api/ats/integrations/{id}/sync-history 同步历史
  GET    /api/ats/integrations/{id}/conflicts   未解决冲突
  POST   /api/ats/integrations/{id}/conflicts/{cid}/resolve  冲突解决

实施时使用 Supabase 作为持久化 (attainable via api.deps.get_supabase_admin),
单测可直接注入 InMemoryStore。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.ats_sync import (
    ATSSyncEngine,
    CandidateRecord,
    ConflictStore,
    JobStore,
    SyncLogStore,
)

logger = logging.getLogger("waibao.ats_integrations")

router = APIRouter(prefix="/api/ats", tags=["ats-integrations"])


# ------------------------------------------------------------ schema
class IntegrationIn(BaseModel):
    provider: str = Field(..., pattern="^(greenhouse|lever|mock_ats|workday|icims)$")
    display_name: str = Field(..., min_length=1, max_length=128)
    api_key: str = Field(..., min_length=8)
    api_base_url: str | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict)


class IntegrationOut(BaseModel):
    id: str
    provider: str
    display_name: str
    active: bool
    last_synced_at: str | None
    last_status: str | None
    last_error: str | None
    api_base_url: str | None
    extra_config: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------ helpers
async def _engine_with_default_stores() -> ATSSyncEngine:
    """构造 Supabase 版本的 sync engine."""
    sb = get_supabase_admin()

    class _CandidatesAdapter:
        async def list_candidates(self, *, integration_id: str) -> list[CandidateRecord]:
            res = (
                sb.table("candidates")
                .select("id,email,name,phone,source,resume_url,external_id,tags,updated_at")
                .eq("integration_id", integration_id)
                .execute()
            )
            out: list[CandidateRecord] = []
            for row in res.data or []:
                out.append(
                    CandidateRecord(
                        id=str(row.get("id")),
                        email=row.get("email") or "",
                        name=row.get("name") or "",
                        phone=row.get("phone"),
                        source=row.get("source"),
                        resume_url=row.get("resume_url"),
                        external_id=row.get("external_id"),
                        tags=row.get("tags") or [],
                        updated_at=row.get("updated_at"),
                    )
                )
            return out

        async def upsert_candidate(self, rec: CandidateRecord, integration_id: str) -> CandidateRecord:
            payload = {
                "email": rec.email,
                "name": rec.name,
                "phone": rec.phone,
                "source": rec.source,
                "resume_url": rec.resume_url,
                "external_id": rec.external_id,
                "tags": rec.tags,
                "integration_id": integration_id,
            }
            res = sb.table("candidates").upsert(payload, on_conflict="email").execute()
            data = (res.data or [{}])[0]
            return CandidateRecord(
                id=str(data.get("id")),
                email=rec.email,
                name=rec.name,
                phone=rec.phone,
                source=rec.source,
                resume_url=rec.resume_url,
                external_id=rec.external_id,
                tags=rec.tags,
            )

    class _JobsAdapter:
        async def list_jobs(self, *, integration_id: str) -> list[dict]:
            res = sb.table("jobs").select("*").eq("integration_id", integration_id).execute()
            return res.data or []

        async def upsert_job(self, rec, integration_id: str):  # type: ignore[no-untyped-def]
            payload = {
                "title": rec.title,
                "description": rec.description,
                "location": rec.location,
                "department": rec.department,
                "status": rec.status,
                "external_id": rec.external_id,
                "url": rec.url,
                "integration_id": integration_id,
            }
            res = sb.table("jobs").upsert(payload, on_conflict="integration_id,external_id").execute()
            return rec

    class _SyncLogAdapter:
        async def start_log(
            self,
            integration_id: str,
            sync_type: str,
            direction: str,
            triggered_by: str,
        ) -> str:
            res = (
                sb.table("ats_sync_log")
                .insert(
                    {
                        "integration_id": integration_id,
                        "sync_type": sync_type,
                        "direction": direction,
                        "triggered_by": triggered_by,
                        "status": "in_progress",
                        "started_at": datetime.utcnow().isoformat(),
                    }
                )
                .execute()
            )
            return str((res.data or [{}])[0].get("id"))

        async def finish_log(
            self,
            log_id: str,
            *,
            status: str,
            total: int,
            succeeded: int,
            failed: int,
            conflicts: int,
            diff: list[dict[str, Any]],
            error: str | None = None,
        ) -> None:
            sb.table("ats_sync_log").update(
                {
                    "status": status,
                    "finished_at": datetime.utcnow().isoformat(),
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "conflicts": conflicts,
                    "diff": diff,
                    "error": error,
                }
            ).eq("id", log_id).execute()

    class _ConflictAdapter:
        async def record(
            self,
            integration_id: str,
            *,
            entity_type: str,
            sync_log_id: str,
            local_id: str | None,
            external_id: str,
            field_diffs: list[dict[str, Any]],
            resolution: str,
        ) -> None:
            sb.table("ats_conflicts").insert(
                {
                    "integration_id": integration_id,
                    "sync_log_id": sync_log_id,
                    "entity_type": entity_type,
                    "local_id": local_id,
                    "external_id": external_id,
                    "field_diffs": field_diffs,
                    "resolution": resolution,
                }
            ).execute()

    return ATSSyncEngine(
        candidates=_CandidatesAdapter(),
        jobs=_JobsAdapter(),  # type: ignore[arg-type]
        sync_log=_SyncLogAdapter(),
        conflicts=_ConflictAdapter(),
    )


# ------------------------------------------------------------ endpoints
@router.get("/integrations", response_model=list[IntegrationOut])
async def list_integrations(_: CurrentUser = Depends(get_current_user)) -> list[IntegrationOut]:
    sb = get_supabase_admin()
    res = sb.table("ats_integrations").select("*").order("created_at", desc=True).execute()
    return [
        IntegrationOut(
            id=str(r["id"]),
            provider=r["provider"],
            display_name=r["display_name"],
            active=r.get("active", True),
            last_synced_at=r.get("last_synced_at"),
            last_status=r.get("last_status"),
            last_error=r.get("last_error"),
            api_base_url=r.get("api_base_url"),
            extra_config=r.get("extra_config") or {},
        )
        for r in (res.data or [])
    ]


@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: IntegrationIn,
    user: CurrentUser = Depends(get_current_user),
) -> IntegrationOut:
    sb = get_supabase_admin()
    res = (
        sb.table("ats_integrations")
        .insert(
            {
                "provider": body.provider,
                "display_name": body.display_name,
                "api_key_secret": body.api_key,
                "api_base_url": body.api_base_url,
                "extra_config": body.extra_config,
                "created_by": user.id if hasattr(user, "id") else None,
            }
        )
        .execute()
    )
    row = (res.data or [{}])[0]
    return IntegrationOut(
        id=str(row["id"]),
        provider=row["provider"],
        display_name=row["display_name"],
        active=row.get("active", True),
        last_synced_at=row.get("last_synced_at"),
        last_status=row.get("last_status"),
        last_error=row.get("last_error"),
        api_base_url=row.get("api_base_url"),
        extra_config=row.get("extra_config") or {},
    )


@router.get("/integrations/{integration_id}", response_model=IntegrationOut)
async def get_integration(integration_id: str, _: CurrentUser = Depends(get_current_user)) -> IntegrationOut:
    sb = get_supabase_admin()
    res = sb.table("ats_integrations").select("*").eq("id", integration_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="integration not found")
    r = res.data
    return IntegrationOut(
        id=str(r["id"]),
        provider=r["provider"],
        display_name=r["display_name"],
        active=r.get("active", True),
        last_synced_at=r.get("last_synced_at"),
        last_status=r.get("last_status"),
        last_error=r.get("last_error"),
        api_base_url=r.get("api_base_url"),
        extra_config=r.get("extra_config") or {},
    )


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(integration_id: str, _: CurrentUser = Depends(get_current_user)) -> None:
    sb = get_supabase_admin()
    sb.table("ats_integrations").delete().eq("id", integration_id).execute()


@router.post("/integrations/{integration_id}/sync-now")
async def sync_now(integration_id: str, _: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    sb = get_supabase_admin()
    row = sb.table("ats_integrations").select("*").eq("id", integration_id).single().execute().data
    if not row:
        raise HTTPException(status_code=404, detail="integration not found")
    from services.ats_sync import make_provider

    provider = make_provider(
        row["provider"],
        api_key=row.get("api_key_secret") or "",
        base_url=row.get("api_base_url"),
    )
    engine = await _engine_with_default_stores()
    cand_result = await engine.pull_candidates(
        integration_id=integration_id,
        provider=provider,
        triggered_by="manual",
    )
    job_result = await engine.pull_jobs(
        integration_id=integration_id,
        provider=provider,
        triggered_by="manual",
    )
    # 写回状态
    sb.table("ats_integrations").update(
        {
            "last_synced_at": datetime.utcnow().isoformat(),
            "last_status": "ok" if cand_result.status == "ok" and job_result.status == "ok" else "partial",
            "last_error": cand_result.error or job_result.error,
        }
    ).eq("id", integration_id).execute()
    return {
        "status": "triggered",
        "candidates": {
            "status": cand_result.status,
            "succeeded": cand_result.succeeded,
            "failed": cand_result.failed,
            "conflicts": cand_result.conflicts,
        },
        "jobs": {
            "status": job_result.status,
            "succeeded": job_result.succeeded,
            "failed": job_result.failed,
            "conflicts": job_result.conflicts,
        },
    }


@router.get("/integrations/{integration_id}/sync-history")
async def sync_history(
    integration_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    _: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()
    res = (
        sb.table("ats_sync_log")
        .select("*")
        .eq("integration_id", integration_id)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


@router.get("/integrations/{integration_id}/conflicts")
async def list_conflicts(
    integration_id: str,
    resolved: bool | None = None,
    _: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()
    q = sb.table("ats_conflicts").select("*").eq("integration_id", integration_id)
    if resolved is None:
        # 默认仅未解决
        q = q.is_("resolution", "null")
    elif resolved:
        q = q.not_.is_("resolution", "null")
    res = q.order("created_at", desc=True).execute()
    return res.data or []


class ConflictResolution(BaseModel):
    resolution: str = Field(..., pattern="^(local_wins|remote_wins|auto_merged)$")

    @field_validator("resolution")
    @classmethod
    def _v(cls, v: str) -> str:
        return v


@router.post("/integrations/{integration_id}/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    integration_id: str,
    conflict_id: str,
    body: ConflictResolution,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_supabase_admin()
    res = (
        sb.table("ats_conflicts")
        .update(
            {
                "resolution": body.resolution,
                "resolved_by": getattr(user, "id", None),
                "resolved_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", conflict_id)
        .eq("integration_id", integration_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="conflict not found")
    return {"status": "resolved", "resolution": body.resolution, "conflict_id": conflict_id}
