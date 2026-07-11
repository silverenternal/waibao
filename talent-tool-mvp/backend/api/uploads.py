"""Uploads API — POST /api/uploads (multipart/form-data).

接受任意角色登录用户上传文件,返回:
    {file_url, path, bucket, mime, size, filename}

可选 query 参数:
    ?bucket=<name>  — 自定义 bucket (默认 env STORAGE_DEFAULT_BUCKET)

兼容 .png/.jpg/.pdf/.txt 等常见类型,白名单由 file_storage 控制。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from services.file_storage import get_file_storage

logger = logging.getLogger("recruittech.api.uploads")
router = APIRouter()


if TYPE_CHECKING:
    # Only used for type hints — never executed at runtime
    from api.auth import CurrentUser, get_current_user  # noqa: F401


# A no-op dependency used by FastAPI at module-load time so we don't trigger
# `import jose` simply by reading api/uploads.py. Tests override this entirely.
async def _bypass_user_dep():
    """Default no-auth fallback.

    Production wiring (main.py) overrides this via app.dependency_overrides
    with api.auth.get_current_user. Tests do the same.
    """
    raise HTTPException(status_code=401, detail="auth not wired — set dependency_overrides")


# Re-export a function tests can override via app.dependency_overrides without
# importing api.auth (which pulls jose). The body just re-raises; the override
# is what matters at request time.
async def get_current_user():  # pragma: no cover - overridden in production & tests
    raise HTTPException(status_code=401, detail="unauthenticated")


@router.post("", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    bucket: str | None = Query(default=None, description="Override target bucket"),
    folder: str = Form(default="files", description="Object prefix/folder"),
    user=Depends(get_current_user),
):
    """Multipart upload — supports any logged-in user."""
    try:
        raw = await file.read()
    except Exception as e:  # noqa: BLE001
        logger.exception(f"upload read failed: {e}")
        raise HTTPException(status_code=400, detail=f"failed to read upload: {e}") from e

    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    svc = get_file_storage()
    try:
        result = await svc.upload(
            raw,
            bucket=bucket,
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            prefix=folder,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception(f"storage upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"upload failed: {e}") from e

    return {
        "success": True,
        **result,
        "uploaded_by": str(getattr(user, "id", "anon")),
    }


@router.get("/signed-url")
async def get_signed_url(
    path: str = Query(...),
    bucket: str | None = Query(default=None),
    ttl: int = Query(default=3600, ge=60, le=86400),
    _user=Depends(get_current_user),
):
    svc = get_file_storage()
    try:
        url = await svc.signed_url(path, bucket=bucket, ttl=ttl)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"file_url": url, "path": path, "bucket": bucket or svc.default_bucket, "ttl": ttl}


@router.delete("")
async def delete_file(
    path: str = Query(...),
    bucket: str | None = Query(default=None),
    _user=Depends(get_current_user),
):
    svc = get_file_storage()
    try:
        ok = await svc.delete(path, bucket=bucket)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"deleted": ok, "path": path, "bucket": bucket or svc.default_bucket}
