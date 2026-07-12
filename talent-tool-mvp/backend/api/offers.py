"""Offer + Negotiation API — T1302.

Endpoints:
    POST /api/offers                     创建 offer
    GET  /api/offers                     列出当前用户全部 offer
    GET  /api/offers/{id}                拉取单个 offer
    PATCH /api/offers/{id}               更新 offer (字段级)
    DELETE /api/offers/{id}              软删除
    POST /api/offers/compare             { offer_ids: [...] } -> 比较结果(雷达)
    POST /api/offers/{id}/negotiate      { market_role?, role_title? } -> 谈判脚本
    POST /api/offers/calculate           单 offer 计算(对比税前税后,用于实时预览)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.negotiation_advisor import generate_negotiation_script
from services.offer_calculator import (
    AnnualTotal,
    OfferInput,
    calculate_total_comp,
    compare_offers,
)

logger = logging.getLogger("recruittech.api.offers")
router = APIRouter()

# 内存仓储(mock 模式 / Supabase 不可用时)
_OFFERS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------
class OfferBody(BaseModel):
    title: str = ""
    company: str = ""
    role_level: str = ""
    location: str = "CN"  # CN / US / SG
    currency: str = "CNY"
    base_salary: float = 0.0
    bonus: float = 0.0
    bonus_target_pct: float = 0.0
    equity_value: float = 0.0
    equity_vesting_years: int = 4
    benefits: float = 0.0
    signing_bonus: float = 0.0
    pto_days: int = 0
    extras: dict[str, Any] = Field(default_factory=dict)


class CompareBody(BaseModel):
    offer_ids: list[str] = Field(..., min_length=1, max_length=6)
    include_new: Optional[list[OfferBody]] = None  # 用于"实时虚拟"


class NegotiateBody(BaseModel):
    market_role: str = "backend_engineer"  # 用于市场分位查表
    market_percentile: Optional[int] = None
    market_value: Optional[float] = None
    market_band: Optional[list[int]] = None
    language: str = "zh"
    extras: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist(offer: dict[str, Any]) -> None:
    try:
        sb = get_supabase_admin()
        sb.table("user_offers").upsert(offer).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"persist offer supabase failed: {e}")


def _delete_persist(offer_id: str) -> None:
    try:
        sb = get_supabase_admin()
        sb.table("user_offers").update({"deleted_at": _now()}).eq("id", offer_id).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"delete persist failed: {e}")


def _build_offer_row(body: OfferBody, user_id: str, *, offer_id: Optional[str] = None) -> dict[str, Any]:
    oid = offer_id or str(uuid.uuid4())
    return {
        "id": oid,
        "user_id": user_id,
        "title": body.title,
        "company": body.company,
        "role_level": body.role_level,
        "location": body.location,
        "currency": body.currency,
        "base_salary": body.base_salary,
        "bonus": body.bonus,
        "bonus_target_pct": body.bonus_target_pct,
        "equity_value": body.equity_value,
        "equity_vesting_years": body.equity_vesting_years,
        "benefits": body.benefits,
        "signing_bonus": body.signing_bonus,
        "pto_days": body.pto_days,
        "extras": body.extras,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _serialize_offer(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != "deleted_at"}


def _annual_total_dict(at: AnnualTotal) -> dict[str, Any]:
    return {
        "location": at.location,
        "currency": at.currency,
        "gross": at.gross,
        "tax": at.tax,
        "social": at.social,
        "net": at.net,
        "benefits": at.benefits,
        "equity_pv": at.equity_pv,
        "bonus": at.bonus,
        "signing_bonus": at.signing_bonus,
        "total_comp": at.total_comp,
        "total_with_signing": at.total_with_signing,
        "monthly_net": at.monthly_net,
        "effective_tax_rate": at.effective_tax_rate,
        "notes": at.notes,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", summary="创建 offer")
async def create_offer(body: OfferBody, user: CurrentUser = Depends(get_current_user)):
    row = _build_offer_row(body, str(user.id))
    _OFFERS[row["id"]] = row
    _persist(row)
    total = calculate_total_comp(OfferInput(**{k: v for k, v in row.items() if k in OfferInput.__annotations__}))
    return {"offer": _serialize_offer(row), "total": _annual_total_dict(total)}


@router.get("", summary="列出我的 offers")
async def list_offers(user: CurrentUser = Depends(get_current_user)):
    rows = [r for r in _OFFERS.values() if r.get("user_id") == str(user.id)]
    return {"offers": [_serialize_offer(r) for r in rows]}


@router.get("/{offer_id}", summary="拉取单个 offer")
async def get_offer(offer_id: str, user: CurrentUser = Depends(get_current_user)):
    row = _OFFERS.get(offer_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="offer not found")
    total = calculate_total_comp(OfferInput(**{k: v for k, v in row.items() if k in OfferInput.__annotations__}))
    return {"offer": _serialize_offer(row), "total": _annual_total_dict(total)}


@router.patch("/{offer_id}", summary="更新 offer")
async def update_offer(
    offer_id: str, body: OfferBody, user: CurrentUser = Depends(get_current_user)
):
    row = _OFFERS.get(offer_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="offer not found")
    new_row = _build_offer_row(body, str(user.id), offer_id=offer_id)
    new_row["created_at"] = row.get("created_at") or _now()
    _OFFERS[offer_id] = new_row
    _persist(new_row)
    total = calculate_total_comp(OfferInput(**{k: v for k, v in new_row.items() if k in OfferInput.__annotations__}))
    return {"offer": _serialize_offer(new_row), "total": _annual_total_dict(total)}


@router.delete("/{offer_id}", summary="删除 offer")
async def delete_offer(offer_id: str, user: CurrentUser = Depends(get_current_user)):
    row = _OFFERS.get(offer_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="offer not found")
    row["deleted_at"] = _now()
    _OFFERS[offer_id] = row
    _delete_persist(offer_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /calculate  — 单 offer 实时预览
# ---------------------------------------------------------------------------
@router.post("/calculate", summary="单 offer 实时预览")
async def calculate_endpoint(body: OfferBody, user: CurrentUser = Depends(get_current_user)):
    o = OfferInput(**body.model_dump())
    at = calculate_total_comp(o)
    return {"total": _annual_total_dict(at)}


# ---------------------------------------------------------------------------
# POST /compare
# ---------------------------------------------------------------------------
@router.post("/compare", summary="比较多个 offer")
async def compare_endpoint(body: CompareBody, user: CurrentUser = Depends(get_current_user)):
    raw_offers: list[OfferInput] = []
    titles: list[str] = []
    for oid in body.offer_ids:
        row = _OFFERS.get(oid)
        if not row or row.get("user_id") != str(user.id):
            raise HTTPException(status_code=404, detail=f"offer {oid} not found")
        o = OfferInput(**{k: v for k, v in row.items() if k in OfferInput.__annotations__})
        raw_offers.append(o)
        titles.append(o.title or o.company or oid)

    # 合并 include_new
    if body.include_new:
        for nb in body.include_new:
            o = OfferInput(**nb.model_dump())
            raw_offers.append(o)
            titles.append(o.title or "虚拟")

    if not raw_offers:
        raise HTTPException(status_code=400, detail="no offers to compare")

    # 给 OfferInput 注入 title 给 comparison 用
    class TitledOffer(OfferInput):
        pass

    titled: list[TitledOffer] = []
    for t, o in zip(titles, raw_offers):
        new = TitledOffer(**{**o.__dict__, "title": t})
        titled.append(new)

    cmp = compare_offers(titled)
    return {
        "offers": [_annual_total_dict(t) for t in cmp.offers],
        "best_by_total": cmp.best_by_total,
        "best_by_monthly_net": cmp.best_by_monthly_net,
        "radar": cmp.radar,
        "rank": cmp.rank,
        "market": cmp.market,
    }


# ---------------------------------------------------------------------------
# POST /{id}/negotiate
# ---------------------------------------------------------------------------
@router.post("/{offer_id}/negotiate", summary="生成谈判策略")
async def negotiate_endpoint(
    offer_id: str, body: NegotiateBody, user: CurrentUser = Depends(get_current_user)
):
    row = _OFFERS.get(offer_id)
    if not row or row.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="offer not found")
    o = OfferInput(**{k: v for k, v in row.items() if k in OfferInput.__annotations__})
    market = {
        "role": body.market_role,
        "percentile": body.market_percentile,
        "value_in_market_unit": body.market_value,
        "band": body.market_band,
    }
    script = await generate_negotiation_script(
        o, market_data=market, language=body.language
    )
    return {
        "offer_id": offer_id,
        "offer_title": script.offer_title,
        "region": script.region,
        "currency": script.currency,
        "current_total": script.current_total,
        "target_total": script.target_total,
        "walkaway_threshold": script.walkaway_threshold,
        "percent_in_market": script.percent_in_market,
        "market_band": script.market_band,
        "overall_advice": script.overall_advice,
        "talking_points": script.talking_points,
        "email_template": script.email_template,
        "counter_examples": script.counter_examples,
        "tactics": [
            {
                "title": t.title,
                "rationale": t.rationale,
                "expected_uplift_pct": t.expected_uplift_pct,
                "risk": t.risk,
            }
            for t in script.tactics
        ],
        "next_steps": script.next_steps,
        "provider": script.provider,
    }
