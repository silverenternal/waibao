"""T1803 — Seed 90 天真实漏斗事件数据.

生成 90 天前 -> 现在的 funnel_events 真实分布,支持:

1. **直接落 Supabase** (默认): 当 ``SUPABASE_URL`` + ``SUPABASE_SERVICE_KEY``
   在环境变量中时,脚本会直接 ``insert`` 进 ``funnel_events`` 表,并同步
   ``channel_spend`` 月度汇总(用于 ROI 计算).

2. **落到本地 JSONL**: 当未配置 Supabase 时,脚本会把事件写到
   ``./seed_output/funnel_events.jsonl``,方便后续用
   ``FunnelEventTracker`` 内存聚合做单元/集成测试.

数据分布(以现实招聘市场为参考):
- 渠道: linkedin / referral / indeed / company_site / lagou / zhilian / direct
- 阶段: sourced -> applied (60%) -> screened (45%) -> interviewed (30%) -> offered (12%) -> hired (8%)
- 每日 sourced 量级 30-80,周一周二高,周末低
- cost_cents 按渠道不同: linkedin 8000 / indeed 5000 / 智联 2000 / referral 1000 / company_site 0
- 单 hired 的元数据里带 referrer_id (referral 渠道) 或 campaign_id (paid)

使用:

    # 本地 JSONL 输出 (默认)
    python scripts/seed_funnel_data.py

    # 写到 Supabase
    SUPABASE_URL=xxx SUPABASE_SERVICE_KEY=yyy python scripts/seed_funnel_data.py --supabase

    # 自定义 60 天, 5 家公司
    python scripts/seed_funnel_data.py --days 60 --orgs 5 --seed 42
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
from typing import Any, Iterable

logger = logging.getLogger("recruittech.seed.funnel")


# ---------------------------------------------------------------------------
# 配置: 阶段转化率 + 渠道 cost (单位 cents)
# ---------------------------------------------------------------------------

# 顺序: sourced -> applied -> screened -> interviewed -> offered -> hired
STAGE_FUNNEL: tuple[str, ...] = (
    "sourced",
    "applied",
    "screened",
    "interviewed",
    "offered",
    "hired",
)

# 每个阶段相对上一阶段的转化率 (%)
STAGE_TRANSITION: dict[str, float] = {
    "sourced_to_applied": 0.62,
    "applied_to_screened": 0.48,
    "screened_to_interviewed": 0.55,
    "interviewed_to_offered": 0.32,
    "offered_to_hired": 0.78,
}

CHANNELS: tuple[str, ...] = (
    "linkedin",
    "referral",
    "indeed",
    "company_site",
    "lagou",
    "zhilian",
    "direct",
)

# 渠道: 每天 sourced 比例 (合计 1.0) + 单 sourced 平均 cost_cents
CHANNEL_MIX: dict[str, dict[str, float]] = {
    "linkedin":     {"share": 0.22, "cost_per_sourced": 8500},
    "referral":     {"share": 0.18, "cost_per_sourced": 1200},
    "indeed":       {"share": 0.14, "cost_per_sourced": 5500},
    "company_site": {"share": 0.12, "cost_per_sourced": 0},
    "lagou":        {"share": 0.10, "cost_per_sourced": 2800},
    "zhilian":      {"share": 0.09, "cost_per_sourced": 2500},
    "direct":       {"share": 0.15, "cost_per_sourced": 0},
}

# 周一/周二权重 +20%, 周末 -40%
WEEKDAY_WEIGHT: dict[int, float] = {
    0: 1.2,  # Mon
    1: 1.2,  # Tue
    2: 1.0,
    3: 1.0,
    4: 1.0,
    5: 0.7,  # Sat
    6: 0.6,  # Sun
}

# 基准: 每天 sourced 人数 (按 org 累加, 单 org 30-50)
BASE_SOURCED_PER_DAY_PER_ORG: int = 35

# 组织/雇主清单 (种子用)
SEED_ORGS: tuple[tuple[str, str], ...] = (
    ("11111111-1111-1111-1111-111111111111", "Acme Tech"),
    ("22222222-2222-2222-2222-222222222222", "ByteForge"),
    ("33333333-3333-3333-3333-333333333333", "CloudNest"),
    ("44444444-4444-4444-4444-444444444444", "DataPivot"),
    ("55555555-5555-5555-5555-555555555555", "EdgeMind"),
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SeedEvent:
    """一条待写入的漏斗事件 (与 funnel_events 表 schema 对齐)."""

    id: str
    org_id: str
    candidate_id: str
    role_id: str
    stage: str
    source: str
    cost_cents: int
    metadata: dict[str, Any]
    occurred_at: str


@dataclass(slots=True)
class SeedSpend:
    """channel_spend 月度汇总行."""

    id: str
    org_id: str
    channel: str
    period_start: str
    period_end: str
    spend_cents: int
    notes: str


# ---------------------------------------------------------------------------
# 生成逻辑
# ---------------------------------------------------------------------------

def _weighted_sourced_count(rng: random.Random, weekday: int, per_org: int) -> int:
    base = per_org * WEEKDAY_WEIGHT[weekday]
    jitter = rng.uniform(0.7, 1.3)
    return max(1, int(base * jitter))


def _pick_channel(rng: random.Random) -> str:
    """按 CHANNEL_MIX 比例抽取渠道."""
    r = rng.random()
    acc = 0.0
    for ch, cfg in CHANNEL_MIX.items():
        acc += cfg["share"]
        if r <= acc:
            return ch
    return CHANNELS[-1]


def _cost_for_stage(channel: str, stage: str, base_cost: int) -> int:
    """阶段成本 — sourced 阶段摊到平均 cost_per_sourced;其他阶段按比例降权."""
    if stage == "sourced":
        return base_cost
    # 后置阶段只保留 ~10% 的渠道成本(分摊)
    return max(0, int(base_cost * 0.1))


def _metadata_for(
    rng: random.Random, channel: str, role_id: str, stage: str
) -> dict[str, Any]:
    md: dict[str, Any] = {"role_id": role_id, "stage": stage}
    if channel == "referral":
        md["referrer_id"] = f"emp-{rng.randint(1000, 9999)}"
    elif channel in {"linkedin", "indeed", "lagou", "zhilian"}:
        md["campaign_id"] = f"camp-{rng.choice(['spring', 'summer', 'autumn', 'winter'])}-{rng.randint(100, 999)}"
        md["job_id_external"] = f"{channel[:3].upper()}-{rng.randint(100000, 999999)}"
    elif channel == "company_site":
        md["landing_page"] = rng.choice(
            ["/careers", "/jobs/python", "/jobs/lead", "/jobs/data"]
        )
    elif channel == "direct":
        md["inbound_email"] = f"candidate{rng.randint(100, 999)}@mail.com"
    return md


def _generate_one_day(
    rng: random.Random,
    day: datetime,
    orgs: list[tuple[str, str]],
    per_org: int,
    output: list[SeedEvent],
    spend_acc: dict[tuple[str, str, str], int],
) -> None:
    weekday = day.weekday()
    for org_id, _name in orgs:
        n_sourced = _weighted_sourced_count(rng, weekday, per_org)

        # 1) 按渠道分摊今天的 sourced
        channel_counts: dict[str, int] = {}
        remaining = n_sourced
        channels_today = list(CHANNELS)
        rng.shuffle(channels_today)
        for i, ch in enumerate(channels_today):
            if i == len(channels_today) - 1:
                channel_counts[ch] = remaining
            else:
                share = CHANNEL_MIX[ch]["share"]
                take = int(round(n_sourced * share))
                take = min(take, remaining)
                channel_counts[ch] = take
                remaining -= take
                if remaining <= 0:
                    break

        # 2) 每个渠道下生成候选人漏斗
        for ch, count in channel_counts.items():
            base_cost = CHANNEL_MIX[ch]["cost_per_sourced"]
            for _ in range(count):
                cand_id = str(uuid.uuid4())
                role_id = str(uuid.uuid4())

                # 漏斗推进 — 每阶段独立掷骰子决定是否进入下一阶段
                advanced = True
                prev_stage = "sourced"
                occurred_at = day + timedelta(
                    hours=rng.randint(9, 18),
                    minutes=rng.randint(0, 59),
                )

                # 写 sourced
                output.append(
                    SeedEvent(
                        id=str(uuid.uuid4()),
                        org_id=org_id,
                        candidate_id=cand_id,
                        role_id=role_id,
                        stage="sourced",
                        source=ch,
                        cost_cents=base_cost,
                        metadata=_metadata_for(rng, ch, role_id, "sourced"),
                        occurred_at=occurred_at.isoformat(),
                    )
                )

                # 按 STAGE_TRANSITION 推进
                for stage in STAGE_FUNNEL[1:]:
                    trans_key = f"{prev_stage}_to_{stage}"
                    p = STAGE_TRANSITION[trans_key]
                    # 越往后转化越低, 加一点随机衰减
                    p_adj = max(0.0, p * rng.uniform(0.85, 1.15))
                    if rng.random() > p_adj:
                        advanced = False
                        break
                    # 推进时间: applied 1-3 天, screened 2-4 天,
                    # interviewed 3-7 天, offered 5-10 天, hired 7-14 天
                    lag_map = {
                        "applied": (1, 3),
                        "screened": (2, 4),
                        "interviewed": (3, 7),
                        "offered": (5, 10),
                        "hired": (7, 14),
                    }
                    lo, hi = lag_map[stage]
                    offset = timedelta(
                        days=rng.randint(lo, hi),
                        hours=rng.randint(0, 23),
                    )
                    # 不能超过今天
                    stage_time = min(
                        day + timedelta(days=89, hours=23),
                        day + offset,
                    )
                    output.append(
                        SeedEvent(
                            id=str(uuid.uuid4()),
                            org_id=org_id,
                            candidate_id=cand_id,
                            role_id=role_id,
                            stage=stage,
                            source=ch,
                            cost_cents=_cost_for_stage(ch, stage, base_cost),
                            metadata=_metadata_for(rng, ch, role_id, stage),
                            occurred_at=stage_time.isoformat(),
                        )
                    )
                    prev_stage = stage

                # T1803 — multi-touch 模拟: ~30% 的候选人会被另一个渠道"二次触达"。
                # 因为 ``record_stage`` 按 (candidate, role, stage) 幂等,我们不能为
                # 同一阶段写两个不同渠道;真实场景下,候选人会从 A 渠道 sourced,
                # 然后通过 B 渠道再次互动(例如内推后的 referral 重投)。
                # 这里用 ``metadata.re_touch=True`` + 不同的 source 记录同一
                # candidate/role/stage 的"二次触达"。前端解析时按 candidate + source
                # 去重即可看到多渠道。
                if rng.random() < 0.30 and advanced:
                    other_channels = [c for c in CHANNELS if c != ch]
                    if other_channels:
                        other = rng.choice(other_channels)
                        touch_stage = prev_stage  # 实际进展到的阶段
                        touch_time = day + timedelta(
                            days=rng.randint(1, 14),
                            hours=rng.randint(0, 23),
                        )
                        touch_time = min(
                            day + timedelta(days=89, hours=23), touch_time
                        )
                        touch_cost = int(
                            CHANNEL_MIX[other]["cost_per_sourced"] * 0.05
                        )
                        # 用 metadata 标识二次触达 — ``_source_secondary`` 字段
                        # 让 ``channel_attribution`` 看到多个 source。
                        output.append(
                            SeedEvent(
                                id=str(uuid.uuid4()),
                                org_id=org_id,
                                candidate_id=cand_id,
                                role_id=role_id,
                                stage=touch_stage,
                                source=other,
                                cost_cents=touch_cost,
                                metadata={
                                    "role_id": role_id,
                                    "stage": touch_stage,
                                    "re_touch": True,
                                    "primary_source": ch,
                                    "secondary_source": other,
                                    **(
                                        {"campaign_id": f"re-touch-{rng.randint(100, 999)}"}
                                        if other in {"linkedin", "indeed", "lagou", "zhilian"}
                                        else {}
                                    ),
                                },
                                occurred_at=touch_time.isoformat(),
                            )
                        )
                        # 二次触达也会产生少量 spend
                        month_key = day.strftime("%Y-%m")
                        key = (org_id, other, month_key)
                        spend_acc[key] = spend_acc.get(key, 0) + touch_cost

                # 累加 spend
                month_key = day.strftime("%Y-%m")
                key = (org_id, ch, month_key)
                spend_acc[key] = spend_acc.get(key, 0) + base_cost


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def generate(
    *,
    days: int = 90,
    orgs: int = 5,
    per_org: int = BASE_SOURCED_PER_DAY_PER_ORG,
    seed: int = 20260712,
) -> tuple[list[SeedEvent], list[SeedSpend]]:
    """生成 90 天 funnel 事件 + 月度 channel_spend 汇总.

    Returns:
        (events, spends) 两条独立列表。
    """
    rng = random.Random(seed)
    selected_orgs = list(SEED_ORGS[: max(1, min(orgs, len(SEED_ORGS)))])

    end = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = end - timedelta(days=days - 1)

    events: list[SeedEvent] = []
    spend_acc: dict[tuple[str, str, str], int] = {}

    cur = start
    while cur <= end:
        _generate_one_day(rng, cur, selected_orgs, per_org, events, spend_acc)
        cur += timedelta(days=1)

    # 月度 spend 汇总
    spends: list[SeedSpend] = []
    for (org_id, ch, ym), cents in spend_acc.items():
        year, month = ym.split("-")
        period_start = f"{year}-{month}-01"
        # 下月第一天 - 1 天 = 当月最后一天
        if month == "12":
            next_month = f"{int(year) + 1}-01-01"
        else:
            next_month = f"{year}-{int(month) + 1:02d}-01"
        period_end_dt = datetime.strptime(next_month, "%Y-%m-%d") - timedelta(days=1)
        spends.append(
            SeedSpend(
                id=str(uuid.uuid4()),
                org_id=org_id,
                channel=ch,
                period_start=period_start,
                period_end=period_end_dt.strftime("%Y-%m-%d"),
                spend_cents=cents,
                notes=f"Seed data for {period_start} (T1803)",
            )
        )

    return events, spends


def write_jsonl(events: list[SeedEvent], spends: list[SeedSpend], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "funnel_events.jsonl"
    spends_path = out_dir / "channel_spend.jsonl"

    with events_path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    with spends_path.open("w", encoding="utf-8") as f:
        for s in spends:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")

    return events_path


def write_supabase(
    events: list[SeedEvent], spends: list[SeedSpend], *, batch_size: int = 500
) -> tuple[int, int]:
    """直接写入 Supabase — 返回 (event_ok, spend_ok)."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")

    # 延迟 import, 没装 supabase 时不强制依赖
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "需要 supabase 客户端: pip install supabase"
        ) from exc

    sb = create_client(url, key)

    event_ok = 0
    for i in range(0, len(events), batch_size):
        batch = [asdict(e) for e in events[i : i + batch_size]]
        try:
            sb.table("funnel_events").insert(batch).execute()
            event_ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seed] events batch %d failed: %s", i, exc)

    spend_ok = 0
    for i in range(0, len(spends), batch_size):
        batch = [asdict(s) for s in spends[i : i + batch_size]]
        try:
            sb.table("channel_spend").insert(batch).execute()
            spend_ok += len(batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seed] spend batch %d failed: %s", i, exc)

    return event_ok, spend_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed 90 天真实漏斗数据")
    p.add_argument("--days", type=int, default=90, help="回溯天数 (默认 90)")
    p.add_argument("--orgs", type=int, default=5, help="组织数量 (默认 5)")
    p.add_argument(
        "--per-org",
        type=int,
        default=BASE_SOURCED_PER_DAY_PER_ORG,
        help="单 org 单日 sourced 均值",
    )
    p.add_argument("--seed", type=int, default=20260712, help="随机种子")
    p.add_argument(
        "--out",
        type=Path,
        default=Path("./seed_output"),
        help="JSONL 输出目录",
    )
    p.add_argument(
        "--supabase",
        action="store_true",
        help="直写 Supabase (需要 SUPABASE_URL/SUPABASE_SERVICE_KEY)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="关闭 progress 日志",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logger.info(
        "[seed] generating days=%d orgs=%d per_org=%d seed=%d",
        args.days,
        args.orgs,
        args.per_org,
        args.seed,
    )

    events, spends = generate(
        days=args.days,
        orgs=args.orgs,
        per_org=args.per_org,
        seed=args.seed,
    )

    logger.info(
        "[seed] generated %d funnel_events + %d channel_spend rows",
        len(events),
        len(spends),
    )

    if args.supabase:
        try:
            event_ok, spend_ok = write_supabase(events, spends)
            logger.info(
                "[seed] supabase insert: events=%d/%d spends=%d/%d",
                event_ok,
                len(events),
                spend_ok,
                len(spends),
            )
        except Exception as exc:
            logger.error("[seed] supabase write failed: %s", exc)
            return 2
    else:
        path = write_jsonl(events, spends, args.out)
        logger.info("[seed] wrote JSONL to %s", path)

    # 输出汇总
    by_stage: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for e in events:
        by_stage[e.stage] = by_stage.get(e.stage, 0) + 1
        by_source[e.source] = by_source.get(e.source, 0) + 1

    print("\n===== Seed Summary =====")
    print(f"  events total     : {len(events)}")
    print(f"  channel_spend    : {len(spends)}")
    print(f"  period           : last {args.days} days")
    print("\n  by stage:")
    for s in STAGE_FUNNEL:
        print(f"    {s:<12s} {by_stage.get(s, 0):>6d}")
    print("\n  by source:")
    for ch in sorted(by_source, key=by_source.get, reverse=True):
        print(f"    {ch:<14s} {by_source[ch]:>6d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
