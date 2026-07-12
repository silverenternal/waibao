"""T1704 — 告警服务 (Alerting Service).

提供:
  - ``Alert`` / ``AlertSeverity`` / ``AlertChannel`` / ``AlertStatus`` 数据模型
  - ``AlertingService`` 主入口: 接收 alert, 路由到对应 channel
  - 4 个 Channel 实现:
      * ``DingTalkChannel`` — 钉钉群机器人 (签名 + markdown)
      * ``FeishuChannel`` — 飞书群机器人 (签名 + interactive card)
      * ``PagerDutyChannel`` — PagerDuty Events API v2
      * ``WebhookChannel`` — 通用 Webhook (含降级到本地文件)
  - 严重度到通道映射:
      * P0 (critical) → PagerDuty + 钉钉 oncall + 飞书 oncall + Webhook
      * P1 (high)     → 钉钉 + 飞书 + Webhook
      * P2 (warning)  → 钉钉 + 飞书
      * P3 (info)     → 飞书
  - 限流 (per-alert 60s 抑制) + 历史 + 告警记录

设计原则:
  - **never raise** — 告警发送失败不能影响主链路
  - **async first** — 提供 async 接口 (fire_async) 供 FastAPI 调用
  - **no external SDK 强依赖** — 仅用 stdlib (urllib, json, hmac, hashlib)
  - **测试友好** — Channel 是 Protocol, 易于 mock

Usage:
    >>> from services.observability.alerting import (
    ...     AlertingService, Alert, AlertSeverity,
    ...     get_default_service,
    ... )
    >>> svc = get_default_service()
    >>> alert = Alert(
    ...     name="HighErrorRate",
    ...     severity=AlertSeverity.P0,
    ...     summary="HTTP 5xx > 5%",
    ...     labels={"service": "backend"},
    ... )
    >>> svc.fire(alert)

环境变量:
    DINGTALK_WEBHOOK_URL       钉钉机器人 webhook (含 access_token)
    DINGTALK_SECRET            钉钉签名密钥 (可选)
    FEISHU_WEBHOOK_URL         飞书机器人 webhook
    FEISHU_SECRET              飞书签名密钥 (可选)
    PAGERDUTY_ROUTING_KEY      PagerDuty Events API v2 routing key
    PAGERDUTY_API_URL          (可选, 默认 https://events.pagerduty.com/v2/enqueue)
    ALERT_WEBHOOK_URL          通用 webhook URL
    ALERT_WEBHOOK_AUTH_HEADER  通用 webhook Authorization header (可选)
    ALERT_LOG_FILE             离线降级: 告警 JSON 写到本文件 (默认 logs/alerts.log)
    ALERT_DRY_RUN              1 = 不真发, 仅写日志
"""
from __future__ import annotations

import asyncio
import hmac
import base64
import hashlib
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable
from uuid import uuid4

logger = logging.getLogger("waibao.alerting")

# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------

class AlertSeverity(str, Enum):
    """告警严重度 — 与 prometheus alert rule 的 severity label 一致."""
    P0 = "critical"     # 5 分钟响应 — 触发 PagerDuty + oncall
    P1 = "high"         # 15 分钟响应
    P2 = "warning"      # 1 小时响应
    P3 = "info"         # 仅记录


class AlertChannel(str, Enum):
    """支持的通知通道."""
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


class AlertStatus(str, Enum):
    """告警生命周期状态."""
    FIRING = "firing"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"  # 因限流被抑制


