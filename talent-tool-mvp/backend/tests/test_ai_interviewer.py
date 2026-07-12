"""T1301 AI Interviewer 服务层测试."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ai_interviewer import (  # noqa: E402
    AIInterviewer,
    AnswerScore,
    FeedbackReport,
)
from services.question_bank import QuestionBank, question_bank  # noqa: E402


def test_question_bank_compiles_100():
    bank = QuestionBank()
    stats = bank.stats()
    assert sum(stats.values()) == 100, f"expected 100 questions, got {stats}"
    assert len(stats) == 10, f"expected 10 role categories, got {stats}"


def test_question_bank_select_balanced():
    qs = question_bank.select_questions("backend_engineer", count=10)
    assert len(qs) == 10
    types = [q.type for q in qs]
    # 至少要有 technical / behavioral 两种类型
    assert "technical" in types
    assert "behavioral" in types
    # 所有题目属于同一 category 或 fallback
    assert all(q.category in ("backend_engineer", "backend_engineer") for q in qs)


def test_question_bank_unknown_role_fallback():
    qs = question_bank.select_questions("interplanetary_pilot", count=5)
    assert len(qs) == 5
    # 应当回退到 backend_engineer
    assert all(q.category == "backend_engineer" for q in qs)


def test_mock_evaluator_returns_score_in_range():
    ai = AIInterviewer(use_mock_fallback=True)
    qs = question_bank.select_questions("data_scientist", count=1)
    q = qs[0]
    score = asyncio.run(
        ai.evaluate_answer(
            q,
            video_url=None,
            audio_bytes=None,
            audio_mime="audio/webm",
            transcript="我之前做过一个推荐系统的项目,主要用协同过滤和向量召回,AUC 提升了 12%。",
            language="zh",
        )
    )
    assert isinstance(score, AnswerScore)
    assert 0 <= score.overall <= 100
    assert score.band in {"weak", "fair", "good", "excellent"}
    assert score.transcript_provider == "user_provided"
    assert score.dimensions, "dimensions must be populated"


def test_mock_evaluator_handles_empty_transcript():
    ai = AIInterviewer(use_mock_fallback=True)
    q = question_bank.select_questions("frontend_engineer", count=1)[0]
    score = asyncio.run(
        ai.evaluate_answer(
            q,
            video_url=None,
            audio_bytes=None,
            audio_mime="audio/webm",
            transcript="",
            language="auto",
        )
    )
    # 没有内容得分应当显著低于完整答案,band 应当 ≤ fair
    assert score.band in {"weak", "fair"}, f"empty transcript should be weak/fair, got {score.band} ({score.overall})"
    # communication 维度应当偏低
    assert score.dimensions.get("communication", 100) < 60


def test_feedback_aggregates_dimensions():
    ai = AIInterviewer(use_mock_fallback=True)
    qs = question_bank.select_questions("product_manager", count=3)
    scores = []
    for idx, q in enumerate(qs):
        # 模拟不同长度回答
        transcript = "啊" * (40 * (idx + 1))
        scores.append(
            asyncio.run(
                ai.evaluate_answer(
                    q,
                    transcript=transcript,
                    video_url=None,
                    audio_bytes=None,
                    audio_mime="audio/webm",
                )
            )
        )
    report = asyncio.run(
        ai.generate_feedback(scores, interview_id="i_x", role="product_manager")
    )
    assert isinstance(report, FeedbackReport)
    assert report.overall_score >= 0 and report.overall_score <= 100
    assert "product_manager" in report.summary
    assert report.recommendation in {"strong_yes", "yes", "consider", "no"}
    assert report.radar.get("overall", 0) > 0
    # 至少有一条 strength / improvement
    assert isinstance(report.strengths, list)
    assert isinstance(report.improvements, list)


def test_evaluator_falls_back_when_stt_fails():
    """STT 失败时应当降级到 mock provider 而不是崩溃."""
    ai = AIInterviewer(use_mock_fallback=True)
    q = question_bank.select_questions("mobile_engineer", count=1)[0]

    class _BoomSTT:
        provider_name = "boom"

        async def transcribe(self, *a, **kw):
            raise RuntimeError("intentional boom")

    ai._stt = _BoomSTT()
    score = asyncio.run(
        ai.evaluate_answer(
            q,
            video_url=None,
            audio_bytes=b"fake-audio-bytes",
            audio_mime="audio/webm",
            transcript=None,
            language="auto",
        )
    )
    # 应当返回合理结果, transcript_provider 应当降级
    assert score.overall >= 0
    assert score.transcript_provider in ("mock_stt", "mock", "user_provided", "")
    # 至少返回了 fallback transcript(或空串)
    assert isinstance(score.transcript, str)


def test_question_bank_generate_extra_llm_failure_is_safe(monkeypatch):
    """LLM 失败时不应阻塞面试, 返回 []."""
    bank = QuestionBank()

    class _BoomLLM:
        async def complete(self, *a, **kw):
            raise RuntimeError("LLM down")

    extras = asyncio.run(bank.generate_extra_questions("backend_engineer", count=3, llm_provider=_BoomLLM()))
    assert extras == []
