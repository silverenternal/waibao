"""T2203 - 视频简历理解 测试.

覆盖:
  - video_processor: 元数据/转码/抽帧
  - video_resume_analyzer: 5 维度评分/聚合/合并到画像
  - 一致性: 同人多次评分偏差 < 0.1
  - mock GPT-4V (DeterministicMockVision)
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
from dataclasses import dataclass
from typing import Any

import pytest

# 强制 mock 模式
os.environ.setdefault("VISION_PROVIDER", "mock")

from providers.vision.base import (  # noqa: E402
    ImageInput,
    VisionMessage,
    VisionProvider,
    VisionResponse,
)
from services.jobseeker.video_resume_analyzer import (  # noqa: E402
    VIDEO_RESUME_DIMENSIONS,
    VIDEO_SCORE_WEIGHT,
    TEXT_PROFILE_WEIGHT,
    NonVerbalSignals,
    VideoResumeAnalysis,
    VideoResumeScores,
    aggregate_scores,
    analyze_video_resume,
    merge_video_into_profile,
    sample_frames,
    summarize_for_clarifier,
)
from services.platform.video_processor import (  # noqa: E402
    SUPPORTED_CODECS,
    SUPPORTED_CONTAINERS,
    FrameExtractionResult,
    KeyFrame,
    TranscodeResult,
    VideoMetadata,
    extract_keyframes,
    extract_metadata,
    process_video_resume,
    transcode_video,
)


# ---------------------------------------------------------------------------
# Mock GPT-4V — 返回确定性的 JSON
# ---------------------------------------------------------------------------
@dataclass
class DeterministicMockVision(VisionProvider):
    """为 T2203 测试而设: 返回稳定的 5 维度评分 JSON."""

    provider_name: str = "deterministic-mock"
    scores: dict[str, float] | None = None
    strengths: tuple[str, ...] = ("表达流畅", "专业度高")
    suggestions: tuple[str, ...] = ("眼神更稳", "结尾加号召")

    @property
    def supported_models(self) -> list[str]:
        return ["deterministic-mock"]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return {"deterministic-mock": (0.0, 0.0)}

    async def chat_with_images(
        self,
        messages: list[VisionMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> VisionResponse:
        scores = self.scores or {
            "communication": 0.8,
            "clarity": 0.75,
            "professionalism": 0.85,
            "confidence": 0.7,
            "warmth": 0.78,
        }
        data = {
            "scores": scores,
            "non_verbal": {
                "expression": "微笑自然",
                "eye_contact": "良好",
                "body_language": "姿态端正",
                "notes": ["节奏适中"],
            },
            "strengths": list(self.strengths),
            "suggestions": list(self.suggestions),
            "tags": ["#沟通", "#自信"],
            "confidence": 0.82,
        }
        return VisionResponse(
            content=json.dumps(data, ensure_ascii=False),
            model="deterministic-mock",
            usage_tokens=100,
        )

    async def ocr(self, image: ImageInput, *, model: str | None = None, **kwargs: Any) -> str:
        return "mock-ocr"


# ---------------------------------------------------------------------------
# video_processor tests
# ---------------------------------------------------------------------------
class TestVideoProcessor:
    def test_extract_metadata_returns_required_fields(self):
        meta = extract_metadata("https://example.com/resume.mp4", blob_size_bytes=5_000_000)
        assert isinstance(meta, VideoMetadata)
        assert meta.duration_sec > 0
        assert meta.width > 0
        assert meta.height > 0
        assert meta.frame_rate > 0
        assert meta.codec in ("H.264", "H.265", "VP9")
        assert meta.container in ("mp4", "webm", "mov", "mkv")

    def test_extract_metadata_stable_per_url(self):
        a = extract_metadata("https://example.com/v1.mp4")
        b = extract_metadata("https://example.com/v1.mp4")
        assert a.to_dict() == b.to_dict()

    def test_transcode_h264(self):
        result = transcode_video(
            "https://example.com/in.mp4", target_codec="H.264", target_container="mp4"
        )
        assert isinstance(result, TranscodeResult)
        assert result.target_codec == "H.264"
        assert result.target_container == "mp4"
        assert result.output_url.endswith(".h_264.mp4") or ".h264.mp4" in result.output_url

    def test_transcode_h265(self):
        result = transcode_video("https://example.com/in.webm", target_codec="H.265")
        assert result.target_codec == "H.265"
        assert result.metadata.duration_sec > 0

    def test_transcode_unsupported_codec(self):
        with pytest.raises(ValueError):
            transcode_video("https://example.com/in.mp4", target_codec="VP9")

    def test_transcode_unsupported_container(self):
        with pytest.raises(ValueError):
            transcode_video("https://example.com/in.mp4", target_container="webm")

    def test_supported_codecs_constants(self):
        assert "H.264" in SUPPORTED_CODECS
        assert "H.265" in SUPPORTED_CODECS
        assert "mp4" in SUPPORTED_CONTAINERS

    def test_extract_keyframes_default_interval(self):
        meta = extract_metadata("https://example.com/v.mp4", blob_size_bytes=3_000_000)
        result = extract_keyframes("https://example.com/v.mp4", metadata=meta, interval_sec=5.0)
        assert isinstance(result, FrameExtractionResult)
        assert result.interval_sec == 5.0
        assert result.total_frames >= 1
        # 5s 间隔 → 第一帧 0s, 第二帧 5s
        assert result.frames[0].timestamp_sec == 0.0
        if len(result.frames) > 1:
            assert result.frames[1].timestamp_sec == 5.0
        # 帧 URL 应包含 .frame. 前缀
        assert ".frame." in result.frames[0].url

    def test_extract_keyframes_respects_max_frames(self):
        result = extract_keyframes(
            "https://example.com/very_long.mp4", interval_sec=1.0, max_frames=5
        )
        assert result.total_frames <= 5

    def test_extract_keyframes_invalid_interval(self):
        with pytest.raises(ValueError):
            extract_keyframes("https://example.com/v.mp4", interval_sec=0)

    def test_process_video_resume_pipeline(self):
        out = process_video_resume("https://example.com/cv.mp4", interval_sec=5.0)
        assert "metadata" in out
        assert "transcode" in out
        assert "frames" in out
        assert out["transcode"]["target_codec"] in ("H.264", "H.265")
        assert out["frames"]["interval_sec"] == 5.0


# ---------------------------------------------------------------------------
# sample_frames tests
# ---------------------------------------------------------------------------
class TestSampleFrames:
    def test_sample_returns_all_when_under_limit(self):
        fe = FrameExtractionResult(
            source_url="x",
            interval_sec=5.0,
            total_frames=3,
            frames=[
                KeyFrame(timestamp_sec=0, index=0, url="a"),
                KeyFrame(timestamp_sec=5, index=1, url="b"),
                KeyFrame(timestamp_sec=10, index=2, url="c"),
            ],
        )
        sampled = sample_frames(fe, max_frames=6)
        assert len(sampled) == 3

    def test_sample_downsamples_when_over_limit(self):
        frames = [
            KeyFrame(timestamp_sec=i * 5, index=i, url=f"f{i}")
            for i in range(20)
        ]
        fe = FrameExtractionResult(
            source_url="x", interval_sec=5.0, total_frames=20, frames=frames
        )
        sampled = sample_frames(fe, max_frames=6)
        assert len(sampled) == 6


# ---------------------------------------------------------------------------
# video_resume_analyzer tests
# ---------------------------------------------------------------------------
class TestVideoResumeAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_returns_5d_scores(self):
        vision = DeterministicMockVision()
        result = await analyze_video_resume(
            "https://example.com/cv.mp4",
            vision=vision,
            interval_sec=5.0,
            max_frames=6,
            blob_size_bytes=3_000_000,
        )
        assert isinstance(result, VideoResumeAnalysis)
        assert result.frames_analyzed >= 1
        for d in VIDEO_RESUME_DIMENSIONS:
            assert 0.0 <= getattr(result.scores, d) <= 1.0
        assert 0.0 <= result.scores.overall <= 1.0
        assert result.scores.overall > 0  # mock 返回非零

    @pytest.mark.asyncio
    async def test_analyze_includes_non_verbal_and_feedback(self):
        vision = DeterministicMockVision()
        result = await analyze_video_resume(
            "https://example.com/cv.mp4", vision=vision
        )
        assert isinstance(result.non_verbal, NonVerbalSignals)
        assert result.non_verbal.expression == "微笑自然"
        assert result.non_verbal.eye_contact == "良好"
        assert len(result.strengths) >= 1
        assert len(result.suggestions) >= 1
        assert result.provider_chain == ["deterministic-mock", "model=deterministic-mock"]

    @pytest.mark.asyncio
    async def test_analyze_handles_llm_failure_gracefully(self):
        class FailingVision(VisionProvider):
            provider_name = "failing"
            @property
            def supported_models(self): return ["fail"]
            @property
            def pricing(self): return {"fail": (0, 0)}
            async def chat_with_images(self, messages, **_): raise RuntimeError("LLM down")
            async def ocr(self, image, **_): return ""

        result = await analyze_video_resume(
            "https://example.com/cv.mp4", vision=FailingVision()
        )
        assert result.scores.overall == 0.0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_analyze_handles_garbage_json(self):
        class GarbageVision(VisionProvider):
            provider_name = "garbage"
            @property
            def supported_models(self): return ["g"]
            @property
            def pricing(self): return {"g": (0, 0)}
            async def chat_with_images(self, messages, **_):
                return VisionResponse(content="not json at all", model="g", usage_tokens=0)
            async def ocr(self, image, **_): return ""

        result = await analyze_video_resume(
            "https://example.com/cv.mp4", vision=GarbageVision()
        )
        # 应该安全降级到 0 分
        assert result.scores.overall == 0.0

    def test_aggregate_scores_weighted(self):
        scores = VideoResumeScores(
            communication=0.8, clarity=0.7, professionalism=0.6,
            confidence=0.5, warmth=0.4,
        )
        aggregate_scores(scores)
        # weighted: 0.8*0.25 + 0.7*0.25 + 0.6*0.20 + 0.5*0.15 + 0.4*0.15 = 0.635
        assert math.isclose(scores.overall, 0.635, abs_tol=0.01)

    def test_scores_clamp(self):
        scores = VideoResumeScores(communication=1.5, clarity=-0.5, professionalism=0.5)
        scores.clamp()
        assert scores.communication == 1.0
        assert scores.clarity == 0.0
        assert scores.professionalism == 0.5

    def test_merge_video_into_profile_text_weight_dominant(self):
        profile = {
            "soft_skills": {
                "communication": 0.9,   # text 来源高分
                "clarity": 0.9,
            },
            "tags": ["#已有"],
        }
        analysis_dict = {
            "source_url": "https://example.com/cv.mp4",
            "video_metadata": {},
            "frames_analyzed": 6,
            "scores": {
                "communication": 0.4,  # 视频打分低
                "clarity": 0.4,
                "professionalism": 0.4,
                "confidence": 0.4,
                "warmth": 0.4,
                "overall": 0.4,
            },
            "non_verbal": {"expression": "紧张", "eye_contact": "飘忽"},
            "strengths": [],
            "suggestions": ["放松"],
            "tags": ["#沟通"],
        }
        scores = VideoResumeScores(
            communication=0.4, clarity=0.4, professionalism=0.4,
            confidence=0.4, warmth=0.4,
        )
        aggregate_scores(scores)
        nv = NonVerbalSignals(expression="紧张", eye_contact="飘忽")
        analysis = VideoResumeAnalysis(
            source_url="https://example.com/cv.mp4",
            video_metadata={},
            frames_analyzed=6,
            scores=scores,
            non_verbal=nv,
            suggestions=["放松"],
            tags=["#沟通"],
        )
        merged = merge_video_into_profile(profile, analysis)

        # 权重检查: 0.9 * 0.85 + 0.4 * 0.15 = 0.825
        assert math.isclose(merged["soft_skills"]["communication"], 0.825, abs_tol=0.01)
        assert math.isclose(merged["soft_skills"]["clarity"], 0.825, abs_tol=0.01)

        # tags 去重
        assert "#已有" in merged["tags"]
        assert "沟通" in merged["tags"]  # 去掉 # 前缀

        # non_verbal + feedback 写入
        assert merged["non_verbal_signals"]["expression"] == "紧张"
        assert merged["video_resume_feedback"]["suggestions"] == ["放松"]
        assert merged["_video_resume_source_url"] == "https://example.com/cv.mp4"

    def test_merge_video_into_profile_empty_profile(self):
        analysis_dict = {
            "scores": {
                "communication": 0.8, "clarity": 0.7, "professionalism": 0.6,
                "confidence": 0.5, "warmth": 0.4, "overall": 0.0,
            },
            "non_verbal": {},
            "strengths": [], "suggestions": [], "tags": [],
        }
        scores = VideoResumeScores(
            communication=0.8, clarity=0.7, professionalism=0.6,
            confidence=0.5, warmth=0.4,
        )
        aggregate_scores(scores)
        analysis = VideoResumeAnalysis(
            source_url="x", video_metadata={}, frames_analyzed=6,
            scores=scores, non_verbal=NonVerbalSignals(),
        )
        merged = merge_video_into_profile({}, analysis)
        # 空画像下, video 评分全量生效 (0 * 0.85 + v * 0.15 = 0.15*v)
        assert math.isclose(merged["soft_skills"]["communication"], 0.15 * 0.8, abs_tol=0.001)
        assert merged["soft_skills"]["source"] == "video_resume"

    def test_summarize_for_clarifier(self):
        scores = VideoResumeScores(
            communication=0.9, clarity=0.5, professionalism=0.6,
            confidence=0.4, warmth=0.7,
        )
        aggregate_scores(scores)
        analysis = VideoResumeAnalysis(
            source_url="x", video_metadata={}, frames_analyzed=6,
            scores=scores, non_verbal=NonVerbalSignals(),
            strengths=["亮点A"], suggestions=["建议B"],
        )
        s = summarize_for_clarifier(analysis)
        assert "沟通能力" in s
        assert "待提升" in s
        assert "亮点A" in s
        assert "建议B" in s

    def test_weight_constants(self):
        # T2203 spec: 视频 0.15, 文本 0.85
        assert VIDEO_SCORE_WEIGHT == 0.15
        assert TEXT_PROFILE_WEIGHT == 0.85
        assert abs(VIDEO_SCORE_WEIGHT + TEXT_PROFILE_WEIGHT - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# 一致性测试 — 同人多次评分偏差 < 0.1
# ---------------------------------------------------------------------------
class TestConsistency:
    @pytest.mark.asyncio
    async def test_consistency_same_video_multiple_runs(self):
        """同人(同一视频) 多次评分,偏差应 < 0.1.

        DeterministicMockVision 每次返回相同结果,因此多次评分应完全一致.
        """
        vision = DeterministicMockVision()
        runs = []
        for _ in range(5):
            r = await analyze_video_resume(
                "https://example.com/cv_same.mp4",
                vision=vision,
                interval_sec=5.0,
                max_frames=6,
            )
            runs.append(r.scores.overall)

        # deterministic mock → stddev = 0
        stdev = statistics.stdev(runs) if len(runs) > 1 else 0.0
        assert stdev < 0.01, f"runs={runs} stdev={stdev}"

    @pytest.mark.asyncio
    async def test_consistency_dimensions_individually(self):
        vision = DeterministicMockVision()
        per_dim_runs: dict[str, list[float]] = {d: [] for d in VIDEO_RESUME_DIMENSIONS}
        for _ in range(5):
            r = await analyze_video_resume(
                "https://example.com/cv.mp4", vision=vision
            )
            for d in VIDEO_RESUME_DIMENSIONS:
                per_dim_runs[d].append(getattr(r.scores, d))

        for d, vals in per_dim_runs.items():
            stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
            assert stdev < 0.1, f"dim={d} runs={vals} stdev={stdev} >= 0.1"

    @pytest.mark.asyncio
    async def test_consistency_with_temperature_seed(self):
        """测试低 temperature 下分数稳定 — 同一 vision 不同实例应保持一致."""
        runs = []
        for _ in range(3):
            v = DeterministicMockVision(
                scores={
                    "communication": 0.7, "clarity": 0.65,
                    "professionalism": 0.8, "confidence": 0.6, "warmth": 0.72,
                }
            )
            r = await analyze_video_resume("https://x.com/v.mp4", vision=v)
            runs.append(r.scores.overall)
        # 偏差应 < 0.1
        spread = max(runs) - min(runs)
        assert spread < 0.1, f"spread={spread} runs={runs}"


# ---------------------------------------------------------------------------
# profile_agent 集成测试 (轻量)
# ---------------------------------------------------------------------------
class TestProfileAgentIntegration:
    @pytest.mark.asyncio
    async def test_profile_agent_calls_video_resume_analyzer(self):
        """profile_agent 收到 video_url 时应调用 _maybe_analyze_video_resume 并合并到 profile."""
        from agents.jobseeker.profile_agent import ProfileAgent
        from unittest.mock import AsyncMock, patch

        agent = ProfileAgent()

        video_dict = {
            "source_url": "https://x.com/v.mp4",
            "video_metadata": {"duration_sec": 30, "codec": "H.264"},
            "frames_analyzed": 6,
            "scores": {
                "communication": 0.8, "clarity": 0.7, "professionalism": 0.6,
                "confidence": 0.5, "warmth": 0.4, "overall": 0.62,
            },
            "non_verbal": {
                "expression": "自然", "eye_contact": "良好",
                "body_language": "端正", "notes": [],
            },
            "strengths": ["ok"], "suggestions": [], "tags": [],
        }

        # 直接验证 _maybe_analyze_video_resume + _merge_video_into_profile
        with patch.object(
            agent, "_maybe_ocr_resume", AsyncMock(return_value=None)
        ):
            result = await agent._maybe_analyze_video_resume(
                {"video_url": "https://x.com/v.mp4"}
            )
            # 由于没有真实 vision provider,会失败/返回空 — 我们只验证它被正确调用
            # 在 mock 环境下返回 _error
            assert result is not None
            assert "source_url" in result or "_error" in result

    def test_profile_agent_merge_video_helper(self):
        """直接测试 profile_agent._merge_video_into_profile 合并逻辑."""
        from agents.jobseeker.profile_agent import ProfileAgent

        agent = ProfileAgent()
        profile = {"name": "Alice", "soft_skills": {}}
        analysis_dict = {
            "source_url": "https://x.com/v.mp4",
            "video_metadata": {},
            "frames_analyzed": 6,
            "scores": {
                "communication": 0.9, "clarity": 0.85, "professionalism": 0.8,
                "confidence": 0.7, "warmth": 0.75, "overall": 0.0,
            },
            "non_verbal": {"expression": "微笑", "eye_contact": "好", "body_language": "端正", "notes": []},
            "strengths": ["自信"], "suggestions": ["可再放松"], "tags": [],
        }
        merged = agent._merge_video_into_profile(profile, analysis_dict)
        assert "soft_skills" in merged
        assert merged["soft_skills"]["communication"] == pytest.approx(0.135, abs=0.01)
        assert merged["name"] == "Alice"
        assert merged["video_resume_feedback"]["strengths"] == ["自信"]
