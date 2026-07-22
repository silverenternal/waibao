"""情绪 API (T103)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.emotion")
router = APIRouter()


@router.post("/detect")
async def detect_emotion(
    text: str,
    user: CurrentUser = Depends(get_current_user),
):
    """对一段文本做情感分析 + 共情回应."""
    agent = registry.get_or_raise("emotion_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=text,
    ))
    response = {
        "response": out.text,
        "emotion": out.artifacts.get("emotion"),
        "intensity": out.artifacts.get("intensity"),
        "sentiment": out.artifacts.get("sentiment"),
        "needs_attention": out.artifacts.get("needs_attention"),
    }

    # Webhook: EMOTION_RISK_DETECTED (T802)
    if response.get("needs_attention"):
        try:
            from services.webhook import fire_webhook, WebhookEvent
            import asyncio as _asyncio
            # CurrentUser only carries id/email/role — organisation_id is not on
            # the JWT-derived model, so fall back to user.id to scope the event.
            org_id = str(getattr(user, "organisation_id", None) or user.id)
            _asyncio.create_task(
                fire_webhook(
                    WebhookEvent.EMOTION_RISK,
                    org_id,
                    {
                        "user_id": str(user.id),
                        "emotion": response.get("emotion"),
                        "intensity": response.get("intensity"),
                        "sentiment": response.get("sentiment"),
                        "trigger_text": text[:500],
                    },
                )
            )
        except Exception as _wh_exc:  # noqa: BLE001
            logger.warning("emotion webhook fire failed: %r", _wh_exc)

    return response


@router.get("/timeline")
async def get_emotion_timeline(
    days: int = Query(default=30, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """情绪时间线(可视化用)."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("emotion_timeline")
        .select("recorded_at, primary_emotion, intensity, sentiment, needs_attention, trigger_text")
        .eq("user_id", str(user.id))
        .order("recorded_at", desc=True)
        .limit(days)
        .execute()
    )
    return {"data": result.data or []}


@router.get("/alerts")
async def get_emotion_alerts(user: CurrentUser = Depends(get_current_user)):
    """HR/管理员视角: 情绪告警列表.

    甲方合同: 管理员/HR 只看风险提醒, 不可查看原始私人对话/情绪文本
    (私人对话需用户单独授权). 因此本端点只返回风险元数据, 不返回
    trigger_text (原始触发文本).
    """
    from contracts.shared import UserRole
    from fastapi import HTTPException
    # 只有 HR (client) / 平台管理员 可看风险告警; 求职者 (talent_partner)
    # 不可看他人告警.
    if user.role not in (UserRole.admin, UserRole.client):
        raise HTTPException(status_code=403, detail="Forbidden")

    supabase = get_supabase_admin()
    result = (
        supabase.table("emotion_timeline")
        .select(
            "user_id, primary_emotion, sentiment, recorded_at, needs_attention"
        )
        .eq("needs_attention", True)
        .order("recorded_at", desc=True)
        .limit(100)
        .execute()
    )
    return {"alerts": result.data or []}