"""Referral Service (T2405).

Internal referral system:
- Status flow: pending → reviewed → interview → offered → hired → rewarded
- Reward: 5000 CNY cash + 100 points per hire
- Anti-fraud: 同一候选人邮箱 + 同一岗位 只能推荐一次
- Points ledger: +5 submit, +20 interview, +100 hired

Pure logic; persistence handled by callers via Supabase.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("recruittech.service.referral")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BONUS_CNY = 5000.0
DEFAULT_BONUS_CURRENCY = "CNY"

# 推荐状态机
STATUS_FLOW = [
    "pending",
    "reviewed",
    "interview",
    "offered",
    "hired",
    "rewarded",
]

# 积分规则
POINTS_SUBMIT = 5
POINTS_INTERVIEW = 20
POINTS_HIRED = 100

POINTS_RULES = {
    "submission": POINTS_SUBMIT,
    "interview": POINTS_INTERVIEW,
    "hired": POINTS_HIRED,
}

# 邮件正则
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


class ReferralStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REWARDED = "rewarded"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Referral:
    referrer_id: str
    candidate_email: str
    candidate_name: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_id: Optional[str] = None
    role_id: Optional[str] = None
    job_title: Optional[str] = None
    notes: Optional[str] = None
    status: str = ReferralStatus.PENDING.value
    id: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReferralService:
    _instance: Optional["ReferralService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # 1. 创建推荐 (带防作弊)
    # ------------------------------------------------------------------

    def create_referral(
        self,
        referrer_id: str,
        candidate_email: str,
        role_id: Optional[str] = None,
        job_title: Optional[str] = None,
        candidate_name: Optional[str] = None,
        candidate_phone: Optional[str] = None,
        notes: Optional[str] = None,
        existing_referrals: Optional[list[dict]] = None,
    ) -> dict:
        """员工推荐候选人; 返回 referral dict; 若已有重复则抛 ValueError."""
        if not EMAIL_RE.match(candidate_email):
            raise ValueError(f"invalid email: {candidate_email}")

        existing = existing_referrals or []
        for r in existing:
            if (
                r.get("candidate_email", "").lower() == candidate_email.lower()
                and r.get("role_id") == role_id
                and r.get("referrer_id") == referrer_id
            ):
                raise ValueError(
                    f"duplicate referral: same candidate+role already referred"
                )

        ref = Referral(
            referrer_id=referrer_id,
            candidate_email=candidate_email.lower(),
            candidate_name=candidate_name,
            candidate_phone=candidate_phone,
            role_id=role_id,
            job_title=job_title,
            notes=notes,
            status=ReferralStatus.PENDING.value,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "referral.created referrer=%s candidate=%s role=%s",
            referrer_id,
            candidate_email,
            role_id,
        )
        return ref.to_dict()

    # ------------------------------------------------------------------
    # 2. 状态推进
    # ------------------------------------------------------------------

    def advance_status(
        self,
        referral_id: str,
        current_status: str,
        target_status: str,
        hr_notes: Optional[str] = None,
    ) -> dict:
        """HR 推进状态, 自动校验合法转移."""
        if current_status == ReferralStatus.REWARDED.value:
            raise ValueError("referral already rewarded, cannot advance")
        if current_status == ReferralStatus.REJECTED.value:
            raise ValueError("referral is rejected, cannot advance")
        if target_status not in STATUS_FLOW + ["rejected"]:
            raise ValueError(f"invalid target_status: {target_status}")

        now = datetime.now(timezone.utc).isoformat()
        result = {
            "referral_id": referral_id,
            "old_status": current_status,
            "new_status": target_status,
            "hr_notes": hr_notes or "",
            "advanced_at": now,
        }
        if target_status == ReferralStatus.INTERVIEW.value:
            result["interview_at"] = now
        elif target_status == ReferralStatus.OFFERED.value:
            result["offered_at"] = now
        elif target_status == ReferralStatus.HIRED.value:
            result["hired_at"] = now
        elif target_status == ReferralStatus.REWARDED.value:
            result["reward_at"] = now
            result["bonus_amount"] = DEFAULT_BONUS_CNY
            result["bonus_currency"] = DEFAULT_BONUS_CURRENCY
        return result

    # ------------------------------------------------------------------
    # 3. 拒绝 (HR)
    # ------------------------------------------------------------------

    def reject(
        self,
        referral_id: str,
        reason: str,
    ) -> dict:
        return {
            "referral_id": referral_id,
            "status": ReferralStatus.REJECTED.value,
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 4. 积分 (HR 触发)
    # ------------------------------------------------------------------

    def award_points(
        self,
        referrer_id: str,
        referral_id: str,
        reason: str,
    ) -> dict:
        """按规则加分."""
        if reason not in POINTS_RULES:
            raise ValueError(f"invalid reason: {reason}; must be one of {list(POINTS_RULES.keys())}")
        pts = POINTS_RULES[reason]
        return {
            "referrer_id": referrer_id,
            "referral_id": referral_id,
            "points": pts,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 5. 现金奖励
    # ------------------------------------------------------------------

    def grant_bonus(
        self,
        referrer_id: str,
        referral_id: str,
        amount: float = DEFAULT_BONUS_CNY,
        currency: str = DEFAULT_BONUS_CURRENCY,
    ) -> dict:
        """发放现金奖励 (默认 5000 CNY)."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        return {
            "referrer_id": referrer_id,
            "referral_id": referral_id,
            "amount": amount,
            "currency": currency,
            "status": "pending",  # 财务审批后才 paid
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 6. 排行榜
    # ------------------------------------------------------------------

    def leaderboard(
        self,
        points_records: list[dict],
        limit: int = 10,
    ) -> list[dict]:
        """积分排行."""
        totals: dict[str, int] = {}
        for r in points_records:
            rid = r.get("referrer_id", "")
            if not rid:
                continue
            totals[rid] = totals.get(rid, 0) + r.get("points", 0)
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [
            {"rank": i + 1, "referrer_id": rid, "total_points": pts}
            for i, (rid, pts) in enumerate(ranked)
        ]

    # ------------------------------------------------------------------
    # 7. 聚合
    # ------------------------------------------------------------------

    def summarize_referrer(
        self,
        referrer_id: str,
        referrals: list[dict],
        points: list[dict],
    ) -> dict:
        """员工视图: 我的推荐 + 积分."""
        total = len(referrals)
        status_count: dict[str, int] = {}
        for r in referrals:
            s = r.get("status", "pending")
            status_count[s] = status_count.get(s, 0) + 1
        total_points = sum(p.get("points", 0) for p in points)
        return {
            "referrer_id": referrer_id,
            "total_referrals": total,
            "status_breakdown": status_count,
            "successful_hires": status_count.get(ReferralStatus.HIRED.value, 0)
            + status_count.get(ReferralStatus.REWARDED.value, 0),
            "total_points": total_points,
            "rewards_earned": sum(
                r.get("bonus_amount", 0)
                for r in referrals
                if r.get("status") == ReferralStatus.REWARDED.value
            ),
        }


def get_referral_service() -> ReferralService:
    return ReferralService()
