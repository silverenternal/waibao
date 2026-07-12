"""Candidate Rediscovery Service (T2406).

Detect dormant candidates in talent pool:
- Scan: 6+ months inactive candidates
- Evaluate: LLM-style scoring based on activity + new roles + profile fit
- Activation strategies: conservative / standard / aggressive

Pure logic — uses heuristics with optional LLM hook.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Protocol

logger = logging.getLogger("recruittech.service.rediscovery")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DORMANT_THRESHOLD_DAYS = 180  # 6 个月
ACTIVITY_WINDOW_DAYS = 365  # 1 年内活跃算 base 1.0

# 策略阈值 (rediscover_potential)
STRATEGY_THRESHOLDS = {
    "conservative": 0.75,  # 极高潜力才发
    "standard": 0.55,
    "aggressive": 0.35,
}


class ActivationStrategy(str, Enum):
    CONSERVATIVE = "conservative"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"


class Channel(str, Enum):
    IM = "im"
    EMAIL = "email"
    SMS = "sms"
    DINGTALK = "dingtalk"


# ---------------------------------------------------------------------------
# LLM 抽象 (注入式, 测试可用 stub)
# ---------------------------------------------------------------------------

class LLMJudge(Protocol):
    """LLM 评估接口 (生产可注入 OpenAI / Claude / Qwen)."""

    def evaluate(self, candidate: dict, new_roles: list[dict]) -> dict: ...


class HeuristicLLMJudge:
    """默认: 基于规则 + 关键词匹配的启发式评估器 (无外部依赖)."""

    def evaluate(self, candidate: dict, new_roles: list[dict]) -> dict:
        cand_skills = set(s.lower() for s in candidate.get("skills", []))
        cand_titles = set(t.lower() for t in candidate.get("job_titles", []))

        matched = []
        match_score = 0.0
        for role in new_roles:
            role_skills = set(s.lower() for s in role.get("required_skills", []))
            role_title = role.get("title", "").lower()
            overlap = cand_skills & role_skills
            title_match = 1.0 if any(w in role_title for w in cand_titles) else 0.0
            score = (len(overlap) / max(len(role_skills), 1)) * 0.6 + title_match * 0.4
            if score > 0.3:
                matched.append({
                    "role_id": role.get("id"),
                    "title": role.get("title"),
                    "score": round(score, 3),
                    "overlap_skills": list(overlap),
                })
                match_score = max(match_score, score)

        reason = self._build_reason(candidate, matched)
        return {
            "fit_score": round(match_score, 3),
            "matched_roles": matched,
            "reason": reason,
        }

    @staticmethod
    def _build_reason(candidate: dict, matched: list[dict]) -> str:
        name = candidate.get("name", "该候选人")
        if matched:
            top = matched[0]
            return (
                f"{name} 的技能 ({', '.join(top['overlap_skills'][:3])}) "
                f"与新职位「{top['title']}」高度匹配, 建议激活。"
            )
        return f"{name} 历史活跃但当前无强匹配职位, 建议发送轻量关怀。"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SleepyCandidate:
    id: str
    name: str
    email: Optional[str] = None
    last_active_at: Optional[str] = None
    dormant_days: int = 0
    job_titles: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    city: Optional[str] = None
    seniority: Optional[str] = None
    salary_expect: Optional[float] = None
    activity_score: float = 0.0
    fit_score: float = 0.0
    rediscover_potential: float = 0.0
    reason: str = ""
    recommended_roles: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class CandidateRediscoveryService:
    """沉睡库激活 service (singleton)."""

    _instance: Optional["CandidateRediscoveryService"] = None

    def __init__(self, judge: Optional[LLMJudge] = None):
        self._judge = judge or HeuristicLLMJudge()

    def __new__(cls, judge: Optional[LLMJudge] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._judge = judge or HeuristicLLMJudge()
        return cls._instance

    # ------------------------------------------------------------------
    # 1. 沉睡检测
    # ------------------------------------------------------------------

    def find_dormant(
        self,
        candidates: list[dict],
        new_roles: list[dict],
        threshold_days: int = DORMANT_THRESHOLD_DAYS,
        now: Optional[datetime] = None,
        strategy: str = ActivationStrategy.STANDARD.value,
    ) -> list[dict]:
        """扫描沉睡候选人, 按策略过滤 + LLM 评估."""
        now = now or datetime.now(timezone.utc)
        threshold = now - timedelta(days=threshold_days)
        sleepy: list[SleepyCandidate] = []

        for c in candidates:
            last_active = _parse_dt(c.get("last_active_at"))
            if last_active is None:
                # 从未活跃 - 也算沉睡 (按 1 年前计算)
                last_active = now - timedelta(days=ACTIVITY_WINDOW_DAYS)
            if last_active >= threshold:
                continue

            dormant_days = (now - last_active).days
            cand_dict = {
                "id": c.get("id"),
                "name": c.get("name", ""),
                "skills": c.get("skills", []),
                "job_titles": c.get("job_titles", []),
            }
            llm_eval = self._judge.evaluate(cand_dict, new_roles)
            activity_score = self._activity_score(dormant_days)
            fit_score = llm_eval.get("fit_score", 0.0)
            # 综合: 衰减 (沉睡越久分越低) + 匹配度
            if new_roles:
                potential = round(activity_score * 0.3 + fit_score * 0.7, 3)
            else:
                # 没有匹配职位时, 仅用活跃度评估
                potential = round(activity_score, 3)

            cand = SleepyCandidate(
                id=c.get("id"),
                name=c.get("name", ""),
                email=c.get("email"),
                last_active_at=c.get("last_active_at"),
                dormant_days=dormant_days,
                job_titles=c.get("job_titles", []),
                skills=c.get("skills", []),
                city=c.get("city"),
                seniority=c.get("seniority"),
                salary_expect=c.get("salary_expect"),
                activity_score=round(activity_score, 3),
                fit_score=fit_score,
                rediscover_potential=potential,
                reason=llm_eval.get("reason", ""),
                recommended_roles=llm_eval.get("matched_roles", []),
            )
            if potential >= STRATEGY_THRESHOLDS[strategy]:
                sleepy.append(cand)

        sleepy.sort(key=lambda c: c.rediscover_potential, reverse=True)
        return [c.to_dict() for c in sleepy]

    @staticmethod
    def _activity_score(dormant_days: int) -> float:
        """沉睡天数 → 活跃衰减分 (0-1)."""
        if dormant_days < 90:
            return 1.0
        if dormant_days >= 365 * 2:  # 2 年以上
            return 0.2
        # 线性衰减 90→730 days → 1.0→0.2
        ratio = (dormant_days - 90) / (730 - 90)
        return round(1.0 - ratio * 0.8, 3)

    # ------------------------------------------------------------------
    # 2. 策略选择
    # ------------------------------------------------------------------

    @staticmethod
    def strategy_for(potential: float) -> str:
        """根据潜力自动选策略."""
        if potential >= STRATEGY_THRESHOLDS["conservative"]:
            return ActivationStrategy.CONSERVATIVE.value
        if potential >= STRATEGY_THRESHOLDS["standard"]:
            return ActivationStrategy.STANDARD.value
        if potential >= STRATEGY_THRESHOLDS["aggressive"]:
            return ActivationStrategy.AGGRESSIVE.value
        return "skip"

    # ------------------------------------------------------------------
    # 3. 生成激活消息
    # ------------------------------------------------------------------

    def build_activation_message(
        self,
        candidate: dict,
        top_role: Optional[dict] = None,
    ) -> str:
        """构造激活消息 (基于候选人画像 + 推荐职位)."""
        name = candidate.get("name", "")
        top = top_role or (candidate.get("recommended_roles") or [{}])[0]
        if top and top.get("title"):
            msg = (
                f"您好 {name}, 我们最近注意到您可能对「{top.get('title')}」感兴趣 —— "
                f"这与您的背景 ({', '.join(candidate.get('skills', [])[:3])}) 非常匹配。\n"
                f"如有兴趣, 欢迎回复本消息或直接查看职位详情。"
            )
        else:
            msg = (
                f"您好 {name}, 距离上次沟通已经 {candidate.get('dormant_days', 0)} 天了, "
                f"市场上有一些新机会, 希望能跟您聊聊。"
            )
        return msg

    # ------------------------------------------------------------------
    # 4. 激活事件记录
    # ------------------------------------------------------------------

    def build_activation_log(
        self,
        candidate_id: str,
        triggered_by: str,
        strategy: str,
        channel: str = "im",
        candidate: Optional[dict] = None,
        message: Optional[str] = None,
    ) -> dict:
        """构造激活日志 (供 API / DB 写入)."""
        candidate = candidate or {}
        msg = message or self.build_activation_message(candidate)
        return {
            "candidate_id": candidate_id,
            "triggered_by": triggered_by,
            "strategy": strategy,
            "channel": channel,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "message": msg,
            "last_active_at": candidate.get("last_active_at"),
            "llm_eval": {
                "reason": candidate.get("reason"),
                "matched_roles": candidate.get("recommended_roles", []),
                "potential": candidate.get("rediscover_potential"),
            },
        }

    # ------------------------------------------------------------------
    # 5. 转化统计
    # ------------------------------------------------------------------

    def compute_stats(self, logs: list[dict]) -> dict:
        """汇总激活数据 + 转化率."""
        total = len(logs)
        converted = sum(1 for l in logs if l.get("converted"))
        by_strategy: dict[str, dict[str, int]] = {}
        by_channel: dict[str, int] = {}

        for l in logs:
            s = l.get("strategy", "unknown")
            cs = by_strategy.setdefault(s, {"total": 0, "converted": 0})
            cs["total"] += 1
            if l.get("converted"):
                cs["converted"] += 1
            ch = l.get("channel", "im")
            by_channel[ch] = by_channel.get(ch, 0) + 1

        # 综合转化率 + 分策略
        rate = round(converted / total, 3) if total else 0.0
        breakdown = {
            s: {
                "total": v["total"],
                "converted": v["converted"],
                "rate": round(v["converted"] / v["total"], 3) if v["total"] else 0.0,
            }
            for s, v in by_strategy.items()
        }
        return {
            "total_activations": total,
            "converted": converted,
            "overall_conversion_rate": rate,
            "by_strategy": breakdown,
            "by_channel": by_channel,
        }


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def get_rediscovery_service(judge: Optional[LLMJudge] = None) -> CandidateRediscoveryService:
    return CandidateRediscoveryService(judge)
