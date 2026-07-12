"""T1702 — Pilot 试用框架服务层 (v3.0).

集中封装 ``pilot_programs`` 表的业务方法,供 API / 报告生成 / 脚本复用:

- ``create_program``      : 创建 pilot program
- ``invite``              : 邀请用户加入 program (转调 ``pilot_invitation``)
- ``get_stats``           : 聚合统计 (邀请/反馈/NPS/活跃度/Top 痛点)
- ``end_program``         : 关闭 program,记录 ``ended_at`` 与最终 NPS
- ``generate_report``     : 拉取完整报告数据 dict (供 PDF / Dashboard 复用)
- ``list_programs`` / ``get_program`` : 只读辅助

设计目标: NPS ≥ 40 / 周活 ≥ 70% / Top 痛点 ≤ 5.
所有时间统一 UTC ISO-8601.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from api.deps import get_supabase_admin
from services.integrations.pilot_invitation import (
    DEFAULT_TTL_DAYS,
    Invitation,
    create_invitation,
)

logger = logging.getLogger("recruittech.services.pilot_service")

# ---------------------------------------------------------------------------
# 常量: NPS 阈值 (Bain & Co. 经典定义)
# ---------------------------------------------------------------------------
PROMOTER_THRESHOLD = 9   # score >= 9
PASSIVE_THRESHOLD = 7    # 6 < score < 9
# detractor: score <= 6

# Top 痛点列表默认上限 (反馈分类聚合)
TOP_PAIN_POINTS_LIMIT = 5

# 周活阈值: WAC ≥ 70% 视为通过
WEEKLY_ACTIVE_TARGET = 0.70
NPS_TARGET = 40

# Program 状态
PROGRAM_STATUSES = ("recruiting", "active", "completed", "cancelled")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProgramStats:
    """试用统计聚合."""

    program_id: str
    invitations_total: int = 0
    invitations_accepted: int = 0
    invitations_pending: int = 0
    invitations_expired: int = 0
    active_users: int = 0
    weekly_active_users: int = 0
    weekly_active_rate: Optional[float] = None
    nps: Optional[float] = None
    nps_responses: int = 0
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    feedback_total: int = 0
    feedback_by_category: dict[str, int] = field(default_factory=dict)
    feedback_by_feature: dict[str, int] = field(default_factory=dict)
    top_pain_points: list[dict[str, Any]] = field(default_factory=list)
    targets_met: dict[str, bool] = field(default_factory=dict)
    target_nps: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PilotReport:
    """完整 Pilot 报告 (供 PDF / Dashboard / 邮件分享)."""

    program_id: str
    program_name: str
    organisation_name: Optional[str]
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    target_nps: int
    target_weekly_active: float
    generated_at: str
    stats: ProgramStats
    feedback_samples: list[dict[str, Any]] = field(default_factory=list)
    invitation_breakdown: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "program_name": self.program_name,
            "organisation_name": self.organisation_name,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "target_nps": self.target_nps,
            "target_weekly_active": self.target_weekly_active,
            "generated_at": self.generated_at,
            "stats": self.stats.to_dict(),
            "feedback_samples": self.feedback_samples,
            "invitation_breakdown": self.invitation_breakdown,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def compute_nps(scores: Iterable[int | None]) -> dict[str, Any]:
    """从 NPS 分数列表计算 promoter / passive / detractor / NPS.

    Returns:
        ``{nps, promoters, passives, detractors, responses}``
    """
    promoters = passives = detractors = responses = 0
    for s in scores:
        if s is None:
            continue
        responses += 1
        if s >= PROMOTER_THRESHOLD:
            promoters += 1
        elif s <= PASSIVE_THRESHOLD - 1:
            detractors += 1
        else:
            passives += 1
    if responses == 0:
        return {"nps": None, "promoters": 0, "passives": 0, "detractors": 0, "responses": 0}
    nps = round((promoters - detractors) / responses * 100, 1)
    return {
        "nps": nps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "responses": responses,
    }


def _aggregate_categories(feedbacks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in feedbacks:
        cat = (f.get("category") or "other").strip()
        if not cat:
            cat = "other"
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _aggregate_features(feedbacks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in feedbacks:
        feat = (f.get("feature_used") or "").strip()
        if not feat:
            continue
        counts[feat] = counts.get(feat, 0) + 1
    return counts


def _top_pain_points(feedbacks: list[dict[str, Any]], limit: int = TOP_PAIN_POINTS_LIMIT) -> list[dict[str, Any]]:
    """Top 痛点 = 反馈中提及的高频痛点短语 (从 comment 提取关键词).

    简化策略:
      1. 优先取 category in ('bug', 'feature_request', 'complaint')
      2. 按 comment 简单分词 + 频次聚合
      3. 输出 [{tag, count, samples: [...]}] 最多 limit 条
    """
    import re
    from collections import Counter

    stopwords = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "个",
        "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没", "看", "好",
        "the", "a", "an", "is", "are", "was", "were", "i", "we", "you", "they", "to",
        "of", "and", "or", "but", "it", "this", "that", "in", "on", "for", "with",
    }
    buckets: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    for f in feedbacks:
        cat = f.get("category")
        if cat not in {"bug", "feature_request", "complaint"}:
            continue
        comment = (f.get("comment") or "").strip()
        if not comment:
            continue
        # 中文 + 英文混合: 按非字母数字连续块切词,长度 2-12
        tokens = re.findall(r"[\w一-鿿]{2,12}", comment.lower())
        for tok in tokens:
            if tok in stopwords:
                continue
            buckets[tok] += 1
            samples.setdefault(tok, []).append(comment[:120])
    out: list[dict[str, Any]] = []
    for tag, count in buckets.most_common(limit):
        out.append({
            "tag": tag,
            "count": count,
            "category_breakdown": {},  # 留作 future 扩展
            "samples": samples[tag][:3],
        })
    return out


def _compute_targets_met(stats: ProgramStats) -> dict[str, bool]:
    """计算目标达成情况."""
    nps_ok = stats.nps is not None and stats.nps >= NPS_TARGET
    wau_ok = (
        stats.weekly_active_rate is not None
        and stats.weekly_active_rate >= WEEKLY_ACTIVE_TARGET
    )
    pain_ok = len(stats.top_pain_points) <= TOP_PAIN_POINTS_LIMIT
    return {
        "nps": nps_ok,
        "weekly_active": wau_ok,
        "top_pain_points": pain_ok,
        "all": nps_ok and wau_ok and pain_ok,
    }


def _compute_weekly_active(
    *,
    invitations: list[dict[str, Any]],
    events: list[dict[str, Any]],
    days: int = 7,
) -> tuple[int, float]:
    """基于 ``funnel_events`` 计算周活 (过去 7 天有事件的接受邀请用户数).

    Returns:
        (weekly_active_users, weekly_active_rate)
    """
    from datetime import timedelta

    if not invitations:
        return 0, 0.0

    accepted = [i for i in invitations if i.get("status") == "accepted" and i.get("accepted_at")]
    if not accepted:
        return 0, 0.0

    # accepted_at 可能没有 email -> user_id 的映射; 用 email 作为去重 key
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    active_emails: set[str] = set()
    accepted_emails = {i["email"].lower() for i in accepted if i.get("email")}
    if not accepted_emails:
        return 0, 0.0

    for ev in events:
        # funnel_events 通常带 user_id 或 metadata.email
        user_id = ev.get("user_id")
        meta = ev.get("metadata") or {}
        email = (meta.get("email") or "").lower()
        created = _parse_iso(ev.get("created_at"))
        if not created or created < cutoff:
            continue
        # 通过 email 关联到 accepted invitations
        if email and email in accepted_emails:
            active_emails.add(email)
        elif user_id and user_id in {i.get("user_id") for i in accepted if i.get("user_id")}:
            active_emails.add(user_id)

    rate = round(len(active_emails) / len(accepted), 4) if accepted else 0.0
    return len(active_emails), rate


# ---------------------------------------------------------------------------
# Service 公开 API
# ---------------------------------------------------------------------------


def create_program(
    *,
    organisation_id: str,
    name: str,
    description: Optional[str] = None,
    target_nps: int = 50,
    max_users: int = 20,
    metadata: Optional[dict[str, Any]] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """创建一个 pilot program (status=recruiting).

    Returns:
        DB 行 dict (含 ``id``).
    """
    if not organisation_id:
        raise ValueError("organisation_id is required")
    if not name or len(name.strip()) < 2:
        raise ValueError("name must be at least 2 characters")

    supabase = get_supabase_admin()
    payload: dict[str, Any] = {
        "organisation_id": organisation_id,
        "name": name.strip(),
        "description": description,
        "status": "recruiting",
        "target_nps": max(-100, min(100, int(target_nps))),
        "max_users": max(1, min(500, int(max_users))),
        "metadata": {**(metadata or {}), "created_by": created_by} if created_by else (metadata or {}),
    }
    result = supabase.table("pilot_programs").insert(payload).execute()
    rows = result.data or []
    if not rows:
        raise RuntimeError("pilot_service.create_program: insert returned no rows")
    return rows[0]


async def invite(
    *,
    program_id: str,
    email: str,
    role: str = "jobseeker",
    invited_by: Optional[str] = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    send_email: bool = True,
) -> Invitation:
    """邀请用户加入 program (转调 ``pilot_invitation.create_invitation``).

    状态守卫:
      - program 不存在 → LookupError
      - program 已结束 (status in {completed, cancelled}) → ValueError
      - max_users 已达 → ValueError
    """
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_programs")
        .select("id, status, max_users")
        .eq("id", program_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise LookupError(f"pilot program not found: {program_id}")
    program = resp.data

    if program.get("status") in {"completed", "cancelled"}:
        raise ValueError(f"program is {program['status']}, cannot invite")

    # 已接受数量是否达 max_users
    if program.get("max_users"):
        accepted_resp = (
            supabase.table("pilot_invitations")
            .select("id")
            .eq("program_id", program_id)
            .eq("status", "accepted")
            .execute()
        )
        count = len(accepted_resp.data or [])
        if count >= int(program["max_users"]):
            raise ValueError(
                f"program max_users reached ({count}/{program['max_users']})"
            )

    return await create_invitation(
        program_id=program_id,
        email=email,
        role=role,
        invited_by=invited_by,
        ttl_days=ttl_days,
        send_email=send_email,
    )


def get_stats(program_id: str) -> ProgramStats:
    """汇总 program 统计 (NPS / 邀请 / 反馈 / 周活 / Top 痛点)."""
    supabase = get_supabase_admin()

    prog_resp = (
        supabase.table("pilot_programs")
        .select("id, target_nps, max_users, status")
        .eq("id", program_id)
        .single()
        .execute()
    )
    if not prog_resp.data:
        raise LookupError(f"pilot program not found: {program_id}")
    program = prog_resp.data

    inv_resp = (
        supabase.table("pilot_invitations")
        .select("id, status, role, email, accepted_at, user_id")
        .eq("program_id", program_id)
        .execute()
    )
    invitations = inv_resp.data or []
    accepted = [i for i in invitations if i["status"] == "accepted"]
    pending = [i for i in invitations if i["status"] == "pending"]
    expired = [i for i in invitations if i["status"] == "expired"]

    fb_resp = (
        supabase.table("pilot_feedback")
        .select("id, category, score, comment, user_id, feature_used, created_at")
        .eq("program_id", program_id)
        .execute()
    )
    feedbacks = fb_resp.data or []

    nps_scores = [
        f.get("score") for f in feedbacks if f.get("category") == "nps" and f.get("score") is not None
    ]
    nps_stats = compute_nps(nps_scores)

    category_counts = _aggregate_categories(feedbacks)
    feature_counts = _aggregate_features(feedbacks)
    pain_points = _top_pain_points(feedbacks, limit=TOP_PAIN_POINTS_LIMIT)

    # 周活: 拉取最近 30 天的 funnel_events,再内部按 7 天滚动
    weekly_active = 0
    wau_rate: Optional[float] = None
    try:
        events_resp = (
            supabase.table("funnel_events")
            .select("user_id, created_at, metadata")
            .eq("program_id", program_id)
            .order("created_at", desc=True)
            .limit(5000)
            .execute()
        )
        events = events_resp.data or []
        weekly_active, wau_rate = _compute_weekly_active(
            invitations=invitations, events=events
        )
    except Exception as exc:  # noqa: BLE001
        # funnel_events 表可能不存在或 program_id 字段缺失; 不阻断主统计
        logger.debug("pilot_service.get_stats: funnel_events lookup skipped: %s", exc)

    stats = ProgramStats(
        program_id=program_id,
        invitations_total=len(invitations),
        invitations_accepted=len(accepted),
        invitations_pending=len(pending),
        invitations_expired=len(expired),
        active_users=len(accepted),
        weekly_active_users=weekly_active,
        weekly_active_rate=wau_rate,
        nps=nps_stats["nps"],
        nps_responses=nps_stats["responses"],
        promoters=nps_stats["promoters"],
        passives=nps_stats["passives"],
        detractors=nps_stats["detractors"],
        feedback_total=len(feedbacks),
        feedback_by_category=category_counts,
        feedback_by_feature=feature_counts,
        top_pain_points=pain_points,
        targets_met={},
    )
    stats.targets_met = _compute_targets_met(stats)
    # 保留 target_nps 用于报告
    try:
        stats.target_nps = int(program.get("target_nps") or 0) or None
    except (TypeError, ValueError):
        stats.target_nps = None
    return stats


def end_program(
    *,
    program_id: str,
    final_notes: Optional[str] = None,
) -> dict[str, Any]:
    """结束 program: status=completed, 记录 ended_at + 最终 NPS 到 metadata."""
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_programs")
        .select("id, status, metadata")
        .eq("id", program_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise LookupError(f"pilot program not found: {program_id}")
    program = resp.data
    if program.get("status") in {"completed", "cancelled"}:
        raise ValueError(f"program already {program['status']}")

    stats = get_stats(program_id)
    now = _now_iso()
    new_meta = {
        **(program.get("metadata") or {}),
        "final_nps": stats.nps,
        "weekly_active_rate": stats.weekly_active_rate,
        "ended_notes": final_notes,
        "ended_at": now,
        "targets_met": stats.targets_met,
    }
    update_resp = (
        supabase.table("pilot_programs")
        .update({"status": "completed", "ended_at": now, "metadata": new_meta})
        .eq("id", program_id)
        .execute()
    )
    rows = update_resp.data or []
    if not rows:
        raise RuntimeError("pilot_service.end_program: update returned no rows")
    return rows[0]


def generate_report(program_id: str) -> PilotReport:
    """生成完整 report (供 PDF / Dashboard / 邮件分享)."""
    supabase = get_supabase_admin()
    prog_resp = (
        supabase.table("pilot_programs")
        .select("*, organisations(name)")
        .eq("id", program_id)
        .single()
        .execute()
    )
    if not prog_resp.data:
        raise LookupError(f"pilot program not found: {program_id}")
    program = prog_resp.data

    org_obj = program.get("organisations")
    org_name: Optional[str] = None
    if isinstance(org_obj, dict):
        org_name = org_obj.get("name")
    elif isinstance(org_obj, list) and org_obj:
        org_name = org_obj[0].get("name")

    stats = get_stats(program_id)

    # 取 20 条最近反馈作为 samples
    fb_resp = (
        supabase.table("pilot_feedback")
        .select("id, category, score, comment, feature_used, created_at, user_id")
        .eq("program_id", program_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    samples = fb_resp.data or []

    # 邀请 breakdown by role
    inv_resp = (
        supabase.table("pilot_invitations")
        .select("role, status")
        .eq("program_id", program_id)
        .execute()
    )
    invs = inv_resp.data or []
    breakdown: dict[str, int] = {}
    for i in invs:
        key = f"{i.get('role', 'unknown')}/{i.get('status', 'unknown')}"
        breakdown[key] = breakdown.get(key, 0) + 1

    notes: list[str] = []
    if stats.nps is not None and stats.nps < NPS_TARGET:
        notes.append(
            f"NPS {stats.nps} 低于目标 {NPS_TARGET}; "
            "建议安排 CSM 1-on-1 收集 detractor 反馈。"
        )
    if stats.weekly_active_rate is not None and stats.weekly_active_rate < WEEKLY_ACTIVE_TARGET:
        notes.append(
            f"周活率 {stats.weekly_active_rate:.0%} 低于目标 "
            f"{WEEKLY_ACTIVE_TARGET:.0%}; 建议推送 onboarding 邮件/在线培训。"
        )
    if len(stats.top_pain_points) > TOP_PAIN_POINTS_LIMIT:
        notes.append(
            f"痛点超过 {TOP_PAIN_POINTS_LIMIT} 个; 建议先聚焦前 5 个高频项。"
        )

    return PilotReport(
        program_id=program_id,
        program_name=program.get("name", ""),
        organisation_name=org_name,
        status=program.get("status", ""),
        started_at=program.get("started_at"),
        ended_at=program.get("ended_at"),
        target_nps=int(program.get("target_nps") or NPS_TARGET),
        target_weekly_active=WEEKLY_ACTIVE_TARGET,
        generated_at=_now_iso(),
        stats=stats,
        feedback_samples=samples,
        invitation_breakdown=breakdown,
        notes=notes,
    )


def list_programs(
    *,
    organisation_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出 programs (可按 organisation / status 过滤)."""
    supabase = get_supabase_admin()
    query = (
        supabase.table("pilot_programs")
        .select("*, organisations(name)")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if organisation_id:
        query = query.eq("organisation_id", organisation_id)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return result.data or []


def get_program(program_id: str) -> dict[str, Any]:
    """获取单个 program 详情 (含 organisation 关联)."""
    supabase = get_supabase_admin()
    resp = (
        supabase.table("pilot_programs")
        .select("*, organisations(name)")
        .eq("id", program_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise LookupError(f"pilot program not found: {program_id}")
    return resp.data


__all__ = [
    "ProgramStats",
    "PilotReport",
    "PROGRAM_STATUSES",
    "NPS_TARGET",
    "WEEKLY_ACTIVE_TARGET",
    "TOP_PAIN_POINTS_LIMIT",
    "compute_nps",
    "create_program",
    "end_program",
    "generate_report",
    "get_program",
    "get_stats",
    "invite",
    "list_programs",
]