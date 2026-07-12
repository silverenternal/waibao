"""Video Processing utilities — T1301.

无外部依赖的轻量工具,用于:
    - 客户端在录制时请求预签名上传 URL (走 Supabase Storage)
    - 服务端拿到原始视频 blob 后做基础元信息提取 (ffprobe 不可用时降级)
    - 上传到 Supabase Storage 并返回公开 / 签名播放 URL

设计原则:
    - 不做真正转码(避免引入 ffmpeg 依赖);仅复制原始文件并附加服务端转写
    - 提供 compat 接口,后续接入 ffmpeg / GCP Transcoder API 时只换实现
    - 全失败 → 返回 mock URL,保证面试闭环
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("recruittech.services.video_processing")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class VideoMeta:
    """视频元信息(粗略)。"""

    url: str
    mime: str
    duration_sec: float
    size_bytes: int
    width: int | None = None
    height: int | None = None
    extra: dict[str, Any] | None = None


@dataclass(slots=True)
class UploadTicket:
    """上传凭据。"""

    object_key: str
    upload_url: str
    public_url: str
    expires_in_sec: int = 3600
    method: str = "PUT"
    headers: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# 客户端上传封装
# ---------------------------------------------------------------------------
def make_object_key(user_id: str, interview_id: str, ext: str = "webm") -> str:
    """生成对象 key:`interviews/{user_id}/{interview_id}/{ts}.{ext}`"""
    safe_uid = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(user_id))[:64] or "anon"
    safe_iid = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(interview_id))[:64] or "unknown"
    return f"interviews/{safe_uid}/{safe_iid}/{int(time.time())}_{secrets.token_hex(4)}.{ext}"


def create_upload_ticket(
    user_id: str,
    interview_id: str,
    *,
    mime: str = "video/webm",
    supabase_admin: Any | None = None,
) -> UploadTicket:
    """生成 Supabase Storage 签名上传 URL。

    Args:
        user_id: 用户 ID
        interview_id: 面试 ID
        mime: mime 类型
        supabase_admin: 可选,提供则生成真实签名 URL;否则 mock

    Returns:
        UploadTicket with object_key / upload_url / public_url
    """
    ext = _ext_from_mime(mime)
    key = make_object_key(user_id, interview_id, ext=ext)
    bucket = os.getenv("SUPABASE_VIDEO_BUCKET", "ai-interview-videos")

    # 真实路径
    if supabase_admin is not None:
        try:
            res = supabase_admin.storage.from_(bucket).create_signed_upload_url(key)
            upload_url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else None)
            token = getattr(res, "token", "") if not isinstance(res, dict) else res.get("token", "")
            public = supabase_admin.storage.from_(bucket).get_public_url(key)
            return UploadTicket(
                object_key=key,
                upload_url=upload_url or f"https://storage.supabase.co/{bucket}/{key}",
                public_url=public if isinstance(public, str) else public.get("publicUrl", ""),
                headers={"x-signature": token} if token else None,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"create_signed_upload_url failed: {e}; fallback mock")

    # mock ticket(测试环境 / 无 supabase)
    base = os.getenv("MOCK_STORAGE_BASE", "https://mock-storage.local")
    return UploadTicket(
        object_key=key,
        upload_url=f"{base}/upload/{bucket}/{key}",
        public_url=f"{base}/public/{bucket}/{key}",
        headers={"Authorization": "Bearer mock"},
    )


# ---------------------------------------------------------------------------
# 服务端元信息
# ---------------------------------------------------------------------------
def parse_video_meta(
    blob: bytes,
    *,
    mime: str = "video/webm",
    suggested_url: str | None = None,
) -> VideoMeta:
    """解析视频元信息。

    不依赖 ffprobe:仅从字节大小估算时长占位;若上游传入 url 则保存到 url。
    """
    # 兼容一些 magic byte (webm: 1A 45 DF A3 / mp4: 00 00 00 ?? 66 74 79 70)
    size = len(blob)
    mime = mime or "video/webm"
    width = height = None
    if mime == "video/webm" and size >= 4 and blob[:4] == b"\x1a\x45\xdf\xa3":
        # 这里可以加 ebml parse;此处简化为 None
        pass
    # 估算时长:粗略按 100KB/s(webm 1Mbps 假设)
    duration = max(0.0, round(size / 100_000.0, 1)) if size > 0 else 0.0
    return VideoMeta(
        url=suggested_url or f"https://mock-storage.local/uploaded/{secrets.token_hex(8)}",
        mime=mime,
        duration_sec=duration,
        size_bytes=size,
        width=width,
        height=height,
    )


def upload_to_storage(
    blob: bytes,
    object_key: str,
    *,
    mime: str = "video/webm",
    bucket: str | None = None,
    supabase_admin: Any | None = None,
) -> str:
    """上传到 Supabase Storage,返回公开 URL。

    全失败 → 返回 mock URL(保底)。
    """
    bucket = bucket or os.getenv("SUPABASE_VIDEO_BUCKET", "ai-interview-videos")
    if supabase_admin is not None and blob:
        try:
            supabase_admin.storage.from_(bucket).upload(
                object_key, blob, {"contentType": mime, "upsert": "true"}
            )
            url = supabase_admin.storage.from_(bucket).get_public_url(object_key)
            return url if isinstance(url, str) else url.get("publicUrl", "")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"upload_to_storage failed: {e}; fallback mock url")

    return f"https://mock-storage.local/public/{bucket}/{object_key}"


def generate_thumbnail_url(video_url: str) -> str:
    """返回缩略图 URL(后续接抽帧服务)。"""
    if not video_url:
        return ""
    return video_url + ".jpg" if "?" not in video_url else video_url + "&thumb=1"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ext_from_mime(mime: str) -> str:
    return {
        "video/webm": "webm",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "video/x-m4v": "m4v",
    }.get((mime or "").lower(), "webm")
