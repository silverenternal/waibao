"""v11.2 T6303 — Identity verification API (mount under /api/identity).

Endpoints:
    POST /api/identity/upload
        body: {doc_type: 'id_card'|'education'|'resume', file_url|file_id}
        -> submits the doc for AI extraction, returns IdentityStatus (display
           labels included). Auth: current user must be talent role.
    GET  /api/identity/status              -> current user IdentityStatus
    GET  /api/identity/profile             -> latest structured profile (editable)
    PUT  /api/identity/profile             -> update profile + save a NEW version
                                              (returns version_no)
    GET  /api/identity/profile/versions    -> [{version_no, created_at}, ...]
    GET  /api/identity/profile/versions/{version_no} -> that snapshot

Auth wiring mirrors api/uploads.py: a placeholder ``get_current_user`` dependency
is defined at module load (so simply importing this module never triggers the
``jose`` import). Production wiring (main.py) overrides it via
``app.dependency_overrides`` with ``api.auth.get_current_user``. Tests do the
same with a fake user.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.identity import IdentityStatus, get_identity_service
from services.identity.verification import DISPLAY_MAP, DOC_TYPES

logger = logging.getLogger("recruittech.api.identity")
router = APIRouter()

if TYPE_CHECKING:  # pragma: no cover — type hints only
    from api.auth import CurrentUser, get_current_user  # noqa: F401


# ---------------------------------------------------------------------------
# Auth dependency (overridable — see module docstring)
# ---------------------------------------------------------------------------


async def get_current_user():  # pragma: no cover — overridden in production & tests
    """Placeholder auth dep. Production/tests override via dependency_overrides."""
    raise HTTPException(status_code=401, detail="auth not wired — set dependency_overrides")


def _ensure_talent(user) -> str:
    """Reject any non-talent (talent_partner) user. Returns the user id str."""
    role = getattr(user, "role", None)
    role_val = getattr(role, "value", role)
    # UserRole.talent_partner == "talent_partner". Admins may act on behalf.
    if role_val not in ("talent_partner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="只有人才 (talent) 角色可以上传身份验证资料",
        )
    return str(getattr(user, "id", user))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class UploadRequest(BaseModel):
    doc_type: str = Field(..., description="'id_card' | 'education' | 'resume'")
    file_url: str | None = Field(default=None, description="signed URL of the uploaded file")
    file_id: str | None = Field(default=None, description="storage object id / path (fallback)")


class ProfileUpdateRequest(BaseModel):
    profile: dict[str, Any] = Field(..., description="editable structured profile snapshot")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=None)
async def upload_document(
    body: UploadRequest,
    user=Depends(get_current_user),
):
    """Submit a document (身份证 / 学历证明 / 简历) for AI extraction.

    The file is expected to already be in storage (see api/uploads.py for the
    upload-then-submit pattern); this endpoint takes the resulting URL/id and
    runs verification. Returns the rolled-up IdentityStatus with display labels.
    """
    user_id = _ensure_talent(user)
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type 必须是 {DOC_TYPES} 之一",
        )
    payload = body.file_url or body.file_id
    svc = get_identity_service()
    try:
        status = svc.submit_document(user_id, body.doc_type, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _status_payload(status)


@router.get("/status", response_model=None)
async def get_status(user=Depends(get_current_user)):
    """Return the current user's IdentityStatus (with display labels)."""
    user_id = _ensure_talent(user)
    svc = get_identity_service()
    return _status_payload(svc.get_status(user_id))


@router.get("/profile", response_model=None)
async def get_profile(user=Depends(get_current_user)):
    """Return the latest editable structured profile (or null if none yet)."""
    user_id = _ensure_talent(user)
    svc = get_identity_service()
    return {"profile": svc.get_latest(user_id)}


@router.put("/profile", response_model=None)
async def update_profile(
    body: ProfileUpdateRequest,
    user=Depends(get_current_user),
):
    """Update the structured profile and save a NEW version. Returns version_no."""
    user_id = _ensure_talent(user)
    if not isinstance(body.profile, dict):
        raise HTTPException(status_code=422, detail="profile 必须是一个对象")
    svc = get_identity_service()
    version_no = svc.save_profile_version(user_id, body.profile)
    return {"version_no": version_no, "profile": svc.get_latest(user_id)}


@router.get("/profile/versions", response_model=None)
async def list_versions(user=Depends(get_current_user)):
    """List all profile versions (newest-first): [{version_no, created_at}, ...]."""
    user_id = _ensure_talent(user)
    svc = get_identity_service()
    return {"versions": svc.list_versions(user_id)}


@router.get("/profile/versions/{version_no}", response_model=None)
async def get_version(version_no: int, user=Depends(get_current_user)):
    """Return the snapshot for a specific version_no (404 if missing)."""
    user_id = _ensure_talent(user)
    svc = get_identity_service()
    snapshot = svc.get_version(user_id, version_no)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"version {version_no} 不存在")
    return {"version_no": version_no, "snapshot": snapshot}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status_payload(status: IdentityStatus) -> dict[str, Any]:
    """IdentityStatus -> API payload (raw + display labels + reasons)."""
    return status.to_dict()
