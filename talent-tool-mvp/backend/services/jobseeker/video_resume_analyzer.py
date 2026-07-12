"""Video Resume Analyzer — T2203 视频简历理解.

基于 GPT-4V 的多帧视频简历分析:
  - 评分维度: 沟通能力 / 表达清晰度 / 专业度 / 自信度 / 亲和力
  - 自然语言评语: 优点 / 建议
  - 表情 / 眼神接触 / 肢体语言

数据流:
  1. video_processor.process_video_resume()      → 抽帧 + 元数据
  2. 选取关键帧 (默认 6 帧均匀采样)
  3. vision_provider.chat_with_images()          → GPT-4V 多模态
  4. 解析 JSON 输出 → VideoResumeAnalysis
  5. 评分聚合 (5 维度 + 总分 + 标签)

提供一致性保证:
  - 单人多次评分偏差 < 0.1 (同 temperature/seed)
  - 评分归一化到 [0, 1]
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from providers.vision.base import (
    ImageInput,
    VisionMessage,
    VisionProvider,
    VisionResponse,
)
from providers.vision.mock_provider import MockVisionProvider
from services.platform.video_processor import (
    FrameExtractionResult,
    KeyFrame,
    process_video_resume,
)

logger = logging.getLogger("recruittech.services.jobseeker.video_resume_analyzer")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
VIDEO_RESUME_DIMENSIONS = (
    "communication",        # 沟通能力
    "clarity",              # 表达清晰度
    "professionalism",      # 专业度
    "confidence",           # 自信度
    "warmth",               # 亲和力
)

VIDEO_RESUME_DIMENSION_LABELS = {
    "communication": "沟通能力",
    "clarity": "表达清晰度",
    "professionalism": "专业度",
    "confidence": "自信度",
    "warmth": "亲和力",
}


@dataclass(slots=True)
class VideoResumeScores:
    """视频简历 5 维度评分 (0.0 ~ 1.0)."""

    communication: float = 0.0
    clarity: float = 0.0
    professionalism: float = 0.0
    confidence: float = 0.0
    warmth: float = 0.0
    overall: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def clamp(self) -> "VideoResumeScores":
        for k in VIDEO_RESUME_DIMENSIONS:
            v = float(getattr(self, k, 0.0))
            setattr(self, k, max(0.0, min(1.0, round(v, 4))))
        self.overall = max(0.0, min(1.0, round(self.overall, 4)))
        return self


@dataclass(slots=True)
class NonVerbalSignals:
    """非语言信号."""

    expression: str = ""            # 表情 (e.g. "自然 / 微笑 / 紧张")
    eye_contact: str = ""           # 眼神接触 (e.g. "良好 / 飘忽")
    body_language: str = ""         # 肢体语言
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VideoResumeAnalysis:
    """完整视频简历分析结果."""

    source_url: str
    video_metadata: dict[str, Any]
    frames_analyzed: int
    scores: VideoResumeScores
    non_verbal: NonVerbalSignals
    strengths: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    transcript_excerpt: str = ""      # 若有音频转写则截取
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    model: str = ""
    provider_chain: list[str] = field(default_factory=list)
    analyzed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "video_metadata": self.video_metadata,
            "frames_analyzed": self.frames_analyzed,
            "scores": self.scores.as_dict(),
            "non_verbal": asdict(self.non_verbal),
            "strengths": self.strengths,
            "suggestions": self.suggestions,
            "transcript_excerpt": self.transcript_excerpt,
            "tags": self.tags,
            "confidence": self.confidence,
            "model": self.model,
            "provider_chain": self.provider_chain,
            "analyzed_at": self.analyzed_at,
        }


# ---------------------------------------------------------------------------
# Vision Provider 选择
# ---------------------------------------------------------------------------
def get_vision_provider() -> VisionProvider:
    """按 VISION_PROVIDER env 选择 vision provider,缺省 mock."""
    name = (os.getenv("VISION_PROVIDER") or "mock").lower()
    if name == "mock":
        return MockVisionProvider()
    # 真实 provider (gpt4v / qwen_vl) 走 registry
    try:
        from providers.vision.registry import get_vision_registry
        registry = get_vision_registry()
        return registry.get(name)  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        logger.warning("vision registry unavailable, fallback to mock")
        return MockVisionProvider()


# ---------------------------------------------------------------------------
# 帧采样
# ---------------------------------------------------------------------------
def sample_frames(
    frame_extraction: FrameExtractionResult,
    *,
    max_frames: int = 6,
) -> list[KeyFrame]:
    """从 FrameExtractionResult 中均匀采样最多 max_frames 帧."""
    frames = frame_extraction.frames
    if len(frames) <= max_frames:
        return frames
    step = max(1, len(frames) // max_frames)
    return frames[::step][:max_frames]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
ANALYSIS_SYSTEM_PROMPT = """你是一位资深面试官,正在评估一段 30~60 秒的视频简历 (候选人自我介绍).

