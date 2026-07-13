"""v8.1 T3601 — Proactive Outreach.

主动关怀推送 — 复用 v6.0 notify dispatcher (in-app + email + 钉钉 + 飞书).

触发场景 (来自 relationship.candidates_for_outreach):

    1. re_engage_3d       — ACTIVE 阶段 3+ 天没互动,温柔提醒
    2. long_break_checkin — ON_BREAK 阶段 7+ 天,周末/节日问候
    3. offer_followup     — NEGOTIATING 阶段,offer 谈判跟进

执行流程:

    candidate → 触发规则 → 渲染模板 → 检查配额/静默 → dispatcher.dispatch_multi
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .relationship import (
    RelationshipService,
    RelationshipStage,
    get_relationship_service,
)

logger = logging.getLogger("recruittech.services.jobseeker.proactive_outreach")


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class OutreachMessage:
    user_id: str
    reason: str
    title: str
    body: str
    channels: List[str] = field(default_factory=lambda: ["in_app"])
    cta: Optional[str] = None
    cta_url: Optional[str] = None
    priority: str = "normal"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "reason": self.reason,
            "title": self.title,
            "body": self.body,
            "channels": list(self.channels),
            "cta": self.cta,
            "cta_url": self.cta_url,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------
_TEMPLATES = {
    "re_engage_3d": {
        "title": "好久不见 {name} 👋",
        "body": (
            "最近 {days} 天没有看到你了,是想换个方向,还是简历需要润色?\n"
            "我帮你准备了 3 个本周新职位,要不要看看?"
        ),
        "cta": "看看新职位",
        "priority": "low",
    },
    "long_break_checkin": {
        "title": "{name},休息得怎么样?",
        "body": (
            "你已经暂停求职 {days} 天了,不用有压力。\n"
            "如果你想回来,我可以帮你温习一下之前的进展。"
        ),
        "cta": "回来看一眼",
        "priority": "low",
    },
    "offer_followup": {
        "title": "offer 谈判进展如何?",
        "body": (
            "你正在和 {company} 谈 offer,要不要我帮你算一下"
            "整体薪酬包 + 谈判话术?"
        ),
        "cta": "打开谈判助手",
        "priority": "high",
    },
    "birthday": {
        "title": "🎂 生日快乐 {name}!",
        "body": "新的一岁,愿你心想事成。要不要我把最近的优质机会汇总给你?",
        "cta": "看看",
        "priority": "low",
    },
    "festival": {
        "title": "{festival_name} 快乐 🎉",
        "body": "节日期间招聘市场相对安静,适合做自我提升。推荐你看这篇文章:",
        "cta": "阅读",
        "priority": "low",
    },
}


def render_template(reason: str, *, name: str = "同学", **kw: Any) -> OutreachMessage:
    tpl = _TEMPLATES.get(reason)
    if not tpl:
        return OutreachMessage(
            user_id="",
            reason=reason,
            title=f"({reason})",
            body="",
        )
    # format 用 default 防止缺字段
    import re as _re

    def _safe_format(s: str, **vals: Any) -> str:
        def repl(m: "_re.Match[str]") -> str:
            key = m.group(1)
            return str(vals.get(key, f"{{{key}}}"))
        return _re.sub(r"\{(\w+)\}", repl, s)

    return OutreachMessage(
        user_id="",
        reason=reason,
        title=_safe_format(tpl["title"], name=name, **kw),
        body=_safe_format(tpl["body"], name=name, **kw),
        cta=tpl.get("cta"),
        priority=tpl.get("priority", "normal"),
        metadata=kw,
    )


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------
class ProactiveOutreachService:
    """主动 push 编排器.

    设计:
        - 状态机: RelationshipService (单独模块, 不耦合)
        - 通道:    notify.dispatcher (in-app + email + 钉钉 + 飞书)
        - 节流:    RelationshipService.can_push / in_quiet_hours
    """

    def __init__(
        self,
        relationship: Optional[RelationshipService] = None,
        *,
        max_per_day: int = 3,
        default_channels: Optional[List[str]] = None,
    ) -> None:
        self.relationship = relationship or get_relationship_service()
        self.max_per_day = max_per_day
        self.default_channels = default_channels or ["in_app", "email"]

    # ----------------- 单用户 -----------------
    async def reach_out(
        self,
        user_id: str,
        reason: str,
        *,
        name: str = "同学",
        channels: Optional[List[str]] = None,
        force: bool = False,
        **template_kw: Any,
    ) -> OutreachMessage:
        """单用户触发一条主动 push."""
        msg = render_template(reason, name=name, **template_kw)
        msg.user_id = user_id
        msg.channels = channels or list(self.default_channels)

        # 1. 静默时段检查 (除非 force=True)
        if not force and self.relationship.in_quiet_hours():
            logger.info("skip push user=%s reason=%s (quiet hours)", user_id, reason)
            msg.metadata["skipped"] = "quiet_hours"
            return msg

        # 2. 配额检查
        if not force and not self.relationship.can_push(user_id, max_per_day=self.max_per_day):
            logger.info("skip push user=%s reason=%s (quota)", user_id, reason)
            msg.metadata["skipped"] = "quota"
            return msg

        # 3. 推送
        await self._dispatch(msg)
        self.relationship.record_push(user_id)
        return msg

    # ----------------- 批量扫描 -----------------
    async def run_scheduled_pass(self, *, max_users: int = 100) -> List[OutreachMessage]:
        """每小时跑一次,从 RelationshipService 找候选用户."""
        candidates = self.relationship.candidates_for_outreach(max_users=max_users)
        results: List[OutreachMessage] = []
        for c in candidates:
            try:
                msg = await self.reach_out(
                    user_id=c["user_id"],
                    reason=c["reason"],
                    name="同学",
                    days=c.get("days_since_interaction", 0),
                )
                results.append(msg)
            except Exception as e:  # noqa: BLE001
                logger.warning("outreach failed user=%s: %s", c["user_id"], e)
        return results

    # ----------------- 推送实现 -----------------
    async def _dispatch(self, msg: OutreachMessage) -> Dict[str, Any]:
        """把消息送到 notify dispatcher."""
        try:
            from services.notify import dispatcher as notify_dispatcher

            outcome = await notify_dispatcher.dispatch_multi(
                [
                    {
                        "channel": ch,
                        "to": msg.user_id,
                        "title": msg.title,
                        "body": msg.body,
                        "data": {
                            "reason": msg.reason,
                            "cta": msg.cta,
                            "cta_url": msg.cta_url,
                            "priority": msg.priority,
                            **msg.metadata,
                        },
                    }
                    for ch in msg.channels
                ],
                template_name=f"proactive_{msg.reason}",
            )
            return outcome.to_dict()
        except Exception as e:  # noqa: BLE001
            logger.warning("dispatcher failed (likely dev mode): %s", e)
            return {"success": False, "error": str(e), "channels": msg.channels}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_service: Optional[ProactiveOutreachService] = None


def get_outreach_service() -> ProactiveOutreachService:
    global _service
    if _service is None:
        _service = ProactiveOutreachService()
    return _service


def reset_outreach_service() -> None:
    global _service
    _service = None