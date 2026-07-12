#!/usr/bin/env python3
"""Full hire workflow end-to-end demo (T1805).

工作流覆盖一次完整招聘: 投递 → 测评 → 视频面试 → 背景调查 → Offer
逐个 step 调用真实 provider (若 env 已配置) 或 fallback 到 mock,
输出每步产生的 join_url / invite_url / check_id 等关键信息。

环境变量 (生产真实):
  VIDEO_PROVIDER=zoom|tencent_meeting|mock
  ZOOM_* / TENCENT_MEETING_*
  ASSESSMENT_PROVIDER=beisen|mock
  BEISEN_*
  BG_CHECK_PROVIDER=checkr|mock
  CHECKR_API_KEY

跑法:
    python scripts/full_hire_workflow.py \\
        --candidate-email alice@example.com \\
        --role-id role_demo_001 \\
        --video-provider zoom \\
        --assessment-provider beisen \\
        --bg-check-provider checkr
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from project root or scripts dir
_SCRIPT_DIR = Path(__file__).resolve().parent
# Layout option A: scripts at <repo>/scripts/full_hire_workflow.py and
# backend at <repo>/talent-tool-mvp/backend — that's the actual layout.
_PARENT_OF_REPO = _SCRIPT_DIR.parent
BACKEND_DIR_CANDIDATE = _PARENT_OF_REPO / "talent-tool-mvp" / "backend"
if not BACKEND_DIR_CANDIDATE.exists():
    # Layout option B: scripts at <repo>/talent-tool-mvp/scripts/...
    BACKEND_DIR_CANDIDATE = _SCRIPT_DIR.parent / "backend"
if not BACKEND_DIR_CANDIDATE.exists():
    # Layout option C: scripts next to backend
    BACKEND_DIR_CANDIDATE = _SCRIPT_DIR.parent
BACKEND_DIR = BACKEND_DIR_CANDIDATE
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

# Patch: ensure providers load relative to backend root
if not os.getenv("OPENAI_API_KEY"):
    os.environ.setdefault("OPENAI_API_KEY", "sk-demo-noop")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
logger = logging.getLogger("full_hire_workflow")


def _section(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def _kv(d: dict) -> None:
    for k, v in d.items():
        print(f"  {k:>22}: {v}")


async def run_workflow(args: argparse.Namespace) -> None:
    """核心 6 步演示流程."""
    candidate_email = args.candidate_email
    candidate_id = args.candidate_id
    candidate_name = args.candidate_name
    role_id = args.role_id
    now = datetime.now(tz=timezone.utc)

    # ---------------------------------------------------------------- Step 1
    _section("Step 1: 候选人创建 + 角色匹配 (CompositeScorer)")
    from matching.scorer import WEIGHT_ASSESSMENT, CompositeScorer

    scorer = CompositeScorer()

    # 模拟候选人数据 (实际生产从 supabase 拿)
    candidate_skills = ["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"]
    semantic_similarity = 0.82
    candidate_experience_months = 60

    from contracts.shared import (
        ExtractedSkill,
        RequiredSkill,
        SeniorityLevel,
    )

    c_skills = [
        ExtractedSkill(name=s, years=4, source="resume")
        for s in candidate_skills
    ]
    role_required = [
        RequiredSkill(name="Python", min_years=3),
        RequiredSkill(name="FastAPI", min_years=2),
        RequiredSkill(name="PostgreSQL"),
    ]
    # 第一次评分: 没有 assessment,纯三因子
    pre_score = scorer.score(
        candidate_skills=c_skills,
        candidate_seniority=SeniorityLevel.senior,
        candidate_experience_months=candidate_experience_months,
        role_required_skills=role_required,
        role_preferred_skills=[],
        role_seniority=SeniorityLevel.senior,
        semantic_similarity=semantic_similarity,
    )
    _kv({
        "candidate_id": candidate_id,
        "email": candidate_email,
        "name": candidate_name,
        "role_id": role_id,
        "pre_assessment_score": pre_score["overall_score"],
        "weights": pre_score["scoring_breakdown"]["weights"],
    })

    # ---------------------------------------------------------------- Step 2
    _section(f"Step 2: 发起测评 ({args.assessment_provider})")
    from providers.assessment.registry import (
        get_assessment_provider,
        reset_cache as reset_assessment,
    )

    reset_assessment()
    os.environ["ASSESSMENT_PROVIDER"] = args.assessment_provider
    assessment = get_assessment_provider()
    print(f"  active provider: {assessment.provider_name}")

    invitation = await assessment.send_invitation(
        candidate_id=candidate_id,
        assessment_id=os.getenv(
            "BEISEN_ASSESSMENT_ID", "demo_assessment_v1",
        ),
        candidate_email=candidate_email,
        candidate_name=candidate_name,
        expires_in_hours=48,
        metadata={"role_id": role_id, "step": "2"},
    )
    _kv({
        "invitation_id": invitation.invitation_id,
        "invite_url": invitation.invite_url,
        "expires_at": invitation.expires_at.isoformat()
        if invitation.expires_at else None,
    })

    # 轮询结果 (演示 timeout 25s, 真实生产使用 webhook / cron)
    assessment_score: float | None = None
    for attempt in range(3):
        result = await assessment.get_results(invitation.invitation_id)
        print(
            f"  poll attempt={attempt + 1} status={result.status}"
            f" overall_score={result.overall_score}",
        )
        if result.status == "scored" and result.overall_score is not None:
            assessment_score = result.overall_score
            break
        await asyncio.sleep(2)

    if assessment_score is None:
        # 后备: 用 demo 评分跑流程 (演示用,真实业务不能用假数据)
        assessment_score = 88.0
        print(f"  [demo fallback] using synthetic assessment_score={assessment_score}")

    # ---------------------------------------------------------------- Step 3
    _section(f"Step 3: 重算 match score (assessment 已就绪)")
    post_score = scorer.score(
        candidate_skills=c_skills,
        candidate_seniority=SeniorityLevel.senior,
        candidate_experience_months=candidate_experience_months,
        role_required_skills=role_required,
        role_preferred_skills=[],
        role_seniority=SeniorityLevel.senior,
        semantic_similarity=semantic_similarity,
        assessment_score=assessment_score,
    )
    _kv({
        "with_assessment_overall": post_score["overall_score"],
        "assessment_raw": post_score["scoring_breakdown"]["components"].get("assessment_raw"),
        "confidence": post_score["confidence"],
        "delta_vs_pre": round(
            post_score["overall_score"] - pre_score["overall_score"], 4
        ),
        "weight_assessment": WEIGHT_ASSESSMENT,
    })

    # ---------------------------------------------------------------- Step 4
    _section(f"Step 4: 创建视频面试 — {args.video_provider}")
    from providers.video_interview.registry import (
        get_video_interview_provider,
        reset_cache as reset_video,
    )

    reset_video()
    os.environ["VIDEO_PROVIDER"] = args.video_provider
    video = get_video_interview_provider()
    print(f"  active provider: {video.provider_name}")

    from providers.video_interview.types import Participant

    panel_size = 5 if args.video_provider == "zoom" else 3
    round_topic = (
        f"[Waibao Demo] Senior 后端 ({args.video_provider})"
    )
    # 不同 provider 调不同方法 (zoom = 5, tencent = 3)
    from datetime import timedelta as _td

    if args.video_provider == "zoom" and hasattr(video, "create_panel_round"):
        start = now + _td(hours=4)
        meetings = await video.create_panel_round(
            candidate_id=candidate_email,
            topic=round_topic,
            panelist_emails=[
                "tech_lead@example.com",
                "behaviour@example.com",
                "case@example.com",
                "system_design@example.com",
                "cto@example.com",
            ],
            start_time=start,
            duration_min=45,
            rounds=5,
            host_email="hr@waibao.com",
            metadata={"role_id": role_id, "candidate_id": candidate_id},
        )
    elif args.video_provider == "tencent_meeting" and hasattr(
        video, "create_panel_round"
    ):
        start = now + _td(hours=4)
        meetings = await video.create_panel_round(
            candidate_id=candidate_email,
            topic=round_topic,
            panelist_userids=[
                "tech_lead",
                "hr_partner",
                "cto",
            ],
            start_time=start,
            duration_min=45,
            rounds=3,
            host_email="hr@waibao.com",
            metadata={"role_id": role_id, "candidate_id": candidate_id},
        )
    else:
        # fallback 单会议
        meeting = await video.create_meeting(
            topic=round_topic,
            start_time=now + _td(hours=4),
            duration_min=45,
            participants=[
                Participant(
                    email=candidate_email, name=candidate_name, role="attendee",
                )
            ],
            host_email="hr@waibao.com",
        )
        meetings = [meeting]

    for i, m in enumerate(meetings, 1):
        _kv({
            f"round_{i:02d}_meeting_id": m.meeting_id,
            f"round_{i:02d}_join_url": m.join_url,
            f"round_{i:02d}_start_time": m.start_time.isoformat()
            if m.start_time else None,
            f"round_{i:02d}_password": (m.password or "")[:8] + "...",
        })

    # ---------------------------------------------------------------- Step 5
    _section(f"Step 5: 背景调查 ({args.bg_check_provider})")
    from providers.background_check.registry import (
        get_background_check_provider,
        reset_cache as reset_bg,
    )

    reset_bg()
    os.environ["BG_CHECK_PROVIDER"] = args.bg_check_provider
    bg = get_background_check_provider()
    print(f"  active provider: {bg.provider_name}")

    from providers.background_check.types import CheckType

    check = await bg.initiate_check(
        candidate_id=candidate_id,
        check_types=[
            CheckType(code="criminal", required=True),
            CheckType(code="employment", required=True),
            CheckType(code="education", required=False),
        ],
        candidate_email=candidate_email,
        candidate_name=candidate_name,
        metadata={
            "offer_id": args.offer_id,
            "role_id": role_id,
            "triggered_by": "t1805-e2e",
        },
    )
    _kv({
        "check_id": check.check_id,
        "status": check.status,
        "report_url": check.report_url,
        "check_types": ",".join(check.check_types),
    })

    # 拉一次状态 (真实业务会等 webhook 而非轮询)
    bg_status = await bg.get_status(check.check_id)
    _kv({
        "current_status": bg_status.status,
        "progress_pct": bg_status.progress_pct,
        "findings_count": len(bg_status.findings),
    })

    # ---------------------------------------------------------------- Step 6
    _section("Step 6: 通过 HR agent 自动 Offer 阶段触发 (T1307)")
    print("  在 hr_service_agent.py 中:")
    print("    _maybe_trigger_pre_offer_background_check")
    print("    ↳ 输入 '我们要给候选人发 Offer' → 自动调用 BackgroundCheckService.trigger_pre_offer")
    print("    ↳ 命中已有 check 时短路 (skipped,reason='already-running')")
    print("    ↳ 没有时立刻发起 Checkr 真请求 → 返回 check_id")

    # ---------------------------------------------------------------- Summary
    _section("SUMMARY")
    print(json.dumps({
        "candidate": {
            "id": candidate_id,
            "email": candidate_email,
            "name": candidate_name,
        },
        "role_id": role_id,
        "steps": {
            "assessment": {
                "provider": assessment.provider_name,
                "invitation_id": invitation.invitation_id,
                "assessment_score": assessment_score,
                "weight": WEIGHT_ASSESSMENT,
            },
            "match": {
                "pre_assessment_score": pre_score["overall_score"],
                "post_assessment_score": post_score["overall_score"],
                "delta": round(
                    post_score["overall_score"] - pre_score["overall_score"], 4
                ),
                "confidence": post_score["confidence"],
            },
            "video_interview": {
                "provider": video.provider_name,
                "meetings_created": len(meetings),
                "round_topic": round_topic,
                "first_join_url": meetings[0].join_url,
            },
            "background_check": {
                "provider": bg.provider_name,
                "check_id": check.check_id,
                "status": check.status,
            },
        },
    }, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="T1805 full hire workflow demo")
    p.add_argument(
        "--candidate-id", default="cand_demo_001",
        help="业务侧的候选人 ID",
    )
    p.add_argument(
        "--candidate-email", default="alice@example.com",
        help="候选人邮箱",
    )
    p.add_argument(
        "--candidate-name", default="Alice Demo",
        help="候选人姓名",
    )
    p.add_argument(
        "--role-id", default="role_demo_001",
        help="角色 ID",
    )
    p.add_argument(
        "--offer-id", default="offer_demo_001",
        help="Offer ID (offer 前必触发背调)",
    )
    p.add_argument(
        "--video-provider", default=os.getenv("VIDEO_PROVIDER", "mock"),
        choices=["mock", "zoom", "tencent_meeting"],
    )
    p.add_argument(
        "--assessment-provider", default=os.getenv("ASSESSMENT_PROVIDER", "mock"),
        choices=["mock", "beisen"],
    )
    p.add_argument(
        "--bg-check-provider", default=os.getenv("BG_CHECK_PROVIDER", "mock"),
        choices=["mock", "checkr"],
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_workflow(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow failed")
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
