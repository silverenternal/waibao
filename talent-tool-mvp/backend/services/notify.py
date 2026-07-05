"""多通道推送通知服务."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("recruittech.services.notify")


async def push(
    channel: str,
    user_id: str,
    title: str,
    content: str,
    payload: Optional[dict] = None,
) -> bool:
    """统一推送入口."""
    if channel == "web":
        return await _push_web(user_id, title, content, payload)
    if channel == "email":
        return await _push_email(user_id, title, content, payload)
    if channel == "dingtalk":
        return await _push_dingtalk(user_id, title, content, payload)
    if channel == "feishu":
        return await _push_feishu(user_id, title, content, payload)
    if channel == "wecom":
        return await _push_wecom(user_id, title, content, payload)
    logger.warning(f"[notify] unknown channel: {channel}")
    return False


async def _push_web(user_id, title, content, payload) -> bool:
    """Web Push (MVP: 写到 realtime 通道 + DB)."""
    logger.info(f"[notify-web] {user_id}: {title}")
    return True


async def _push_email(user_id, title, content, payload) -> bool:
    """邮件 (MVP: log; 生产接 SendGrid/SMTP)."""
    logger.info(f"[notify-email] {user_id}: {title} - {content[:80]}")
    return True


async def _push_dingtalk(user_id, title, content, payload) -> bool:
    """钉钉机器人 webhook (MVP: log)."""
    logger.info(f"[notify-dingtalk] {user_id}: {title}")
    return True


async def _push_feishu(user_id, title, content, payload) -> bool:
    """飞书机器人 webhook (MVP: log)."""
    logger.info(f"[notify-feishu] {user_id}: {title}")
    return True


async def _push_wecom(user_id, title, content, payload) -> bool:
    """企业微信 (MVP: log)."""
    logger.info(f"[notify-wecom] {user_id}: {title}")
    return True