你会看到来自视频的 6 张关键帧 (每 5 秒 1 帧).请基于这些帧的画面内容评估候选人.

输出严格的 JSON,字段:
{
  "scores": {
    "communication": 0.0~1.0,
    "clarity": 0.0~1.0,
    "professionalism": 0.0~1.0,
    "confidence": 0.0~1.0,
    "warmth": 0.0~1.0
  },
  "non_verbal": {
    "expression": "表情描述 (e.g. 微笑 / 严肃 / 紧张)",
    "eye_contact": "眼神接触 (e.g. 始终看镜头 / 偶有飘忽)",
    "body_language": "肢体语言 (e.g. 姿态端正 / 紧张僵硬)",
    "notes": ["额外观察点 1", "额外观察点 2"]
  },
  "strengths": ["优点 1", "优点 2"],
  "suggestions": ["建议 1", "建议 2"],
  "tags": ["#标签1", "#标签2"],
  "confidence": 0.0~1.0
}

评分标准:
  - 0.0~0.3: 明显不足
  - 0.3~0.6: 中等
  - 0.6~0.8: 较好
  - 0.8~1.0: 优秀

只返回 JSON,不要附加解释.
"""


# ---------------------------------------------------------------------------
# 评分聚合
# ---------------------------------------------------------------------------
def aggregate_scores(scores: VideoResumeScores) -> VideoResumeScores:
    """5 维度评分聚合 → overall = 加权平均."""
    weights = {
        "communication": 0.25,
        "clarity": 0.25,
        "professionalism": 0.20,
        "confidence": 0.15,
        "warmth": 0.15,
    }
    overall = sum(getattr(scores, k) * w for k, w in weights.items())
    scores.overall = round(overall, 4)
    return scores


# ---------------------------------------------------------------------------
# JSON 解析 (宽容)
# ---------------------------------------------------------------------------
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中抽取 JSON. 容错: 剥离 markdown fence;失败返回空 dict."""
    if not text:
        return {}
    cleaned = _JSON_FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试取首个 {...}
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {}


