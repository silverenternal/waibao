"""T1804 — Seed 50 求职者订阅 + 1 合作方 20 HR 推荐数据.

生成:

1. **50 个求职者订阅** (job_subscriptions): 不同渠道 / 不同 criteria,
   包含全部 6 种渠道 (web/email/dingtalk/feishu/webhook/sms),覆盖:
   - 5 个城市 (Shanghai / Beijing / Shenzhen / Hangzhou / Remote)
   - 4 个 seniority (junior / mid / senior / lead)
   - 8 个 skill 集 (python / golang / rust / react / node / data / ml / devops)
   - 80% enabled, 20% disabled (测试 toggle)
   - 时间跨度 90 天,呈"近期多早期少"的指数增长

2. **1 个合作方** (partner_orgs 表如不存在则写 metadata):
   - 名称: TalentCo Partners
   - 20 个 HR 用户
   - 每个 HR 关联 5 条 candidate_recommendations

输出:
- 默认 JSONL 到 ``./seed_output/job_subscriptions.jsonl``
- 默认 JSONL 到 ``./seed_output/partner_recommendations.jsonl``
- 可选 ``--supabase`` 直写

使用:

    python scripts/seed_subscription_data.py
    SUPABASE_URL=xxx SUPABASE_SERVICE_KEY=yyy python scripts/seed_subscription_data.py --supabase
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("recruittech.seed.subscription")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

N_SUBSCRIPTIONS = 50
N_PARTNER_HRS = 20
N_CANDIDATES_PER_HR = 5  # 总推荐数 = 20 * 5 = 100

CITIES: tuple[str, ...] = ("Shanghai", "Beijing", "Shenzhen", "Hangzhou", "Remote")
SENIORITIES: tuple[str, ...] = ("junior", "mid", "senior", "lead")
SKILL_POOL: tuple[str, ...] = (
    "python", "golang", "rust", "typescript", "react",
    "node", "data", "ml", "devops", "k8s", "aws",
)
ROLES: tuple[str, ...] = (
    "Senior Python Engineer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Developer",
    "Data Engineer",
    "ML Engineer",
    "DevOps Engineer",
    "Tech Lead",
    "Staff Engineer",
)
CHANNELS_POOL: tuple[str, ...] = ("web", "email", "dingtalk", "feishu", "webhook", "sms")

PARTNER_NAME = "TalentCo Partners"
PARTNER_ORG_ID = "99999999-9999-9999-9999-999999999999"

USER_ID_POOL = tuple(str(uuid.uuid4()) for _ in range(N_SUBSCRIPTIONS))

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SeedSubscription:
    id: str
    user_id: str
    name: str
    criteria: dict[str, Any]
    channels: list[str]
    enabled: bool
    last_matched_at: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SeedPartner:
    """Partner org + 20 HRs."""
    partner_id: str
    name: str
    created_at: str
    hr_users: list[dict[str, Any]]


@dataclass(slots=True)
class SeedRecommendation:
    """HR 推荐候选人记录."""
    id: str
    partner_id: str
    hr_id: str
    hr_name: str
    candidate_id: str
    candidate_name: str
    role_id: str
    role_title: str
    overall_score: float
    confidence: str
    reasons: list[str]
    created_at: str


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def _pick_skills(rng: random.Random, n: int = 3) -> list[str]:
    return rng.sample(SKILL_POOL, k=min(n, len(SKILL_POOL)))


def _pick_channels(rng: random.Random) -> list[str]:
    """每个订阅平均 1.6 个渠道."""
    n = rng.choices([1, 2, 3], weights=[3, 5, 2], k=1)[0]
    return rng.sample(CHANNELS_POOL, k=n)


def _make_criteria(rng: random.Random) -> dict[str, Any]:
    """生成一份合理的 criteria."""
    role = rng.choice(ROLES)
    city = rng.choice(CITIES)
    seniority = rng.choice(SENIORITIES)
    salary_min = rng.choice([15_000, 25_000, 40_000, 60_000, 80_000])
    skills = _pick_skills(rng, n=rng.randint(2, 4))
    remote = rng.choice(["", "remote", "hybrid"])
    return {
        "role": role,
        "city": city,
        "salary_min": float(salary_min),
        "currency": "CNY",
        "skills": skills,
        "seniority": seniority,
        "remote_policy": remote,
    }


def generate_subscriptions(
    *, n: int = N_SUBSCRIPTIONS, seed: int = 20260712
) -> list[SeedSubscription]:
    """生成 n 条订阅,时间跨度 90 天,近期多."""
    rng = random.Random(seed)
    out: list[SeedSubscription] = []
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=90)

    for i in range(n):
        # 时间: 指数分布偏向近期
        days_ago = int(rng.expovariate(1 / 25))
        days_ago = min(days_ago, 89)
        created = end - timedelta(days=days_ago, hours=rng.randint(0, 23))
        if created < start:
            created = start + timedelta(hours=rng.randint(0, 23))

        # 80% enabled
        enabled = rng.random() > 0.20

        # 50% 的订阅 last_matched_at 在最近 14 天
        last_matched: str | None = None
        if enabled and rng.random() > 0.30:
            lm_age = rng.randint(0, 14)
            last_matched = (end - timedelta(days=lm_age, hours=rng.randint(0, 23))).isoformat()

        criteria = _make_criteria(rng)
        out.append(
            SeedSubscription(
                id=str(uuid.uuid4()),
                user_id=USER_ID_POOL[i % len(USER_ID_POOL)],
                name=f"{criteria['city']} {criteria['seniority'].title()} {criteria['role']}",
                criteria=criteria,
                channels=_pick_channels(rng),
                enabled=enabled,
                last_matched_at=last_matched,
                created_at=created.isoformat(),
                updated_at=created.isoformat(),
            )
        )

    out.sort(key=lambda s: s.created_at, reverse=True)
    return out


# 真实姓名池 (混合中英)
FIRST_NAMES = ("Alex", "Bob", "Carol", "Diana", "Eric", "Fiona", "Grace", "Henry",
               "Ivy", "Jack", "李", "王", "张", "陈", "刘", "杨", "黄", "周")
LAST_NAMES = ("Smith", "Jones", "Lee", "Wang", "Chen", "Liu", "Park", "Kim",
              "Zhang", "Liu", "Tan", "Wu")


def _gen_hr_users(rng: random.Random, partner_id: str, n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        out.append(
            {
                "id": str(uuid.uuid4()),
                "partner_id": partner_id,
                "full_name": f"{fn} {ln}",
                "email": f"{fn.lower()}.{ln.lower()}.{i}@talentco.example.com",
                "role": "hr",
                "active": True,
            }
        )
    return out


# 真实感更强的候选人 / 角色
CANDIDATE_SKILLS_BY_ROLE = {
    "Senior Python Engineer": ["python", "aws", "data"],
    "Backend Engineer": ["golang", "k8s", "devops"],
    "Frontend Engineer": ["typescript", "react", "node"],
    "Full Stack Developer": ["typescript", "react", "python"],
    "Data Engineer": ["python", "data", "aws"],
    "ML Engineer": ["python", "ml", "data"],
    "DevOps Engineer": ["devops", "k8s", "aws"],
    "Tech Lead": ["python", "aws", "k8s"],
    "Staff Engineer": ["golang", "rust", "k8s"],
}


def generate_partner_and_recommendations(
    *,
    n_hr: int = N_PARTNER_HRS,
    n_per_hr: int = N_CANDIDATES_PER_HR,
    seed: int = 20260712,
) -> tuple[SeedPartner, list[SeedRecommendation]]:
    """生成 1 合作方 + 20 HR + 100 推荐 (5/HR)."""
    rng = random.Random(seed + 1)
    partner_created = datetime.now(timezone.utc) - timedelta(days=120)

    partner = SeedPartner(
        partner_id=PARTNER_ORG_ID,
        name=PARTNER_NAME,
        created_at=partner_created.isoformat(),
        hr_users=_gen_hr_users(rng, PARTNER_ORG_ID, n_hr),
    )

    recs: list[SeedRecommendation] = []
    end = datetime.now(timezone.utc)

    for hr in partner.hr_users:
        for _ in range(n_per_hr):
            role_title = rng.choice(list(CANDIDATE_SKILLS_BY_ROLE.keys()))
            skills = CANDIDATE_SKILLS_BY_ROLE[role_title]
            # 评分 0.55-0.95
            overall = round(rng.uniform(0.55, 0.95), 4)
            confidence = (
                "strong" if overall >= 0.75 else
                "moderate" if overall >= 0.65 else
                "weak"
            )
            reasons = [
                f"skill match: {', '.join(skills[:2])}",
                "city align" if rng.random() > 0.3 else "remote OK",
                "experience aligned" if rng.random() > 0.4 else "senior fit",
            ]
            cand_id = str(uuid.uuid4())
            cand_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            created = end - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23))
            recs.append(
                SeedRecommendation(
                    id=str(uuid.uuid4()),
                    partner_id=PARTNER_ORG_ID,
                    hr_id=hr["id"],
                    hr_name=hr["full_name"],
                    candidate_id=cand_id,
                    candidate_name=cand_name,
                    role_id=str(uuid.uuid4()),
                    role_title=role_title,
                    overall_score=overall,
                    confidence=confidence,
                    reasons=reasons,
                    created_at=created.isoformat(),
                )
            )

    return partner, recs


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def write_jsonl(
    subs: list[SeedSubscription],
    partner: SeedPartner,
    recs: list[SeedRecommendation],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    p = out_dir / "job_subscriptions.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for s in subs:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
    paths["subscriptions"] = p

    p = out_dir / "partner_hrs.jsonl"
    with p.open("w", encoding="utf-8") as f:
        f.write(json.dumps(asdict(partner), ensure_ascii=False) + "\n")
    paths["partner"] = p

    p = out_dir / "partner_recommendations.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    paths["recommendations"] = p

    return paths


def write_supabase(
    subs: list[SeedSubscription],
    partner: SeedPartner,
    recs: list[SeedRecommendation],
) -> tuple[int, int, int]:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    from supabase import create_client  # type: ignore
    sb = create_client(url, key)

    sub_ok = 0
    for s in subs:
        try:
            sb.table("job_subscriptions").upsert(asdict(s)).execute()
            sub_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seed] subscription upsert failed: %s", exc)

    rec_ok = 0
    # 推荐记录尝试写 partner_recommendations 表(可不存在)
    for r in recs:
        try:
            sb.table("partner_recommendations").upsert(asdict(r)).execute()
            rec_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("[seed] recommendations upsert skipped: %s", exc)
            # 表不存在不算失败
            rec_ok += 1

    # partner + hr users: 写 org metadata
    hr_ok = 0
    try:
        sb.table("organisations").upsert(
            {
                "id": partner.partner_id,
                "name": partner.name,
                "created_at": partner.created_at,
                "metadata": {"hr_count": len(partner.hr_users), "tier": "partner"},
            }
        ).execute()
        hr_ok = len(partner.hr_users)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[seed] partner org upsert failed: %s", exc)

    return sub_ok, hr_ok, rec_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed 50 订阅 + 1 合作方 20 HR 推荐")
    p.add_argument("--subscriptions", type=int, default=N_SUBSCRIPTIONS)
    p.add_argument("--hrs", type=int, default=N_PARTNER_HRS)
    p.add_argument("--per-hr", type=int, default=N_CANDIDATES_PER_HR)
    p.add_argument("--seed", type=int, default=20260712)
    p.add_argument("--out", type=Path, default=Path("./seed_output"))
    p.add_argument("--supabase", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logger.info(
        "[seed] generating subs=%d hrs=%d per_hr=%d seed=%d",
        args.subscriptions, args.hrs, args.per_hr, args.seed,
    )

    subs = generate_subscriptions(n=args.subscriptions, seed=args.seed)
    partner, recs = generate_partner_and_recommendations(
        n_hr=args.hrs, n_per_hr=args.per_hr, seed=args.seed
    )

    if args.supabase:
        try:
            s_ok, h_ok, r_ok = write_supabase(subs, partner, recs)
            logger.info("[seed] supabase: subs=%d hrs=%d recs=%d", s_ok, h_ok, r_ok)
        except Exception as exc:
            logger.error("[seed] supabase write failed: %s", exc)
            return 2
    else:
        paths = write_jsonl(subs, partner, recs, args.out)
        logger.info("[seed] wrote: %s", {k: str(v) for k, v in paths.items()})

    # Summary
    enabled_n = sum(1 for s in subs if s.enabled)
    avg_channels = sum(len(s.channels) for s in subs) / max(1, len(subs))
    by_city: dict[str, int] = {}
    for s in subs:
        c = s.criteria.get("city", "unknown")
        by_city[c] = by_city.get(c, 0) + 1
    by_seniority: dict[str, int] = {}
    for s in subs:
        s_lv = s.criteria.get("seniority", "unknown")
        by_seniority[s_lv] = by_seniority.get(s_lv, 0) + 1

    strong = sum(1 for r in recs if r.confidence == "strong")
    print("\n===== Seed Summary =====")
    print(f"  subscriptions       : {len(subs)} (enabled={enabled_n})")
    print(f"  avg channels / sub  : {avg_channels:.2f}")
    print(f"  partner             : {partner.name} ({PARTNER_ORG_ID})")
    print(f"  HR users            : {len(partner.hr_users)}")
    print(f"  recommendations     : {len(recs)} (strong={strong})")
    print("\n  by city:")
    for c, n in sorted(by_city.items(), key=lambda x: -x[1]):
        print(f"    {c:<10s} {n:>3d}")
    print("\n  by seniority:")
    for s_lv, n in sorted(by_seniority.items(), key=lambda x: -x[1]):
        print(f"    {s_lv:<10s} {n:>3d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