@dataclass
class Alert:
    """一条告警的结构化数据.

    Attributes:
        name: 告警规则名 (e.g. ``HighErrorRate``)
        severity: 严重度
        summary: 一行摘要
        description: 详细描述 (可多行)
        labels: Prometheus / Grafana 风格标签
        annotations: 自由文本注释
        value: 触发值 (e.g. 错误率 0.07)
        source: 来源 (e.g. ``prometheus``, ``app``, ``sentry``)
        runbook_url: 处理手册链接
        starts_at: 触发时间 (UTC)
        ends_at: 结束时间 (resolved 时填)
        fingerprint: 唯一指纹 (用于去重 / 抑制); 默认 name+labels hash
    """
    name: str
    severity: AlertSeverity
    summary: str
    description: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)
    value: float | None = None
    source: str = "app"
    runbook_url: str | None = None
    starts_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ends_at: datetime | None = None
    fingerprint: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.severity, str):
            self.severity = _parse_severity(self.severity)
        if self.fingerprint is None:
            # 稳定指纹 = name + sorted(labels) 的 sha256 前 16
            h = hashlib.sha256()
            h.update(self.name.encode())
            for k in sorted(self.labels):
                h.update(f"|{k}={self.labels[k]}".encode())
            self.fingerprint = h.hexdigest()[:16]

    def get_status(self) -> AlertStatus:
        return AlertStatus.RESOLVED if self.ends_at else AlertStatus.FIRING

    @property
    def status(self) -> AlertStatus:
        """计算属性 — 不存储为字段."""
        return self.get_status()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["status"] = self.get_status().value
        d["starts_at"] = self.starts_at.isoformat()
        d["ends_at"] = self.ends_at.isoformat() if self.ends_at else None
        d["fingerprint"] = self.fingerprint
        return d


def _parse_severity(value: str) -> AlertSeverity:
    """允许输入: 'P0' / 'p0' / 'critical' / 'crit' / 'P0_CRITICAL'."""
    if not isinstance(value, str):
        return AlertSeverity(value)
    v = value.strip()
    # 直接匹配枚举值
    for sev in AlertSeverity:
        if v == sev.value or v == sev.name:
            return sev
    # 简化别名
    aliases = {
        "p0": AlertSeverity.P0, "p0_critical": AlertSeverity.P0, "crit": AlertSeverity.P0,
        "p1": AlertSeverity.P1, "p1_high": AlertSeverity.P1,
        "p2": AlertSeverity.P2, "p2_warning": AlertSeverity.P2, "warn": AlertSeverity.P2,
        "p3": AlertSeverity.P3, "p3_info": AlertSeverity.P3,
    }
    if v.lower() in aliases:
        return aliases[v.lower()]
    return AlertSeverity(v)  # 让 Enum 抛清晰错误


# ---------------------------------------------------------------------------
# Channel Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Channel(Protocol):
    """通知通道协议."""
    name: AlertChannel

    def send(self, alert: Alert) -> bool:  # pragma: no cover
        """同步发送. 返回 True=成功, False=失败."""
        ...

    async def send_async(self, alert: Alert) -> bool:  # pragma: no cover
        """异步发送."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hmac_sign_dingtalk(secret: str, ts_ms: int) -> str:
    """钉钉加签算法 — 见 https://open.dingtalk.com/document/orgapp/custom-robot-access."""
    string_to_sign = f"{ts_ms}\n{secret}"
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return sign


def _hmac_sign_feishu(secret: str, ts: int) -> str:
    """飞书加签算法 — 见 https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot."""
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode()


