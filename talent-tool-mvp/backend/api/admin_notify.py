"""Admin Notification API (T104).

路径:
- GET  /api/admin/notify/channels          —— 列出所有可用通知通道及其启用状态
- POST /api/admin/notify/channels          —— 启用/禁用/更新某个通道配置
- GET  /api/admin/notify/channels/prefs    —— 列出用户的偏好 (可选 user_id 查询)
- POST /api/admin/notify/channels/prefs    —— 管理员为某用户写入偏好

权限: 全部需要 ``admin`` 角色 (沿用 ``require_role``).

通道运行时配置来源:
- 环境变量 (生产): ``NOTIFY_<CHANNEL>_ENABLED`` 控制 provider 是否走真实实现.
- DB 配置 (admin override): 后续可扩展为 ``notify_channel_configs`` 表;
  当前实现通过 ``os.environ`` 反映到 ``enabled`` 字段 (写操作会更新 env 并提示持久化).
  为避免污染运行时进程,实际写入仅修改 ``in-memory cache`` + 给前端返回新值,
  由部署脚本/CI 真正落地到 .env.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from providers.registry import reset_cache

logger = logging.getLogger("recruittech.api.admin_notify")

router = APIRouter()

# ---------------------------------------------------------------------------
# 通道元数据
# ---------------------------------------------------------------------------

SUPPORTED_CHANNELS: dict[str, dict[str, Any]] = {
    "smtp": {
        "label": "Email (SMTP / SendGrid)",
        "provider_class": "SMTPProvider",
        "env_enable_key": "NOTIFY_SMTP_ENABLED",
        "env_config_keys": [
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USERNAME",
            "SMTP_PASSWORD",
            "SMTP_FROM",
        ],
        "default_enabled": False,
    },
    "dingtalk": {
        "label": "DingTalk Robot",
        "provider_class": "DingTalkProvider",
        "env_enable_key": "NOTIFY_DINGTALK_ENABLED",
        "env_config_keys": ["DINGTALK_WEBHOOK", "DINGTALK_SECRET"],
        "default_enabled": False,
    },
    "feishu": {
        "label": "Feishu (Lark) Robot",
        "provider_class": "FeishuProvider",
        "env_enable_key": "NOTIFY_FEISHU_ENABLED",
        "env_config_keys": ["FEISHU_WEBHOOK", "FEISHU_SECRET"],
        "default_enabled": False,
    },
    "wecom": {
        "label": "WeCom Robot",
        "provider_class": "WeComProvider",
        "env_enable_key": "NOTIFY_WECOM_ENABLED",
        "env_config_keys": ["WECOM_WEBHOOK"],
        "default_enabled": False,
    },
    "webhook": {
        "label": "Generic Webhook",
        "provider_class": "WebhookProvider",
        "env_enable_key": "NOTIFY_WEBHOOK_ENABLED",
        "env_config_keys": ["WEBHOOK_URL", "WEBHOOK_AUTH_HEADER"],
        "default_enabled": False,
    },
    "web": {
        "label": "In-app Web (Realtime)",
        "provider_class": "RealtimeWebProvider",
        "env_enable_key": "NOTIFY_WEB_ENABLED",
        "env_config_keys": [],
        "default_enabled": True,  # Web 通道默认开启 (无外部依赖)
    },
}


def _read_channel_runtime(channel: str) -> dict[str, Any]:
    """读取 channel 的运行时配置 (env 状态 + 是否实际启用)."""
    meta = SUPPORTED_CHANNELS[channel]
    enable_key = meta["env_enable_key"]
    raw = os.getenv(enable_key, "")
    enabled = raw.lower() in ("1", "true", "yes") or (
        channel == "web" and meta["default_enabled"]
    )
    config: dict[str, str] = {}
    for k in meta["env_config_keys"]:
        v = os.getenv(k)
        if v:
            # 敏感字段脱敏
            if "PASSWORD" in k or "SECRET" in k or "TOKEN" in k:
                config[k] = "***" + v[-4:] if len(v) > 4 else "***"
            else:
                config[k] = v
    return {
        "channel": channel,
        "label": meta["label"],
        "provider_class": meta["provider_class"],
        "enabled": enabled,
        "env_enable_key": enable_key,
        "config": config,
    }


# ---------------------------------------------------------------------------
# 通道 CRUD
# ---------------------------------------------------------------------------


@router.get("/channels")
async def list_channels(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """列出所有支持的通道 + 当前启用状态.

    供 admin dashboard 渲染「通知中心」页.
    """
    return {"channels": [_read_channel_runtime(c) for c in SUPPORTED_CHANNELS]}


class ChannelUpdate(BaseModel):
    """通道更新请求体."""

    enabled: bool
    config: dict[str, str] = Field(default_factory=dict)


@router.post("/channels")
async def update_channel(
    payload: ChannelUpdate,
    channel: str = Query(..., description="smtp / dingtalk / feishu / wecom / webhook / web"),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """启用 / 禁用通道 + 更新其配置.

    注意:
    - ``config`` 中的 key 必须属于该 channel 的 ``env_config_keys`` 白名单.
    - 实际持久化: 进程内 ``os.environ`` (供 dispatcher 立即生效).
      部署级持久化需运维同步到 .env 或 secrets manager (返回 ``persist_hint``).
    """
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(
            status_code=404, detail=f"unknown channel: {channel}"
        )

    meta = SUPPORTED_CHANNELS[channel]
    allowed_keys = set(meta["env_config_keys"])
    rejected = [k for k in payload.config if k not in allowed_keys]
    if rejected:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid config keys for channel={channel}: {rejected}; "
                f"allowed={sorted(allowed_keys)}"
            ),
        )

    # 写入进程 env (dispatcher 下次 dispatch 即生效)
    os.environ[meta["env_enable_key"]] = "true" if payload.enabled else "false"
    for k, v in payload.config.items():
        # 前端回传的脱敏值 "***abcd" 不覆盖真实值;运维需直接填全量
        if v.startswith("***"):
            continue
        os.environ[k] = v

    # 清掉 provider 缓存,强制下次重新解析 env
    reset_cache()

    logger.info(
        "admin %s updated notify channel=%s enabled=%s keys=%s",
        user.id,
        channel,
        payload.enabled,
        list(payload.config.keys()),
    )

    new_state = _read_channel_runtime(channel)
    new_state["persist_hint"] = (
        f"Set {meta['env_enable_key']}={'true' if payload.enabled else 'false'} "
        "in your deployment env file (.env / secrets manager) to persist."
    )
    return new_state


# ---------------------------------------------------------------------------
# 用户偏好 (管理员视角)
# ---------------------------------------------------------------------------


class NotifyPrefUpsert(BaseModel):
    """管理员写入单条用户偏好."""

    user_id: UUID
    channel: str
    category: str
    enabled: bool = True
    channel_config: dict[str, Any] = Field(default_factory=dict)


@router.get("/channels/prefs")
async def list_prefs(
    user_id: Optional[UUID] = Query(default=None),
    channel: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """列出用户偏好 (可按 user_id / channel / category 过滤).

    无任何过滤时返回最近 limit 条 (供 admin dashboard 浏览).
    """
    supabase = get_supabase_admin()
    query = (
        supabase.table("notify_preferences")
        .select("*")
        .order("updated_at", desc=True)
        .limit(limit)
    )
    if user_id:
        query = query.eq("user_id", str(user_id))
    if channel:
        query = query.eq("channel", channel)
    if category:
        query = query.eq("category", category)

    result = query.execute()
    return {"preferences": result.data or []}


@router.post("/channels/prefs")
async def upsert_pref(
    payload: NotifyPrefUpsert,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """管理员为某用户写入一条偏好 (upsert by user_id+channel+category)."""
    if payload.channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"unknown channel: {payload.channel}")

    supabase = get_supabase_admin()
    record = {
        "user_id": str(payload.user_id),
        "channel": payload.channel,
        "category": payload.category,
        "enabled": payload.enabled,
        "channel_config": payload.channel_config,
    }

    # 先查;存在则 update;否则 insert
    existing = (
        supabase.table("notify_preferences")
        .select("id")
        .eq("user_id", record["user_id"])
        .eq("channel", payload.channel)
        .eq("category", payload.category)
        .maybe_single()
        .execute()
    )

    if existing and getattr(existing, "data", None):
        result = (
            supabase.table("notify_preferences")
            .update({
                "enabled": payload.enabled,
                "channel_config": payload.channel_config,
            })
            .eq("id", existing.data["id"])
            .execute()
        )
        action = "updated"
    else:
        result = supabase.table("notify_preferences").insert(record).execute()
        action = "created"

    if not result.data:
        raise HTTPException(status_code=500, detail="upsert failed: no data returned")

    logger.info(
        "admin %s %s notify pref user=%s channel=%s category=%s enabled=%s",
        user.id,
        action,
        payload.user_id,
        payload.channel,
        payload.category,
        payload.enabled,
    )
    return {"action": action, "preference": result.data[0]}


# ---------------------------------------------------------------------------
# 模板类型列表 (供前端 UI 下拉)
# ---------------------------------------------------------------------------


@router.get("/templates")
async def list_templates(
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """返回所有可用的通知模板类型 + 默认变量提示 (前端表单生成用)."""
    # 局部导入避免循环 (admin_notify 不依赖 dispatcher)
    from services.notify.templates import available_types

    return {"types": available_types()}