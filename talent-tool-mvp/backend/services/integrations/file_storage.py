"""Supabase Storage 包装 — 上传 / 签名 URL / 删除.

默认 bucket 名称可通过 env STORAGE_DEFAULT_BUCKET 覆盖。
支持两种 backend:
  1. 真实 Supabase Storage (生产) — 用 service key 访问
  2. 本地 in-memory fallback (测试 / 无 Supabase 配置) — 把 bytes 存到 dict,
     signed_url 用 data: URL 模拟

所有函数都是 async,signed_url 返回有过期时间。
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, BinaryIO

logger = logging.getLogger("recruittech.services.file_storage")


DEFAULT_BUCKET = os.getenv("STORAGE_DEFAULT_BUCKET", "uploads")
SIGNED_URL_TTL_SECONDS = int(os.getenv("STORAGE_SIGNED_URL_TTL", "3600"))

# Allowed mime families — simple content sniffing based on suffix
ALLOWED_MIME_PREFIXES: tuple[str, ...] = (
    "image/",
    "application/pdf",
    "text/",
)


def _guess_mime(filename: str, content_type: str | None) -> str:
    """从文件名/header 推断 mime,未知默认 application/octet-stream."""
    if content_type and content_type != "application/octet-stream":
        return content_type
    name = (filename or "").lower()
    if name.endswith((".png",)):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith((".webp",)):
        return "image/webp"
    if name.endswith((".pdf",)):
        return "application/pdf"
    if name.endswith((".txt",)):
        return "text/plain"
    return content_type or "application/octet-stream"


def _validate_content_type(mime: str) -> None:
    """白名单 mime 类型。"""
    from fastapi import HTTPException

    if not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported mime: {mime}. allowed prefixes: {ALLOWED_MIME_PREFIXES}",
        )


class _InMemoryBucket:
    """无 Supabase 时的本地 fallback bucket.

    仅在测试/本地 dev 用 — 不耐久,重启即丢。
    """

    def __init__(self) -> None:
        self._objects: dict[str, dict[str, Any]] = {}
        self._signatures: dict[str, tuple[float, str]] = {}

    def upload(self, path: str, data: bytes, mime: str) -> str:
        self._objects[path] = {"bytes": data, "mime": mime, "size": len(data)}
        return path

    def signed_url(self, path: str, ttl: int) -> str:
        if path not in self._objects:
            raise FileNotFoundError(path)
        exp = time.time() + ttl
        token = base64.urlsafe_b64encode(
            f"{path}:{int(exp)}".encode()
        ).decode().rstrip("=")
        url = f"memory://{self._objects[path]['mime']};base64,{base64.b64encode(self._objects[path]['bytes']).decode()}"
        self._signatures[path] = (exp, url)
        return url

    def delete(self, path: str) -> bool:
        existed = path in self._objects
        self._objects.pop(path, None)
        self._signatures.pop(path, None)
        return existed


class FileStorageService:
    """统一封装 Supabase Storage + 本地 fallback.

    示例:
        svc = FileStorageService()
        path = await svc.upload(file_bytes, filename="resume.png", bucket="uploads")
        url  = await svc.signed_url(path, bucket="uploads", ttl=3600)
        ok   = await svc.delete(path, bucket="uploads")
    """

    def __init__(self, default_bucket: str | None = None) -> None:
        self.default_bucket = default_bucket or DEFAULT_BUCKET
        self._memory: dict[str, _InMemoryBucket] = {}
        self._client: Any | None = None  # lazy init

    # -------- backend selection --------

    def _supabase(self) -> Any:
        if self._client is not None:
            return self._client
        from api.deps import get_supabase_admin  # local import to avoid cycle

        try:
            self._client = get_supabase_admin()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"supabase unavailable, using in-memory: {e}")
            self._client = None
        return self._client

    def _bucket(self, name: str) -> _InMemoryBucket:
        if name not in self._memory:
            self._memory[name] = _InMemoryBucket()
        return self._memory[name]

    # -------- public API --------

    async def upload(
        self,
        file: bytes | BinaryIO,
        *,
        bucket: str | None = None,
        filename: str = "upload.bin",
        content_type: str | None = None,
        prefix: str = "files",
    ) -> dict:
        """上传一个文件, 返回 {path, bucket, size, mime, file_url}."""
        if hasattr(file, "read"):
            data = file.read()  # type: ignore[union-attr]
        else:
            data = file  # type: ignore[assignment]
        if not isinstance(data, (bytes, bytearray)):
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="file must be bytes-like")
        data = bytes(data)
        if not data:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="empty file")

        mime = _guess_mime(filename, content_type)
        _validate_content_type(mime)

        bucket = bucket or self.default_bucket
        # path: prefix/{ts}-{filename}
        safe_name = filename.replace("/", "_").replace("..", "_")
        ts = int(time.time() * 1000)
        path = f"{prefix}/{ts}-{safe_name}"

        client = self._supabase()
        if client is not None:
            try:
                # supabase storage: upload with raw bytes
                client.storage.from_(bucket).upload(
                    path=path,
                    file=data,
                    file_options={"content-type": mime, "upsert": "true"},
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"supabase upload failed, fallback to memory: {e}")
                self._bucket(bucket).upload(path, data, mime)
        else:
            self._bucket(bucket).upload(path, data, mime)

        url = await self.signed_url(path, bucket=bucket)
        return {
            "path": path,
            "bucket": bucket,
            "size": len(data),
            "mime": mime,
            "filename": safe_name,
            "file_url": url,
        }

    async def signed_url(
        self,
        path: str,
        *,
        bucket: str | None = None,
        ttl: int | None = None,
    ) -> str:
        """生成签名 URL (Supabase create_signed_url)."""
        bucket = bucket or self.default_bucket
        ttl = ttl or SIGNED_URL_TTL_SECONDS
        client = self._supabase()
        if client is not None:
            try:
                res = client.storage.from_(bucket).create_signed_url(path, ttl)
                if isinstance(res, dict) and res.get("signedURL"):
                    return res["signedURL"]
                if isinstance(res, dict) and res.get("signed_url"):
                    return res["signed_url"]
            except Exception as e:  # noqa: BLE001
                logger.warning(f"supabase signed_url failed, fallback memory: {e}")
        try:
            return self._bucket(bucket).signed_url(path, ttl)
        except FileNotFoundError:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"object not found: {path}") from None

    async def delete(self, path: str, *, bucket: str | None = None) -> bool:
        bucket = bucket or self.default_bucket
        client = self._supabase()
        if client is not None:
            try:
                client.storage.from_(bucket).remove([path])
                return True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"supabase delete failed, fallback memory: {e}")
        return self._bucket(bucket).delete(path)


# ------- module-level singleton -------

_default_service: FileStorageService | None = None


def get_file_storage() -> FileStorageService:
    """模块级单例 getter."""
    global _default_service
    if _default_service is None:
        _default_service = FileStorageService()
    return _default_service


def reset_file_storage() -> None:
    """测试用 — 清空单例。"""
    global _default_service
    _default_service = None