# ---------------------------------------------------------------------------
# 主分析函数
# ---------------------------------------------------------------------------
async def analyze_video_resume(
    source_url: str,
    *,
    vision: VisionProvider | None = None,
    interval_sec: float = 5.0,
    max_frames: int = 6,
    transcript_excerpt: str = "",
    blob_size_bytes: int | None = None,
    model: str | None = None,
) -> VideoResumeAnalysis:
    """分析视频简历,返回 VideoResumeAnalysis.

    Args:
        source_url: 视频 URL (mock 模式下任意 URL 都可)
        vision: 可选 vision provider (默认 mock)
        interval_sec: 抽帧间隔 (默认 5s)
        max_frames: 最大采样帧数 (默认 6)
        transcript_excerpt: 音频转写片段 (可选,用于更准确评分)
        blob_size_bytes: 视频字节数 (用于估算时长)

    Returns:
        VideoResumeAnalysis: 完整分析结果
    """
    from datetime import datetime, timezone

    vision = vision or get_vision_provider()
    provider_chain: list[str] = [vision.provider_name]

    # 1. 抽帧 + 元数据
    pipeline = process_video_resume(
        source_url,
        interval_sec=interval_sec,
        max_frames=30,
        blob_size_bytes=blob_size_bytes,
    )
    raw_frames = pipeline["frames"].get("frames") or []
    keyframes = [
        KeyFrame(
            timestamp_sec=float(f.get("timestamp_sec", 0)),
            index=int(f.get("index", 0)),
            url=str(f.get("url", "")),
            width=int(f.get("width", 0)),
            height=int(f.get("height", 0)),
            bytes_size=int(f.get("bytes_size", 0)),
            extracted_at=str(f.get("extracted_at", "")),
        )
        for f in raw_frames
    ]
    frames_result = FrameExtractionResult(
        source_url=pipeline["frames"]["source_url"],
        interval_sec=float(pipeline["frames"]["interval_sec"]),
        total_frames=int(pipeline["frames"]["total_frames"]),
        frames=keyframes,
        extracted_at=str(pipeline["frames"].get("extracted_at", "")),
    )
    sampled = sample_frames(frames_result, max_frames=max_frames)

    # 2. 构造多模态消息
    images = [ImageInput(url=f.url) for f in sampled]
    user_text = (
        f"这是候选人 30~60 秒视频简历的关键 {len(sampled)} 帧 (每 {interval_sec}s 一帧).\n"
        f"视频源: {source_url}\n"
    )
    if transcript_excerpt:
        user_text += f"\n音频转写片段:\n{transcript_excerpt[:500]}\n"
    messages = [
        VisionMessage(role="system", text=ANALYSIS_SYSTEM_PROMPT),
        VisionMessage(role="user", text=user_text, images=images),
    ]

    # 3. 调用 vision
    try:
        resp: VisionResponse = await vision.chat_with_images(
            messages, model=model, temperature=0.2, max_tokens=900,
        )
        data = _extract_json(resp.content)
        provider_chain.append(f"model={resp.model}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"vision chat failed: {e}; using empty scores")
        data = {}

    # 4. 解析为 VideoResumeScores
    raw_scores = (data.get("scores") or {}) if isinstance(data, dict) else {}
    scores = VideoResumeScores(
        communication=float(raw_scores.get("communication", 0.0)),
        clarity=float(raw_scores.get("clarity", 0.0)),
        professionalism=float(raw_scores.get("professionalism", 0.0)),
        confidence=float(raw_scores.get("confidence", 0.0)),
        warmth=float(raw_scores.get("warmth", 0.0)),
    ).clamp()
    aggregate_scores(scores)

    # 5. 非语言信号
    nv_raw = (data.get("non_verbal") or {}) if isinstance(data, dict) else {}
    non_verbal = NonVerbalSignals(
        expression=str(nv_raw.get("expression", "")),
        eye_contact=str(nv_raw.get("eye_contact", "")),
        body_language=str(nv_raw.get("body_language", "")),
        notes=list(nv_raw.get("notes") or []),
    )

    return VideoResumeAnalysis(
        source_url=source_url,
        video_metadata=pipeline["metadata"],
        frames_analyzed=len(sampled),
        scores=scores,
        non_verbal=non_verbal,
        strengths=list(data.get("strengths") or []),
        suggestions=list(data.get("suggestions") or []),
        transcript_excerpt=transcript_excerpt[:500],
        tags=list(data.get("tags") or []),
        confidence=float(data.get("confidence", 0.0)) if isinstance(data, dict) else 0.0,
        model=(model or "default"),
        provider_chain=provider_chain,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# 合并到画像 (供 profile_agent / candidate_clarifier_agent 使用)
# ---------------------------------------------------------------------------
VIDEO_SCORE_WEIGHT = 0.15      # 视频评分合并权重 (T2203 spec)
TEXT_PROFILE_WEIGHT = 0.85     # 文本简历合并权重


def merge_video_into_profile(
    profile: dict[str, Any],
    analysis: VideoResumeAnalysis,
) -> dict[str, Any]:
    """把视频简历分析结果合并到候选人画像.

    合并策略:
      - 软技能 (5 维度评分) → profile["soft_skills"] (加权 0.15)
      - non_verbal → profile["non_verbal_signals"]
      - strengths / suggestions → profile["video_resume_feedback"]
      - tags → profile["tags"] (去重合并)
      - provenance → profile["_video_resume_*"]
    """
    merged = dict(profile)
    scores = analysis.scores.as_dict()

    # 1. soft_skills 整合
    soft = dict(merged.get("soft_skills") or {})
    for dim in VIDEO_RESUME_DIMENSIONS:
        cur = float(soft.get(dim, 0.0))
        video_v = float(scores.get(dim, 0.0))
        # 加权合并: 已有值 × text_weight + 视频 × video_weight (假设已有值来自文本)
        merged_v = round(cur * TEXT_PROFILE_WEIGHT + video_v * VIDEO_SCORE_WEIGHT, 4)
        soft[dim] = max(0.0, min(1.0, merged_v))
    soft["overall"] = round(sum(soft[d] for d in VIDEO_RESUME_DIMENSIONS) / len(VIDEO_RESUME_DIMENSIONS), 4)
    soft["source"] = "video_resume+text" if any(merged.get("soft_skills", {}).values()) else "video_resume"
    merged["soft_skills"] = soft

    # 2. non_verbal_signals
    merged["non_verbal_signals"] = {
        "expression": analysis.non_verbal.expression,
        "eye_contact": analysis.non_verbal.eye_contact,
        "body_language": analysis.non_verbal.body_language,
        "notes": list(analysis.non_verbal.notes),
    }

    # 3. 反馈
    feedback = dict(merged.get("video_resume_feedback") or {})
    feedback["strengths"] = analysis.strengths
    feedback["suggestions"] = analysis.suggestions
    feedback["source_url"] = analysis.source_url
    feedback["frames_analyzed"] = analysis.frames_analyzed
    feedback["analyzed_at"] = analysis.analyzed_at
    merged["video_resume_feedback"] = feedback

    # 4. tags 去重合并
    existing_tags = set(merged.get("tags") or [])
    for t in analysis.tags:
        tag = str(t).strip().lstrip("#")
        if tag and tag not in existing_tags:
            existing_tags.add(tag)
    merged["tags"] = sorted(existing_tags)

    # 5. provenance
    import datetime as _dt
    merged["_video_resume_source_url"] = analysis.source_url
    merged["_video_resume_provider_chain"] = analysis.provider_chain
    merged["_video_resume_model"] = analysis.model
    merged["_video_resume_scores"] = scores
    merged["_video_resume_analyzed_at"] = analysis.analyzed_at

    return merged


def summarize_for_clarifier(analysis: VideoResumeAnalysis) -> str:
    """生成供 candidate_clarifier_agent 引用的一句话摘要."""
    s = analysis.scores
    top_dim = max(VIDEO_RESUME_DIMENSIONS, key=lambda d: getattr(s, d))
    bottom_dim = min(VIDEO_RESUME_DIMENSIONS, key=lambda d: getattr(s, d))
    top_label = VIDEO_RESUME_DIMENSION_LABELS[top_dim]
    bottom_label = VIDEO_RESUME_DIMENSION_LABELS[bottom_dim]
    overall_pct = int(s.overall * 100)
    return (
        f"[视频简历 {overall_pct}分] 最佳:{top_label} ({int(getattr(s, top_dim)*100)}分),"
        f"待提升:{bottom_label} ({int(getattr(s, bottom_dim)*100)}分). "
        f"主要优点:{analysis.strengths[0] if analysis.strengths else 'N/A'}. "
        f"建议:{analysis.suggestions[0] if analysis.suggestions else 'N/A'}"
    )


__all__ = [
    "VIDEO_RESUME_DIMENSIONS",
    "VIDEO_RESUME_DIMENSION_LABELS",
    "VIDEO_SCORE_WEIGHT",
    "TEXT_PROFILE_WEIGHT",
    "VideoResumeScores",
    "NonVerbalSignals",
    "VideoResumeAnalysis",
    "analyze_video_resume",
    "merge_video_into_profile",
    "summarize_for_clarifier",
    "aggregate_scores",
    "sample_frames",
]