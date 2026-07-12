"""Tests for candidate rediscovery (T2406)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from services.integrations.candidate_rediscovery import (
    ActivationStrategy,
    CandidateRediscoveryService,
    DORMANT_THRESHOLD_DAYS,
    HeuristicLLMJudge,
    STRATEGY_THRESHOLDS,
    get_rediscovery_service,
)


@pytest.fixture
def svc():
    return get_rediscovery_service(judge=HeuristicLLMJudge())


# ---------------------------------------------------------------------------
# 1. 沉睡检测
# ---------------------------------------------------------------------------

class TestDormantScan:
    def test_filters_active(self, svc):
        now = datetime.now(timezone.utc)
        candidates = [
            {
                "id": "c1",
                "name": "Active",
                "last_active_at": (now - timedelta(days=30)).isoformat(),
                "skills": ["React"],
                "job_titles": ["前端"],
            },
        ]
        result = svc.find_dormant(candidates, [], now=now, strategy="aggressive")
        assert result == []

    def test_dormant_detected(self, svc):
        now = datetime.now(timezone.utc)
        candidates = [
            {
                "id": "c2",
                "name": "Sleepy",
                "last_active_at": (now - timedelta(days=200)).isoformat(),
                "skills": ["Python"],
                "job_titles": ["工程师"],
            },
        ]
        result = svc.find_dormant(candidates, [], now=now, strategy="aggressive")
        assert len(result) == 1
        assert result[0]["dormant_days"] >= 199

    def test_six_month_threshold(self, svc):
        """临界 180 天应被视为沉睡."""
        now = datetime.now(timezone.utc)
        cands = [
            {
                "id": "c3",
                "name": "Borderline",
                "last_active_at": (now - timedelta(days=181)).isoformat(),
                "skills": ["Go"],
                "job_titles": ["后端"],
            }
        ]
        result = svc.find_dormant(cands, [], now=now, strategy="aggressive")
        assert len(result) == 1

    def test_no_last_active_treated_as_dormant(self, svc):
        cands = [{"id": "c4", "name": "Unknown", "skills": ["JS"]}]
        result = svc.find_dormant(cands, [], strategy="aggressive")
        assert len(result) == 1
        assert result[0]["dormant_days"] >= DORMANT_THRESHOLD_DAYS


# ---------------------------------------------------------------------------
# 2. 策略过滤
# ---------------------------------------------------------------------------

class TestStrategyFilter:
    @pytest.fixture
    def candidates(self):
        now = datetime.now(timezone.utc)
        return [
            {
                "id": "high",
                "name": "高潜力",
                "last_active_at": (now - timedelta(days=200)).isoformat(),
                "skills": ["React", "TypeScript", "Next.js"],
                "job_titles": ["前端工程师"],
            },
            {
                "id": "low",
                "name": "低潜力",
                "last_active_at": (now - timedelta(days=400)).isoformat(),
                "skills": ["PHP"],
                "job_titles": ["网站管理员"],
            },
        ]

    def test_conservative_filters_low(self, svc, candidates):
        roles = [{"id": "r1", "title": "前端工程师", "required_skills": ["React"]}]
        result = svc.find_dormant(candidates, roles, strategy="conservative")
        # 高潜力的可能进来, 低潜力的不进
        ids = [r["id"] for r in result]
        assert "low" not in ids

    def test_aggressive_includes_more(self, svc, candidates):
        roles = [{"id": "r1", "title": "前端工程师", "required_skills": ["React"]}]
        aggressive = svc.find_dormant(candidates, roles, strategy="aggressive")
        standard = svc.find_dormant(candidates, roles, strategy="standard")
        assert len(aggressive) >= len(standard)

    def test_unknown_strategy_raises(self, svc, candidates):
        with pytest.raises(KeyError):
            svc.find_dormant(candidates, [], strategy="bogus")


# ---------------------------------------------------------------------------
# 3. LLM 评估
# ---------------------------------------------------------------------------

class TestLLMJudge:
    def test_match_by_skills(self):
        judge = HeuristicLLMJudge()
        cand = {
            "id": "c1",
            "name": "测试",
            "skills": ["React", "TypeScript"],
            "job_titles": ["前端"],
        }
        roles = [
            {"id": "r1", "title": "前端工程师", "required_skills": ["React", "TypeScript"]}
        ]
        result = judge.evaluate(cand, roles)
        assert result["fit_score"] > 0.5
        assert len(result["matched_roles"]) == 1

    def test_no_match(self):
        judge = HeuristicLLMJudge()
        cand = {"id": "c1", "name": "PHP 工程师", "skills": ["PHP"], "job_titles": []}
        roles = [
            {"id": "r1", "title": "前端工程师", "required_skills": ["React"]}
        ]
        result = judge.evaluate(cand, roles)
        assert result["fit_score"] <= 0.3

    def test_returns_reason(self):
        judge = HeuristicLLMJudge()
        cand = {"name": "张三", "skills": ["Python"], "job_titles": []}
        roles = [{"title": "Python 工程师", "required_skills": ["Python"]}]
        result = judge.evaluate(cand, roles)
        assert "张三" in result["reason"]


# ---------------------------------------------------------------------------
# 4. 激活消息
# ---------------------------------------------------------------------------

class TestMessage:
    def test_with_recommended_role(self, svc):
        cand = {
            "name": "Alice",
            "skills": ["React", "TS"],
            "recommended_roles": [{"title": "前端工程师"}],
        }
        msg = svc.build_activation_message(cand)
        assert "Alice" in msg
        assert "前端工程师" in msg

    def test_without_role(self, svc):
        cand = {"name": "Bob", "skills": [], "dormant_days": 200, "recommended_roles": []}
        msg = svc.build_activation_message(cand)
        assert "Bob" in msg
        assert "200" in msg


# ---------------------------------------------------------------------------
# 5. 策略选择
# ---------------------------------------------------------------------------

class TestStrategyChoice:
    def test_high_potential_conservative(self):
        s = CandidateRediscoveryService.strategy_for(0.85)
        assert s == "conservative"

    def test_mid_potential_standard(self):
        s = CandidateRediscoveryService.strategy_for(0.6)
        assert s == "standard"

    def test_low_potential_aggressive(self):
        s = CandidateRediscoveryService.strategy_for(0.4)
        assert s == "aggressive"

    def test_below_threshold_skip(self):
        s = CandidateRediscoveryService.strategy_for(0.1)
        assert s == "skip"


# ---------------------------------------------------------------------------
# 6. 激活日志
# ---------------------------------------------------------------------------

class TestActivationLog:
    def test_basic(self, svc):
        log = svc.build_activation_log(
            candidate_id="c1",
            triggered_by="hr-1",
            strategy="standard",
            channel="im",
            candidate={"name": "测试", "skills": ["React"]},
        )
        assert log["candidate_id"] == "c1"
        assert log["strategy"] == "standard"
        assert log["channel"] == "im"
        assert "activated_at" in log


# ---------------------------------------------------------------------------
# 7. 转化统计
# ---------------------------------------------------------------------------

class TestStats:
    def test_overall(self, svc):
        logs = [
            {"strategy": "s1", "converted": True, "channel": "im"},
            {"strategy": "s1", "converted": False, "channel": "im"},
            {"strategy": "s2", "converted": True, "channel": "email"},
        ]
        stats = svc.compute_stats(logs)
        assert stats["total_activations"] == 3
        assert stats["converted"] == 2
        assert stats["overall_conversion_rate"] == pytest.approx(2 / 3, abs=1e-3)

    def test_by_strategy(self, svc):
        logs = [
            {"strategy": "s1", "converted": True, "channel": "im"},
            {"strategy": "s1", "converted": True, "channel": "im"},
            {"strategy": "s1", "converted": False, "channel": "im"},
        ]
        stats = svc.compute_stats(logs)
        s1 = stats["by_strategy"]["s1"]
        assert s1["total"] == 3
        assert s1["converted"] == 2
        assert s1["rate"] == pytest.approx(2 / 3, abs=1e-3)

    def test_by_channel(self, svc):
        logs = [
            {"strategy": "s1", "converted": False, "channel": "im"},
            {"strategy": "s1", "converted": False, "channel": "im"},
            {"strategy": "s1", "converted": False, "channel": "email"},
        ]
        stats = svc.compute_stats(logs)
        assert stats["by_channel"]["im"] == 2
        assert stats["by_channel"]["email"] == 1

    def test_empty(self, svc):
        stats = svc.compute_stats([])
        assert stats["total_activations"] == 0
        assert stats["converted"] == 0
        assert stats["overall_conversion_rate"] == 0.0


# ---------------------------------------------------------------------------
# 8. 活跃衰减
# ---------------------------------------------------------------------------

class TestActivityDecay:
    def test_recent_high_score(self, svc):
        # < 90 天: 1.0
        assert svc._activity_score(60) == 1.0

    def test_long_dormant_low_score(self, svc):
        # >= 730 天 (2年): 0.2
        assert svc._activity_score(800) == 0.2

    def test_linear_decay(self, svc):
        # 中间值: 1.0 - ratio * 0.8
        # ratio = (365 - 90) / (730 - 90) = 275/640 ≈ 0.43
        # score ≈ 1.0 - 0.43 * 0.8 ≈ 0.656
        s = svc._activity_score(365)
        assert 0.6 < s < 0.7
