"""Video Processor — T2203 视频简历理解 (v5.0 重构升级).

本模块位于 services/platform/ 下,作为「平台级」的视频处理服务,
与 jobseeker/video_processing.py 的「轻量工具」(上传/元信息)互补:

- 转码: H.264 / H.265 / MP4 容器(模拟/可降级)
- 关键帧提取: 每 5 秒抽 1 帧
- 元数据: 时长/分辨率/码率/编码
- 提供抽帧 URL 列表供 vision_provider (GPT-4V) 多帧分析

设计原则:
  - 不依赖 ffmpeg 二进制;在 ffmpeg 不可用时降级到伪元数据
  - 接口稳定: 转码 / 抽帧 / 元数据 三类操作都是纯函数
  - 与 video_processing.py (jobseeker) 协作: 上传 → 转码 → 抽帧 → 分析
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("recruittech.services.platform.video_processor")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class VideoMetadata:
    """视频完整元信息 (含转码目标)."""

    duration_sec: float
    width: int = 0
    height: int = 0
    frame_rate: float = 0.0
    bitrate_kbps: int = 0
    codec: str = "unknown"               # H.264 / H.265 / VP9 / ...
    container: str = "unknown"           # mp4 / webm / mov
    size_bytes: int = 0
    audio_codec: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KeyFrame:
    """关键帧 (抽帧结果)."""

    timestamp_sec: float
    index: int
    url: str
    width: int = 0
    height: int = 0
    bytes_size: int = 0
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TranscodeResult:
    """转码结果."""

    source_url: str
    target_codec: str                       # H.264 / H.265
    target_container: str                   # mp4
    output_url: str
    metadata: VideoMetadata
    transcoded_at: str = ""
    transcoder: str = "internal"            # internal / ffmpeg / gcp-transcoder

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "target_codec": self.target_codec,
            "target_container": self.target_container,
            "output_url": self.output_url,
            "metadata": self.metadata.to_dict(),
            "transcoded_at": self.transcoded_at,
            "transcoder": self.transcoder,
        }


@dataclass(slots=True)
class FrameExtractionResult:
    """抽帧结果集."""

    source_url: str
    interval_sec: float
    total_frames: int
    frames: list[KeyFrame] = field(default_factory=list)
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "interval_sec": self.interval_sec,
            "total_frames": self.total_frames,
            "frames": [f.to_dict() for f in self.frames],
            "extracted_at": self.extracted_at,
        }


# ---------------------------------------------------------------------------
# 元数据提取 (mock-friendly)
# ---------------------------------------------------------------------------
def extract_metadata(
    source_url: str,
    *,
    blob_size_bytes: int | None = None,
) -> VideoMetadata:
    """提取视频元信息.

    真实环境应使用 ffprobe;此处提供:
      - 基于 source_url hash 的稳定伪元数据(便于测试/离线)
      - 优先用 blob_size_bytes 估算时长
    """
    url_hash = hashlib.sha1(source_url.encode("utf-8")).hexdigest()

    # 容器从 url 推断
    container = "mp4"
    if source_url.lower().endswith(".webm"):
        container = "webm"
    elif source_url.lower().endswith(".mov"):
        container = "mov"
    elif source_url.lower().endswith(".mkv"):
        container = "mkv"

    # 编码推断
    codec = "H.264"
    if container == "webm":
        codec = "VP9"

    # 时长估算: 假设 1Mbps,1MB ≈ 8s
    if blob_size_bytes:
        duration = round(blob_size_bytes / 125_000.0, 1)
    else:
        # 用 hash 派生一个稳定 30~90s 之间的时长
        duration = 30.0 + (int(url_hash[:4], 16) % 60)

    # 分辨率: 常见值 (480p/720p/1080p)
    common_resolutions = [(640, 480), (1280, 720), (1920, 1080)]
    idx = int(url_hash[4:6], 16) % len(common_resolutions)
    width, height = common_resolutions[idx]

    # 帧率 24/25/30/60
    fr_options = [24.0, 25.0, 30.0, 60.0]
    frame_rate = fr_options[int(url_hash[6:8], 16) % len(fr_options)]

    # 码率
    bitrate_kbps = int(width * height * frame_rate * 0.1)  # 粗略估算

    return VideoMetadata(
        duration_sec=duration,
        width=width,
        height=height,
        frame_rate=frame_rate,
        bitrate_kbps=bitrate_kbps,
        codec=codec,
        container=container,
        size_bytes=blob_size_bytes or 0,
        audio_codec="AAC" if container == "mp4" else "Opus",
    )


# ---------------------------------------------------------------------------
# 转码
# ---------------------------------------------------------------------------
SUPPORTED_CODECS = ("H.264", "H.265")
SUPPORTED_CONTAINERS = ("mp4",)


def transcode_video(
    source_url: str,
    *,
    target_codec: str = "H.264",
    target_container: str = "mp4",
    metadata: VideoMetadata | None = None,
) -> TranscodeResult:
    """转码视频到目标格式.

    真实环境: 调用 ffmpeg / GCP Transcoder API / AWS MediaConvert.
    当前实现: 在 ffmpeg 不可用时返回 mock 转码结果 (output_url = source_url 转码后缀).
    """
    if target_codec not in SUPPORTED_CODECS:
        raise ValueError(f"unsupported target_codec: {target_codec}")
    if target_container not in SUPPORTED_CONTAINERS:
        raise ValueError(f"unsupported target_container: {target_container}")

    meta = metadata or extract_metadata(source_url)
    from datetime import datetime, timezone
    transcoded_at = datetime.now(timezone.utc).isoformat()

    # 真实转码路径 (有 ffmpeg 时)
    if os.getenv("FFMPEG_BIN") and os.path.exists(os.getenv("FFMPEG_BIN", "")):
        # 预留真实转码 hook;当前实现总是走 mock 以保证离线可测试
        pass

    # mock 输出 URL (保留源 + 转码后缀)
    suffix = f".{target_codec.lower().replace('.', '_')}.{target_container}"
    output_url = source_url.rsplit(".", 1)[0] + suffix if "." in source_url else source_url + suffix

    return TranscodeResult(
        source_url=source_url,
        target_codec=target_codec,
        target_container=target_container,
        output_url=output_url,
        metadata=meta,
        transcoded_at=transcoded_at,
        transcoder="internal",
    )


# ---------------------------------------------------------------------------
# 关键帧提取
# ---------------------------------------------------------------------------
def extract_keyframes(
    source_url: str,
    *,
    interval_sec: float = 5.0,
    metadata: VideoMetadata | None = None,
    max_frames: int = 30,
) -> FrameExtractionResult:
    """按 interval_sec 间隔抽帧 (默认 5 秒/帧).

    Args:
        source_url: 视频源 URL
        interval_sec: 抽帧间隔 (默认 5.0)
        metadata: 可选预提取的元信息
        max_frames: 最大帧数 (避免 1 小时视频产生 720 帧)

    Returns:
        FrameExtractionResult 包含所有关键帧
    """
    meta = metadata or extract_metadata(source_url)
    duration = meta.duration_sec

    if interval_sec <= 0:
        raise ValueError("interval_sec must be > 0")
    if duration <= 0:
        # 兜底: 至少 1 帧
        duration = interval_sec

    n_frames = max(1, min(int(duration / interval_sec) + 1, max_frames))

    from datetime import datetime, timezone
    extracted_at = datetime.now(timezone.utc).isoformat()

    frames: list[KeyFrame] = []
    base_hash = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:8]

    for i in range(n_frames):
        ts = round(i * interval_sec, 1)
        # 每帧 URL 命名: <source>.frame.<i>.<ts>s.jpg
        if "?" in source_url:
            base, q = source_url.split("?", 1)
            frame_url = f"{base}.frame.{i:03d}.{ts}s.jpg?{q}&hash={base_hash}"
        else:
            frame_url = f"{source_url}.frame.{i:03d}.{ts}s.jpg?hash={base_hash}"

        frames.append(
            KeyFrame(
                timestamp_sec=ts,
                index=i,
                url=frame_url,
                width=meta.width,
                height=meta.height,
                bytes_size=0,             # mock;真实实现会记录实际大小
                extracted_at=extracted_at,
            )
        )

    return FrameExtractionResult(
        source_url=source_url,
        interval_sec=interval_sec,
        total_frames=len(frames),
        frames=frames,
        extracted_at=extracted_at,
    )


# ---------------------------------------------------------------------------
# 高阶管线: 转码 + 抽帧
# ---------------------------------------------------------------------------
def process_video_resume(
    source_url: str,
    *,
    target_codec: str = "H.264",
    interval_sec: float = 5.0,
    max_frames: int = 30,
    blob_size_bytes: int | None = None,
) -> dict[str, Any]:
    """视频简历处理管线: 提取元数据 → 转码 → 抽帧 → 返回完整结果.

    Returns:
        {
            "metadata": VideoMetadata.to_dict(),
            "transcode": TranscodeResult.to_dict(),
            "frames": FrameExtractionResult.to_dict(),
        }
    """
    meta = extract_metadata(source_url, blob_size_bytes=blob_size_bytes)
    tc = transcode_video(source_url, target_codec=target_codec, metadata=meta)
    fe = extract_keyframes(
        source_url, interval_sec=interval_sec, metadata=meta, max_frames=max_frames,
    )
    return {
        "metadata": meta.to_dict(),
        "transcode": tc.to_dict(),
        "frames": fe.to_dict(),
    }


__all__ = [
    "VideoMetadata",
    "KeyFrame",
    "TranscodeResult",
    "FrameExtractionResult",
    "SUPPORTED_CODECS",
    "SUPPORTED_CONTAINERS",
    "extract_metadata",
    "transcode_video",
    "extract_keyframes",
    "process_video_resume",
]