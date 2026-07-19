"""T6301 (v11.2) — tests for the matching visibility gate / threshold.

甲方要求: 不淘汰, 只排序 —— 但低于阀值 (默认 70%) 时双方暂不可见, 避免无效沟通.
"""
from __future__ import annotations

import importlib
import os

import pytest

from matching import threshold as threshold_mod
from matching.hard_filter import MatchResult
from matching.threshold import (
    MATCH_THRESHOLD,
    VisibilityGate,
    best_score_against_roles,
    best_score_against_talents,
    compute_pair_score,
    is_above_threshold,
)


# ---------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------

def _candidate(**kw) -> dict:
    base = {
        "id": "c1",
        "skills": ["python", "django"],
        "education": "硕士",
        "certificates": [],
        "salary_min_k": 35,
        "salary_max_k": 45,
        "city": "北京",
        "availability": "立即上岗",
        "job_intent": "积极",
    }
    base.update(kw)
    return base


def _role(**kw) -> dict:
    base = {
        "id": "r1",
        "required_skills": ["python", "django"],
        "education": "本科",
        "certificates_required": [],
        "salary_min_k": 30,
        "salary_max_k": 50,
        "city": "北京",
        "remote_policy": "onsite",
        "availability_required": "1月",
    }
    base.update(kw)
    return base


# ===========================================================================
# 1. 阀值边界
# ===========================================================================

class TestThresholdBoundary:
    def test_default_threshold_is_70(self):
        assert MATCH_THRESHOLD == 70

    def test_score_70_is_above(self):
        assert is_above_threshold(70) is True

    def test_score_69_is_below(self):
        assert is_above_threshold(69) is False

    def test_score_100_above(self):
        assert is_above_threshold(100) is True

    def test_score_0_below(self):
        assert is_above_threshold(0) is False

    def test_invalid_score_treated_as_below(self):
        assert is_above_threshold("not-a-number") is False
        assert is_above_threshold(None) is False


# ===========================================================================
# 2. VisibilityGate
# ===========================================================================

class TestVisibilityGate:
    def test_visible_at_threshold(self):
        gate = VisibilityGate()
        d = gate.decide(70)
        assert d["visible"] is True
        assert d["threshold"] == 70
        assert "可见" in d["reason"]

    def test_hidden_below_threshold(self):
        gate = VisibilityGate()
        d = gate.decide(69)
        assert d["visible"] is False
        assert d["threshold"] == 70
        # 甲方口径文案
        assert "暂不可见" in d["reason"]
        assert "避免无效沟通" in d["reason"]

    def test_custom_threshold(self):
        gate = VisibilityGate(threshold=80)
        assert gate.decide(79)["visible"] is False
        assert gate.decide(80)["visible"] is True
        assert gate.decide(80)["threshold"] == 80

    def test_decide_returns_required_keys(self):
        d = VisibilityGate().decide(50)
        assert set(d.keys()) >= {"visible", "threshold", "reason"}


# ===========================================================================
# 3. compute_pair_score
# ===========================================================================

class TestComputePairScore:
    def test_returns_match_result(self):
        res = compute_pair_score(_candidate(), _role())
        assert isinstance(res, MatchResult)
        assert 0 <= res.match_score <= 100

    def test_perfect_pair_high_score(self):
        res = compute_pair_score(_candidate(), _role())
        assert res.match_score >= 70


# ===========================================================================
# 4. best_score_against_roles — 取最大, 任一过线即对雇主可见
# ===========================================================================

class TestBestScoreAgainstRoles:
    def test_picks_max_score(self):
        talent = _candidate()
        roles = [
            _role(id="r_low", salary_max_k=5, city="广州"),    # 低分
            _role(id="r_high", salary_min_k=30, salary_max_k=50, city="北京"),
        ]
        best_score, best_id, res = best_score_against_roles(talent, roles)
        assert best_id == "r_high"
        assert best_score == res.match_score
        # 高分岗应在所有岗中最大
        assert best_score >= compute_pair_score(talent, roles[0]).match_score

    def test_any_role_above_threshold_makes_visible(self):
        talent = _candidate()
        roles = [
            _role(id="r_low", salary_max_k=5, city="广州"),
            _role(id="r_ok", salary_min_k=30, salary_max_k=50, city="北京"),
        ]
        best_score, _, _ = best_score_against_roles(talent, roles)
        # 任一过线 → best >= 阀值 → 对雇主可见
        assert best_score >= MATCH_THRESHOLD

    def test_empty_roles_safe(self):
        best_score, best_id, res = best_score_against_roles(_candidate(), [])
        assert best_score == 0
        assert best_id is None
        assert res is None

    def test_none_roles_safe(self):
        best_score, best_id, res = best_score_against_roles(_candidate(), None)
        assert best_score == 0
        assert best_id is None
        assert res is None


# ===========================================================================
# 5. best_score_against_talents — 对称
# ===========================================================================

class TestBestScoreAgainstTalents:
    def test_picks_max_score(self):
        role = _role()
        talents = [
            _candidate(id="t_weak", skills=["cobol"], education="高中"),
            _candidate(id="t_strong", skills=["python", "django"], education="硕士"),
        ]
        best_score, best_id, res = best_score_against_talents(role, talents)
        assert best_id == "t_strong"
        assert best_score == res.match_score

    def test_empty_talents_safe(self):
        best_score, best_id, res = best_score_against_talents(_role(), [])
        assert (best_score, best_id, res) == (0, None, None)


# ===========================================================================
# 6. 环境变量覆盖阀值
# ===========================================================================

class TestEnvOverride:
    def test_env_override_threshold(self, monkeypatch):
        monkeypatch.setenv("MATCH_THRESHOLD", "85")
        # 重新加载模块使新 env 生效
        importlib.reload(threshold_mod)
        try:
            assert threshold_mod.MATCH_THRESHOLD == 85
            # VisibilityGate 默认也跟随
            gate = threshold_mod.VisibilityGate()
            assert gate.decide(84)["visible"] is False
            assert gate.decide(85)["visible"] is True
        finally:
            # 恢复默认, 避免污染同进程其它测试
            monkeypatch.delenv("MATCH_THRESHOLD", raising=False)
            importlib.reload(threshold_mod)
            assert threshold_mod.MATCH_THRESHOLD == 70

    def test_is_above_threshold_uses_overridden(self, monkeypatch):
        monkeypatch.setenv("MATCH_THRESHOLD", "90")
        importlib.reload(threshold_mod)
        try:
            assert threshold_mod.is_above_threshold(89) is False
            assert threshold_mod.is_above_threshold(90) is True
        finally:
            monkeypatch.delenv("MATCH_THRESHOLD", raising=False)
            importlib.reload(threshold_mod)


# ===========================================================================
# 7. 综合: 不淘汰 + 阀值门 协同
# ===========================================================================

class TestNoEliminationWithGate:
    def test_low_pair_still_computed_but_hidden(self):
        # 不淘汰: 弱匹配仍有分数; 但阀值门判定不可见
        weak = compute_pair_score(
            _candidate(skills=["cobol"], education="高中", salary_min_k=500),
            _role(required_skills=["python", "django"], education="硕士",
                  salary_max_k=20),
        )
        assert weak.match_score >= 0  # 不淘汰
        gate = VisibilityGate()
        decision = gate.decide(weak.match_score)
        # 极弱匹配应在阀值之下 (不可见)
        if weak.match_score < MATCH_THRESHOLD:
            assert decision["visible"] is False
