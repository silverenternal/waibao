#!/usr/bin/env python3
"""T3801 — Pilot 中型企业批量创建脚本.

功能:
1. 读取 docs/pilot/PILOT_CANDIDATES_V8.md 候选名单 (硬编码 fallback).
2. 对每家创建 organisation + pilot_programs + 默认邀请 SPOC.
3. 输出 JSON 报告 (program_id, admin_token, invite_urls).

环境变量:
- SUPABASE_URL, SUPABASE_SERVICE_KEY   (生产/预生产)
- PILOT_FRONTEND_BASE_URL              (默认 http://localhost:3000)
- DRY_RUN=1                            (只打印, 不写 DB)

用法:
    python scripts/seed_pilot_partners.py [--dry-run] [--candidates path/to/json]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_pilot_partners")


# ---------------------------------------------------------------------------
# 默认候选名单 (与 docs/pilot/PILOT_CANDIDATES_V8.md 同步)
# ---------------------------------------------------------------------------
DEFAULT_CANDIDATES: list[dict[str, Any]] = [
    {
        "slug": "globex-ecommerce",
        "name": "Globex E-Commerce Ltd",
        "country": "UK",
        "industry": "cross_border_ecommerce",
        "size_band": "100-500",
        "hires_per_month": 12,
        "spoc_email": "sarah.chen@globex.example",
        "spoc_name": "Sarah Chen",
        "spoc_role": "Head of People",
        "data_residency": "UK",
    },
    {
        "slug": "nexus-ai",
        "name": "NexusAI Technology Co., Ltd",
        "country": "CN",
        "industry": "ai_llm",
        "size_band": "100-500",
        "hires_per_month": 8,
        "spoc_email": "lin.wei@nexusai.example",
        "spoc_name": "Lin Wei",
        "spoc_role": "CTO",
        "data_residency": "CN",
    },
    {
        "slug": "finpath-capital",
        "name": "FinPath Capital Pte Ltd",
        "country": "SG",
        "industry": "fintech",
        "size_band": "100-500",
        "hires_per_month": 6,
        "spoc_email": "anand.krishnan@finpath.example",
        "spoc_name": "Anand Krishnan",
        "spoc_role": "Talent Lead",
        "data_residency": "SG",
    },
    {
        "slug": "talentforge-saas",
        "name": "TalentForge SaaS GmbH",
        "country": "DE",
        "industry": "hrtech",
        "size_band": "100-500",
        "hires_per_month": 5,
        "spoc_email": "klaus.mueller@talentforge.example",
        "spoc_name": "Klaus Mueller",
        "spoc_role": "VP People",
        "data_residency": "EU",
    },
    {
        "slug": "verda-logistics",
        "name": "Verda Logistics B.V.",
        "country": "NL",
        "industry": "cross_border_logistics",
        "size_band": "100-500",
        "hires_per_month": 18,
        "spoc_email": "marieke.devries@verda.example",
        "spoc_name": "Marieke de Vries",
        "spoc_role": "Head of Recruitment",
        "data_residency": "EU",
    },
    {
        "slug": "bluepeak-studios",
        "name": "BluePeak Studios Ltd",
        "country": "CN",
        "industry": "gaming",
        "size_band": "100-500",
        "hires_per_month": 10,
        "spoc_email": "wang.hao@bluepeak.example",
        "spoc_name": "Wang Hao",
        "spoc_role": "HR Director",
        "data_residency": "CN",
    },
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_supabase():
    try:
        from api.deps import get_supabase_admin  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.error("Cannot import api.deps: %s", exc)
        raise SystemExit(3) from exc
    return get_supabase_admin()


def _seed_org(supabase, candidate: dict[str, Any]) -> str:
    """确保 organisation 存在, 返回 id."""
    existing = (
        supabase.table("organisations")
        .select("id")
        .eq("slug", candidate["slug"])
        .limit(1)
        .execute()
    )
    if existing.data:
        org_id = existing.data[0]["id"]
        logger.info("organisation exists: %s -> %s", candidate["slug"], org_id)
        return org_id

    row = {
        "id": str(uuid.uuid4()),
        "slug": candidate["slug"],
        "name": candidate["name"],
        "country": candidate["country"],
        "industry": candidate["industry"],
        "size_band": candidate["size_band"],
        "metadata": {
            "source": "pilot_seed",
            "hires_per_month": candidate["hires_per_month"],
            "data_residency": candidate["data_residency"],
        },
    }
    res = supabase.table("organisations").insert(row).execute()
    org_id = res.data[0]["id"]
    logger.info("created organisation: %s -> %s", candidate["name"], org_id)
    return org_id


def _seed_program(supabase, candidate: dict[str, Any], org_id: str) -> str:
    """创建 pilot_programs (status=recruiting)."""
    program_name = f"Pilot 30d — {candidate['name']}"
    existing = (
        supabase.table("pilot_programs")
        .select("id,status")
        .eq("organisation_id", org_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        pid = existing.data[0]["id"]
        logger.info("pilot program exists: %s -> %s", program_name, pid)
        return pid

    row = {
        "id": str(uuid.uuid4()),
        "organisation_id": org_id,
        "name": program_name,
        "description": (
            f"30 天免费 Pilot 合作, {candidate['hires_per_month']} hires/month, "
            f"data residency={candidate['data_residency']}"
        ),
        "status": "recruiting",
        "target_nps": 40,
        "max_users": 20,
        "metadata": {
            "spoc_email": candidate["spoc_email"],
            "spoc_name": candidate["spoc_name"],
            "spoc_role": candidate["spoc_role"],
            "industry": candidate["industry"],
            "country": candidate["country"],
            "hires_per_month": candidate["hires_per_month"],
        },
    }
    res = supabase.table("pilot_programs").insert(row).execute()
    pid = res.data[0]["id"]
    logger.info("created pilot program: %s -> %s", program_name, pid)
    return pid


def _seed_invitation(supabase, candidate: dict[str, Any], program_id: str) -> dict[str, Any]:
    """为 SPOC 生成一次性邀请 token."""
    try:
        from services.integrations.pilot_invitation import (
            build_invite_url,
            generate_invite_token,
        )
    except Exception:
        generate_invite_token = None  # type: ignore
        build_invite_url = None  # type: ignore

    if generate_invite_token is None:
        # fallback
        import secrets

        token = secrets.token_urlsafe(32)
        base = os.getenv("PILOT_FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
        invite_url = f"{base}/onboarding/accept?token={token}"
    else:
        token = generate_invite_token()
        invite_url = build_invite_url(token)

    row = {
        "id": str(uuid.uuid4()),
        "program_id": program_id,
        "email": candidate["spoc_email"],
        "role": "talent_partner",
        "token": token,
        "invited_by": None,
        "invited_at": _now(),
        "expires_at": _now_plus(days=14),
        "status": "pending",
        "metadata": {
            "spoc_name": candidate["spoc_name"],
            "spoc_role": candidate["spoc_role"],
        },
    }
    try:
        res = supabase.table("pilot_invitations").insert(row).execute()
        invitation_id = res.data[0]["id"]
    except Exception as exc:  # pragma: no cover
        logger.warning("pilot_invitations insert failed: %s", exc)
        invitation_id = row["id"]
    return {"id": invitation_id, "invite_url": invite_url, "token": token}


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


def _now_plus(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(tz=timezone.utc) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(candidates: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    if dry_run:
        logger.info("DRY RUN — skipping DB writes")
        for c in candidates:
            out.append({"candidate": c["slug"], "dry_run": True})
        return {"status": "dry_run", "count": len(out), "items": out}

    supabase = _get_supabase()
    for c in candidates:
        try:
            org_id = _seed_org(supabase, c)
            program_id = _seed_program(supabase, c, org_id)
            inv = _seed_invitation(supabase, c, program_id)
            out.append({
                "candidate": c["slug"],
                "organisation_id": org_id,
                "program_id": program_id,
                "invitation": inv,
            })
        except Exception as exc:  # pragma: no cover
            logger.exception("seed failed for %s: %s", c["slug"], exc)
            out.append({"candidate": c["slug"], "error": str(exc)})
    return {"status": "ok", "count": len(out), "items": out}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed pilot partner orgs + programs.")
    parser.add_argument("--dry-run", action="store_true", help="不写 DB, 只打印。")
    parser.add_argument("--candidates", help="JSON 文件路径, 覆盖默认候选名单。")
    args = parser.parse_args(argv)

    candidates = DEFAULT_CANDIDATES
    if args.candidates:
        with open(args.candidates, "r", encoding="utf-8") as fp:
            candidates = json.load(fp)

    result = run(candidates, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())