def _http_post_json(url: str, payload: dict[str, Any], headers: Mapping[str, str] | None = None,
                    timeout: float = 5.0) -> tuple[int, str]:
    """stdlib HTTP POST — 不引入 requests, 避免污染依赖."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "waibao-alerting/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("alerting.http_post_failed url=%s err=%s", url, e)
        return 0, str(e)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

class DingTalkChannel:
    """钉钉群机器人 Webhook."""

    name = AlertChannel.DINGTALK

    def __init__(self, webhook_url: str | None = None, secret: str | None = None,
                 at_mobiles: list[str] | None = None, at_all: bool = False) -> None:
        self.webhook_url = webhook_url or os.getenv("DINGTALK_WEBHOOK_URL", "")
        self.secret = secret or os.getenv("DINGTALK_SECRET", "")
        self.at_mobiles = at_mobiles or []
        self.at_all = at_all

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def _build_url(self) -> str:
        if not self.secret:
            return self.webhook_url
        ts_ms = int(round(time.time() * 1000))
        sign = _hmac_sign_dingtalk(self.secret, ts_ms)
        sep = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{sep}timestamp={ts_ms}&sign={sign}"

    def _build_payload(self, alert: Alert) -> dict[str, Any]:
        emoji = {"critical": "🔥", "high": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(
            alert.severity.value, "📢"
        )
        title = f"{emoji} [{alert.severity.value.upper()}] {alert.name}"
        text_lines = [
            f"## {title}",
            f"**Summary**: {alert.summary}",
        ]
        if alert.description:
            text_lines.append(f"**Detail**: {alert.description}")
        if alert.value is not None:
            text_lines.append(f"**Value**: {alert.value}")
        if alert.labels:
            labels_str = ", ".join(f"{k}={v}" for k, v in alert.labels.items())
            text_lines.append(f"**Labels**: {labels_str}")
        if alert.runbook_url:
            text_lines.append(f"**Runbook**: {alert.runbook_url}")
        text_lines.append(f"**Time**: {alert.starts_at.isoformat()}")
        text_lines.append(f"**Fingerprint**: {alert.fingerprint}")

        payload: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": "\n\n".join(text_lines),
            },
        }
        if self.at_all:
            payload["at"] = {"isAtAll": True}
        elif self.at_mobiles:
            payload["at"] = {"atMobiles": self.at_mobiles}
        return payload

    def send(self, alert: Alert) -> bool:
        if not self.enabled:
            logger.debug("dingtalk.disabled")
            return False
        url = self._build_url()
        payload = self._build_payload(alert)
        status, body = _http_post_json(url, payload)
        ok = 200 <= status < 300 and '"errcode":0' in body.replace(" ", "")
        if ok:
            logger.info("dingtalk.sent fingerprint=%s", alert.fingerprint)
        else:
            logger.warning("dingtalk.failed status=%s body=%s", status, body[:200])
        return ok

    async def send_async(self, alert: Alert) -> bool:
        return await asyncio.to_thread(self.send, alert)


class FeishuChannel:
    """飞书群机器人 Webhook."""

    name = AlertChannel.FEISHU

    def __init__(self, webhook_url: str | None = None, secret: str | None = None,
                 at_user_ids: list[str] | None = None) -> None:
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self.secret = secret or os.getenv("FEISHU_SECRET", "")
        self.at_user_ids = at_user_ids or []

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def _build_payload(self, alert: Alert) -> dict[str, Any]:
        color = {
            "critical": "red",
            "high": "orange",
            "warning": "yellow",
            "info": "blue",
        }.get(alert.severity.value, "grey")

        fields = [
            {"tag": "text", "text": f"Summary: {alert.summary}"},
        ]
        if alert.description:
            fields.append({"tag": "text", "text": f"Detail: {alert.description}"})
        if alert.value is not None:
            fields.append({"tag": "text", "text": f"Value: {alert.value}"})
        if alert.labels:
            fields.append({
                "tag": "text",
                "text": "Labels: " + ", ".join(f"{k}={v}" for k, v in alert.labels.items()),
            })
        if alert.runbook_url:
            fields.append({"tag": "text", "text": f"Runbook: {alert.runbook_url}"})
        fields.append({"tag": "text", "text": f"Time: {alert.starts_at.isoformat()}"})

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"[{alert.severity.value.upper()}] {alert.name}"},
                "template": color,
            },
            "elements": [{"tag": "div", "fields": fields}],
        }
        if self.at_user_ids:
            card["elements"].append({
                "tag": "at",
                "users": [{"id": uid} for uid in self.at_user_ids],
            })
        return {"msg_type": "interactive", "card": card}

    def _sign(self) -> tuple[int, str] | None:
        """返回 (timestamp, sign), 无 secret 时为 None."""
        if not self.secret:
            return None
        ts = int(time.time())
        return ts, _hmac_sign_feishu(self.secret, ts)

    def send(self, alert: Alert) -> bool:
        if not self.enabled:
            return False
        url = self.webhook_url
        payload = self._build_payload(alert)
        sign_data = self._sign()
        if sign_data:
            payload["timestamp"] = str(sign_data[0])
            payload["sign"] = sign_data[1]
        status, body = _http_post_json(url, payload)
        ok = 200 <= status < 300 and ('"StatusCode":0' in body or '"code":0' in body)
        if ok:
            logger.info("feishu.sent fingerprint=%s", alert.fingerprint)
        else:
            logger.warning("feishu.failed status=%s body=%s", status, body[:200])
        return ok

    async def send_async(self, alert: Alert) -> bool:
        return await asyncio.to_thread(self.send, alert)


class PagerDutyChannel:
    """PagerDuty Events API v2."""

    name = AlertChannel.PAGERDUTY

    P0_URGENCY = "high"
    DEFAULT_URGENCY = "low"

    def __init__(self, routing_key: str | None = None,
                 api_url: str | None = None) -> None:
        self.routing_key = routing_key or os.getenv("PAGERDUTY_ROUTING_KEY", "")
        self.api_url = api_url or os.getenv(
            "PAGERDUTY_API_URL", "https://events.pagerduty.com/v2/enqueue"
        )

    @property
    def enabled(self) -> bool:
        return bool(self.routing_key)

    def _build_payload(self, alert: Alert) -> dict[str, Any]:
        # PagerDuty dedup_key = fingerprint, 便于合并 + 自动 resolve
        urgency = self.P0_URGENCY if alert.severity == AlertSeverity.P0 else self.DEFAULT_URGENCY
        custom = {
            "alert_name": alert.name,
            "severity": alert.severity.value,
            "summary": alert.summary,
            "description": alert.description,
            "value": alert.value,
            "labels": dict(alert.labels),
            "annotations": dict(alert.annotations),
            "fingerprint": alert.fingerprint,
            "source": alert.source,
        }
        return {
            "routing_key": self.routing_key,
            "event_action": "resolve" if alert.status == AlertStatus.RESOLVED else "trigger",
            "dedup_key": alert.fingerprint,
            "payload": {
                "summary": f"[{alert.severity.value.upper()}] {alert.name}: {alert.summary}",
                "source": alert.source,
                "severity": alert.severity.value,
                "custom_details": custom,
                "timestamp": alert.starts_at.isoformat(),
            },
            "client": "waibao-alerting/1.0",
        }

    def send(self, alert: Alert) -> bool:
        if not self.enabled:
            return False
        payload = self._build_payload(alert)
        status, body = _http_post_json(self.api_url, payload)
        ok = status in (200, 201, 202) and '"status":"success"' in body
        if ok:
            logger.info("pagerduty.sent fingerprint=%s action=%s",
                        alert.fingerprint, payload["event_action"])
        else:
            logger.warning("pagerduty.failed status=%s body=%s", status, body[:200])
        return ok

    async def send_async(self, alert: Alert) -> bool:
        return await asyncio.to_thread(self.send, alert)


class WebhookChannel:
    """通用 Webhook 通道 — 也作本地日志降级."""

    name = AlertChannel.WEBHOOK

    def __init__(self, url: str | None = None, auth_header: str | None = None,
                 log_file: str | None = None) -> None:
        self.url = url or os.getenv("ALERT_WEBHOOK_URL", "")
        self.auth_header = auth_header or os.getenv("ALERT_WEBHOOK_AUTH_HEADER", "")
        self.log_file = log_file or os.getenv("ALERT_LOG_FILE", "logs/alerts.log")
        self._log_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def _write_local(self, alert: Alert) -> None:
        """无 URL 时写本地日志, 永不丢告警."""
        try:
            os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
            line = json.dumps(alert.to_dict(), ensure_ascii=False) + "\n"
            with self._log_lock:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as e:  # noqa: BLE001
            logger.warning("webhook.local_write_failed err=%s", e)

    def send(self, alert: Alert) -> bool:
        if not self.enabled:
            self._write_local(alert)
            return True  # 本地写入视为成功 (降级)
        headers: dict[str, str] = {}
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        status, body = _http_post_json(self.url, alert.to_dict(), headers=headers)
        ok = 200 <= status < 300
        if ok:
            logger.info("webhook.sent fingerprint=%s", alert.fingerprint)
        else:
            logger.warning("webhook.failed status=%s body=%s", status, body[:200])
            self._write_local(alert)  # 失败也降级
        return ok

    async def send_async(self, alert: Alert) -> bool:
        return await asyncio.to_thread(self.send, alert)


# ---------------------------------------------------------------------------
# AlertingService — 入口
# ---------------------------------------------------------------------------

# 严重度 → 通道 默认路由
DEFAULT_ROUTING: dict[AlertSeverity, list[AlertChannel]] = {
    AlertSeverity.P0: [AlertChannel.PAGERDUTY, AlertChannel.DINGTALK, AlertChannel.FEISHU, AlertChannel.WEBHOOK],
    AlertSeverity.P1: [AlertChannel.DINGTALK, AlertChannel.FEISHU, AlertChannel.WEBHOOK],
    AlertSeverity.P2: [AlertChannel.DINGTALK, AlertChannel.FEISHU],
    AlertSeverity.P3: [AlertChannel.FEISHU],
}


class AlertingService:
    """告警服务主入口.

    Args:
        channels: 已实例化的 channel 字典 (key=AlertChannel)
        routing: 严重度 → 通道列表 映射, 默认 ``DEFAULT_ROUTING``
        suppress_window_sec: 同一 fingerprint 在此秒数内的重复告警被抑制 (默认 60s)
        dry_run: True 时仅写日志不外发
    """

    def __init__(
        self,
        channels: Mapping[AlertChannel, Channel] | None = None,
        routing: Mapping[AlertSeverity, Iterable[AlertChannel]] | None = None,
        suppress_window_sec: int = 60,
        dry_run: bool | None = None,
    ) -> None:
        self.channels: dict[AlertChannel, Channel] = dict(channels or {})
        self.routing: dict[AlertSeverity, list[AlertChannel]] = {
            k: list(v) for k, v in (routing or DEFAULT_ROUTING).items()
        }
        self.suppress_window_sec = suppress_window_sec
        self.dry_run = (
            dry_run if dry_run is not None
            else os.getenv("ALERT_DRY_RUN", "0") == "1"
        )
        self._last_sent_at: dict[str, float] = {}
        self._history: list[dict[str, Any]] = []
        self._history_lock = threading.Lock()

    # ----- 注册 -----
    def register_channel(self, channel: Channel) -> None:
        self.channels[channel.name] = channel

    # ----- 主入口 -----
    def fire(self, alert: Alert) -> dict[str, Any]:
        """同步发送一条告警. 返回结果摘要."""
        return self._dispatch(alert)

    def resolve(self, name: str, labels: Mapping[str, str] | None = None,
                summary: str = "auto-resolved") -> dict[str, Any]:
        """便捷: 触发 resolved 状态告警."""
        alert = Alert(
            name=name,
            severity=AlertSeverity.P3,
            summary=summary,
            labels=labels or {},
            ends_at=datetime.now(timezone.utc),
        )
        return self._dispatch(alert)

    async def fire_async(self, alert: Alert) -> dict[str, Any]:
        return await asyncio.to_thread(self._dispatch, alert)

    # ----- 实现 -----
    def _dispatch(self, alert: Alert) -> dict[str, Any]:
        # 抑制
        if self._is_suppressed(alert):
            logger.info("alert.suppressed fingerprint=%s name=%s",
                        alert.fingerprint, alert.name)
            self._record(alert, AlertStatus.SUPPRESSED, sent={})
            return {"status": "suppressed", "fingerprint": alert.fingerprint}

        targets = self.routing.get(alert.severity, [])
        sent: dict[str, bool] = {}

        if self.dry_run:
            logger.info("alert.dry_run fingerprint=%s name=%s severity=%s channels=%s",
                        alert.fingerprint, alert.name, alert.severity.value,
                        [c.value for c in targets])
            self._last_sent_at[alert.fingerprint] = time.time()
            self._record(alert, AlertStatus.FIRING, sent={c.value: True for c in targets})
            return {"status": "dry_run", "fingerprint": alert.fingerprint,
                    "channels": [c.value for c in targets]}

        for ch_name in targets:
            ch = self.channels.get(ch_name)
            if ch is None:
                logger.debug("alert.channel_missing name=%s", ch_name.value)
                sent[ch_name.value] = False
                continue
            try:
                sent[ch_name.value] = bool(ch.send(alert))
            except Exception as e:  # noqa: BLE001
                logger.warning("alert.channel_error name=%s err=%s", ch_name.value, e)
                sent[ch_name.value] = False

        any_success = any(sent.values())
        self._last_sent_at[alert.fingerprint] = time.time()
        status = AlertStatus.FIRING if alert.status == AlertStatus.FIRING else AlertStatus.RESOLVED
        self._record(alert, status, sent=sent)

        result = {
            "status": "sent" if any_success else "failed",
            "fingerprint": alert.fingerprint,
            "channels": sent,
        }
        logger.info("alert.fired name=%s severity=%s channels=%s",
                    alert.name, alert.severity.value, sent)
        return result

    def _is_suppressed(self, alert: Alert) -> bool:
        if self.suppress_window_sec <= 0:
            return False
        # 解决 (resolved) 永远立即发出
        if alert.status == AlertStatus.RESOLVED:
            return False
        last = self._last_sent_at.get(alert.fingerprint)
        if last is None:
            return False
        return (time.time() - last) < self.suppress_window_sec

    def _record(self, alert: Alert, status: AlertStatus,
                sent: Mapping[str, bool]) -> None:
        with self._history_lock:
            self._history.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "alert": alert.to_dict(),
                "status": status.value,
                "channels": dict(sent),
            })
            # 保留最近 1000 条
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

    # ----- 查询 -----
    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._history_lock:
            return list(self._history[-limit:])

    def stats(self) -> dict[str, Any]:
        with self._history_lock:
            total = len(self._history)
            by_sev: dict[str, int] = {}
            for r in self._history:
                sev = r["alert"].get("severity", "?")
                by_sev[sev] = by_sev.get(sev, 0) + 1
        return {"total": total, "by_severity": by_sev,
                "channels": {c.value: bool(getattr(ch, "enabled", True))
                             for c, ch in self.channels.items()}}


# ---------------------------------------------------------------------------
# 全局单例 + 默认工厂
# ---------------------------------------------------------------------------

_default_service: AlertingService | None = None
_default_service_lock = threading.Lock()


def _build_default_channels() -> dict[AlertChannel, Channel]:
    return {
        AlertChannel.DINGTALK: DingTalkChannel(),
        AlertChannel.FEISHU: FeishuChannel(),
        AlertChannel.PAGERDUTY: PagerDutyChannel(),
        AlertChannel.WEBHOOK: WebhookChannel(),
    }


def get_default_service() -> AlertingService:
    """获取默认告警服务单例 (懒加载)."""
    global _default_service
    with _default_service_lock:
        if _default_service is None:
            _default_service = AlertingService(
                channels=_build_default_channels(),
                routing=DEFAULT_ROUTING,
            )
        return _default_service


def reset_default_service() -> None:
    """测试用: 重置默认单例."""
    global _default_service
    with _default_service_lock:
        _default_service = None


def fire(name: str, severity: str | AlertSeverity = "warning",
         summary: str = "", **kwargs: Any) -> dict[str, Any]:
    """便捷函数: 用默认服务触发告警."""
    sev = _parse_severity(severity) if isinstance(severity, str) else severity
    alert = Alert(name=name, severity=sev, summary=summary, **kwargs)
    return get_default_service().fire(alert)


__all__ = [
    "AlertSeverity",
    "AlertChannel",
    "AlertStatus",
    "Alert",
    "Channel",
    "DingTalkChannel",
    "FeishuChannel",
    "PagerDutyChannel",
    "WebhookChannel",
    "AlertingService",
    "DEFAULT_ROUTING",
    "get_default_service",
    "reset_default_service",
    "fire",
]
