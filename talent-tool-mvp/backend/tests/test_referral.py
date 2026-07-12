"""Tests for referral service (T2405)."""
from __future__ import annotations

import pytest

from services.employer.referral_service import (
    DEFAULT_BONUS_CNY,
    POINTS_HIRED,
    POINTS_SUBMIT,
    ReferralService,
    ReferralStatus,
    STATUS_FLOW,
    get_referral_service,
)


@pytest.fixture
def svc():
    return get_referral_service()


# ---------------------------------------------------------------------------
# 1. 创建 + 防作弊
# ---------------------------------------------------------------------------

class TestCreate:
    def test_basic(self, svc):
        ref = svc.create_referral(
            referrer_id="emp-1",
            candidate_email="alice@example.com",
            candidate_name="Alice",
            role_id="role-1",
        )
        assert ref["candidate_email"] == "alice@example.com"
        assert ref["status"] == ReferralStatus.PENDING.value

    def test_email_normalized(self, svc):
        ref = svc.create_referral(
            referrer_id="emp-1",
            candidate_email="Alice@Example.COM",
        )
        assert ref["candidate_email"] == "alice@example.com"

    def test_invalid_email_raises(self, svc):
        with pytest.raises(ValueError, match="invalid email"):
            svc.create_referral(referrer_id="emp-1", candidate_email="not-an-email")

    def test_duplicate_email_role_raises(self, svc):
        existing = [
            {
                "referrer_id": "emp-1",
                "candidate_email": "alice@example.com",
                "role_id": "role-1",
            }
        ]
        with pytest.raises(ValueError, match="duplicate referral"):
            svc.create_referral(
                referrer_id="emp-1",
                candidate_email="alice@example.com",
                role_id="role-1",
                existing_referrals=existing,
            )

    def test_different_role_allowed(self, svc):
        existing = [
            {
                "referrer_id": "emp-1",
                "candidate_email": "alice@example.com",
                "role_id": "role-1",
            }
        ]
        ref = svc.create_referral(
            referrer_id="emp-1",
            candidate_email="alice@example.com",
            role_id="role-2",
            existing_referrals=existing,
        )
        assert ref["candidate_email"] == "alice@example.com"

    def test_different_referrer_allowed(self, svc):
        existing = [
            {
                "referrer_id": "emp-1",
                "candidate_email": "alice@example.com",
                "role_id": "role-1",
            }
        ]
        ref = svc.create_referral(
            referrer_id="emp-2",
            candidate_email="alice@example.com",
            role_id="role-1",
            existing_referrals=existing,
        )
        assert ref["referrer_id"] == "emp-2"


# ---------------------------------------------------------------------------
# 2. 状态推进
# ---------------------------------------------------------------------------

class TestStatusFlow:
    def test_full_flow(self, svc):
        sid = "ref-1"
        cur = "pending"
        for target in ["reviewed", "interview", "offered", "hired", "rewarded"]:
            res = svc.advance_status(sid, cur, target)
            assert res["new_status"] == target
            cur = target
        # 转 reward 应包含 bonus
        assert res["bonus_amount"] == DEFAULT_BONUS_CNY

    def test_interview_at_set(self, svc):
        res = svc.advance_status("r", "reviewed", "interview")
        assert "interview_at" in res

    def test_hired_at_set(self, svc):
        res = svc.advance_status("r", "offered", "hired")
        assert "hired_at" in res

    def test_invalid_target_raises(self, svc):
        with pytest.raises(ValueError, match="invalid target_status"):
            svc.advance_status("r", "pending", "bogus")

    def test_already_rewarded_raises(self, svc):
        with pytest.raises(ValueError, match="already rewarded"):
            svc.advance_status("r", "rewarded", "pending")

    def test_rejected_raises(self, svc):
        with pytest.raises(ValueError, match="is rejected"):
            svc.advance_status("r", "rejected", "pending")


# ---------------------------------------------------------------------------
# 3. 拒绝
# ---------------------------------------------------------------------------

class TestReject:
    def test_reject(self, svc):
        res = svc.reject("r-1", "不匹配岗位要求")
        assert res["status"] == "rejected"
        assert res["reason"] == "不匹配岗位要求"
        assert "rejected_at" in res


# ---------------------------------------------------------------------------
# 4. 积分
# ---------------------------------------------------------------------------

class TestPoints:
    def test_submission_points(self, svc):
        p = svc.award_points("emp-1", "ref-1", "submission")
        assert p["points"] == POINTS_SUBMIT

    def test_interview_points(self, svc):
        p = svc.award_points("emp-1", "ref-1", "interview")
        assert p["points"] == 20

    def test_hired_points(self, svc):
        p = svc.award_points("emp-1", "ref-1", "hired")
        assert p["points"] == POINTS_HIRED

    def test_invalid_reason(self, svc):
        with pytest.raises(ValueError, match="invalid reason"):
            svc.award_points("emp-1", "ref-1", "bogus")


# ---------------------------------------------------------------------------
# 5. 现金
# ---------------------------------------------------------------------------

class TestBonus:
    def test_default(self, svc):
        b = svc.grant_bonus("emp-1", "ref-1")
        assert b["amount"] == DEFAULT_BONUS_CNY
        assert b["currency"] == "CNY"

    def test_custom(self, svc):
        b = svc.grant_bonus("emp-1", "ref-1", 8000, "CNY")
        assert b["amount"] == 8000

    def test_zero_raises(self, svc):
        with pytest.raises(ValueError):
            svc.grant_bonus("emp-1", "ref-1", 0)

    def test_negative_raises(self, svc):
        with pytest.raises(ValueError):
            svc.grant_bonus("emp-1", "ref-1", -100)


# ---------------------------------------------------------------------------
# 6. 排行榜
# ---------------------------------------------------------------------------

class TestLeaderboard:
    def test_ranking(self, svc):
        records = [
            {"referrer_id": "A", "points": 100},
            {"referrer_id": "B", "points": 250},
            {"referrer_id": "C", "points": 50},
        ]
        lb = svc.leaderboard(records)
        assert lb[0]["referrer_id"] == "B"
        assert lb[1]["referrer_id"] == "A"
        assert lb[2]["referrer_id"] == "C"

    def test_limit(self, svc):
        records = [
            {"referrer_id": f"R{i}", "points": 100 - i}
            for i in range(20)
        ]
        lb = svc.leaderboard(records, limit=5)
        assert len(lb) == 5

    def test_aggregate(self, svc):
        records = [
            {"referrer_id": "A", "points": 10},
            {"referrer_id": "A", "points": 20},
            {"referrer_id": "A", "points": 5},
        ]
        lb = svc.leaderboard(records)
        assert lb[0]["referrer_id"] == "A"
        assert lb[0]["total_points"] == 35


# ---------------------------------------------------------------------------
# 7. 员工汇总
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_counts(self, svc):
        referrals = [
            {"status": "pending", "bonus_amount": 0},
            {"status": "interview", "bonus_amount": 0},
            {"status": "hired", "bonus_amount": 5000},
            {"status": "rewarded", "bonus_amount": 5000},
        ]
        points = [
            {"points": 5}, {"points": 20}, {"points": 100},
        ]
        s = svc.summarize_referrer("emp-1", referrals, points)
        assert s["total_referrals"] == 4
        assert s["successful_hires"] == 2
        assert s["total_points"] == 125
        assert s["rewards_earned"] == 5000

    def test_empty(self, svc):
        s = svc.summarize_referrer("emp-1", [], [])
        assert s["total_referrals"] == 0
        assert s["total_points"] == 0
        assert s["rewards_earned"] == 0
