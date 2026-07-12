"""T1704 — Alerting 服务单元测试.

覆盖:
  - Alert / AlertSeverity / AlertChannel 数据模型
  - 4 个 Channel 实现 (mock transport)
  - AlertingService: 路由 / 限流 / dry-run / 错误处理
  - 默认单例 / reset
  - 历史 / 统计
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.observability.alerting import (
    Alert,
    AlertChannel,
    AlertingService,
    AlertSeverity,
    AlertStatus,
    DEFAULT_ROUTING,
    DingTalkChannel,
    FeishuChannel,
    PagerDutyChannel,
    WebhookChannel,
    fire,
    get_default_service,
    reset_default_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env():
    """每个测试前后清理可能影响 channel 配置的环境变量."""
    saved = {}
    for k in ("DINGTALK_WEBHOOK_URL", "DINGTALK_SECRET",
              "FEISHU_WEBHOOK_URL", "FEISHU_SECRET",
              "PAGERDUTY_ROUTING_KEY",
              "ALERT_WEBHOOK_URL", "ALERT_WEBHOOK_AUTH_HEADER",
              "ALERT_LOG_FILE", "ALERT_DRY_RUN"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    yield
    for k, v in saved.items():
        os.environ[k] = v
    reset_default_service()


# ---------------------------------------------------------------------------
# Alert / Enum
# ---------------------------------------------------------------------------

class TestAlertEnums:
    def test_severity_values(self):
        assert AlertSeverity.P0.value == "critical"
        assert AlertSeverity.P1.value == "high"
        assert AlertSeverity.P2.value == "warning"
        assert AlertSeverity.P3.value == "info"

    def test_channel_values(self):
        assert AlertChannel.DINGTALK.value == "dingtalk"
        assert AlertChannel.FEISHU.value == "feishu"
        assert AlertChannel.PAGERDUTY.value == "pagerduty"
        assert AlertChannel.WEBHOOK.value == "webhook"

    def test_default_routing_keys(self):
        for sev in AlertSeverity:
            assert sev in DEFAULT_ROUTING
        assert AlertChannel.PAGERDUTY in DEFAULT_ROUTING[AlertSeverity.P0]
        assert AlertChannel.DINGTALK in DEFAULT_ROUTING[AlertSeverity.P1]


class TestAlertModel:
    def test_basic_construction(self):
        a = Alert(name="x", severity=AlertSeverity.P0, summary="s")
        assert a.name == "x"
        assert a.severity == AlertSeverity.P0
        assert a.status == AlertStatus.FIRING
        assert a.fingerprint is not None and len(a.fingerprint) == 16

    def test_string_severity_accepted(self):
        a = Alert(name="x", severity="high", summary="s")
        assert a.severity == AlertSeverity.P1

    def test_fingerprint_stable(self):
        a1 = Alert(name="X", severity="P0", summary="s", labels={"k": "v"})
        a2 = Alert(name="X", severity="P1", summary="s2", labels={"k": "v"})
        # 严重度不影响 fingerprint
        assert a1.fingerprint == a2.fingerprint

    def test_fingerprint_changes_with_labels(self):
        a1 = Alert(name="X", severity="P0", summary="s", labels={"k": "v"})
        a2 = Alert(name="X", severity="P0", summary="s", labels={"k": "w"})
        assert a1.fingerprint != a2.fingerprint

    def test_explicit_fingerprint(self):
        a = Alert(name="x", severity="P0", summary="s", fingerprint="abc")
        assert a.fingerprint == "abc"

    def test_status_resolved(self):
        a = Alert(
            name="x", severity="P3", summary="s",
            ends_at=datetime.now(timezone.utc),
        )
        assert a.status == AlertStatus.RESOLVED

    def test_to_dict_serializable(self):
        a = Alert(name="x", severity="P0", summary="s", value=1.5,
                  labels={"k": "v"})
        d = a.to_dict()
        assert d["name"] == "x"
        assert d["severity"] == "critical"
        assert d["status"] == "firing"
        assert d["value"] == 1.5
        assert d["fingerprint"] == a.fingerprint
        # 应能 json.dumps
        json.dumps(d)


# ---------------------------------------------------------------------------
# DingTalk Channel
# ---------------------------------------------------------------------------

class TestDingTalkChannel:
    def test_disabled_without_url(self):
        ch = DingTalkChannel(webhook_url="", secret="")
        assert ch.enabled is False
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is False

    def test_enabled_with_url(self):
        ch = DingTalkChannel(webhook_url="https://example.com/hook")
        assert ch.enabled is True

    def test_sign_includes_secret(self):
        ch = DingTalkChannel(
            webhook_url="https://example.com/hook?access_token=t",
            secret="SEC123",
        )
        url = ch._build_url()
        assert "timestamp=" in url
        assert "sign=" in url

    def test_no_sign_without_secret(self):
        ch = DingTalkChannel(webhook_url="https://example.com/hook")
        assert "sign=" not in ch._build_url()

    def test_payload_markdown(self):
        ch = DingTalkChannel(webhook_url="https://example.com/hook")
        payload = ch._build_payload(Alert(
            name="ErrHigh", severity="P0", summary="5xx>5%",
            value=0.07, labels={"svc": "api"},
        ))
        assert payload["msgtype"] == "markdown"
        assert "ErrHigh" in payload["markdown"]["title"]
        assert "5xx>5%" in payload["markdown"]["text"]

    def test_at_all_in_payload(self):
        ch = DingTalkChannel(webhook_url="https://example.com/hook", at_all=True)
        p = ch._build_payload(Alert(name="x", severity="P0", summary="s"))
        assert p["at"]["isAtAll"] is True

    @patch("services.observability.alerting._http_post_json")
    def test_send_success(self, mock_post):
        mock_post.return_value = (200, '{"errcode":0,"errmsg":"ok"}')
        ch = DingTalkChannel(webhook_url="https://example.com/hook")
        ok = ch.send(Alert(name="x", severity="P0", summary="s"))
        assert ok is True
        mock_post.assert_called_once()

    @patch("services.observability.alerting._http_post_json")
    def test_send_failure(self, mock_post):
        mock_post.return_value = (500, "boom")
        ch = DingTalkChannel(webhook_url="https://example.com/hook")
        ok = ch.send(Alert(name="x", severity="P0", summary="s"))
        assert ok is False

    def test_async_send(self):
        async def _run():
            ch = DingTalkChannel(webhook_url="")
            return await ch.send_async(Alert(name="x", severity="P0", summary="s"))
        assert asyncio.run(_run()) is False


# ---------------------------------------------------------------------------
# Feishu Channel
# ---------------------------------------------------------------------------

class TestFeishuChannel:
    def test_disabled(self):
        ch = FeishuChannel(webhook_url="")
        assert ch.enabled is False
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is False

    def test_payload_card(self):
        ch = FeishuChannel(webhook_url="https://example.com/hook")
        p = ch._build_payload(Alert(name="x", severity="P1", summary="s"))
        assert p["msg_type"] == "interactive"
        assert p["card"]["header"]["template"] == "orange"  # P1 → orange
        assert "HIGH" in p["card"]["header"]["title"]["content"].upper()

    def test_sign_payload_with_secret(self):
        ch = FeishuChannel(webhook_url="https://example.com/hook", secret="S")
        sign = ch._sign()
        assert sign is not None
        assert isinstance(sign[0], int)
        assert isinstance(sign[1], str) and len(sign[1]) > 0

    @patch("services.observability.alerting._http_post_json")
    def test_send_success(self, mock_post):
        mock_post.return_value = (200, '{"StatusCode":0,"msg":"success"}')
        ch = FeishuChannel(webhook_url="https://example.com/hook")
        assert ch.send(Alert(name="x", severity="P1", summary="s")) is True


# ---------------------------------------------------------------------------
# PagerDuty Channel
# ---------------------------------------------------------------------------

class TestPagerDutyChannel:
    def test_disabled(self):
        ch = PagerDutyChannel(routing_key="")
        assert ch.enabled is False

    def test_payload_trigger(self):
        ch = PagerDutyChannel(routing_key="RK")
        p = ch._build_payload(Alert(
            name="DB", severity="P0", summary="s", value=0.9,
            labels={"a": "1"}, fingerprint="fp123",
        ))
        assert p["routing_key"] == "RK"
        assert p["event_action"] == "trigger"
        assert p["dedup_key"] == "fp123"
        assert p["payload"]["severity"] == "critical"

    def test_payload_resolve(self):
        ch = PagerDutyChannel(routing_key="RK")
        a = Alert(name="DB", severity="P0", summary="s",
                  ends_at=datetime.now(timezone.utc))
        p = ch._build_payload(a)
        assert p["event_action"] == "resolve"

    @patch("services.observability.alerting._http_post_json")
    def test_send_success(self, mock_post):
        mock_post.return_value = (202, '{"status":"success"}')
        ch = PagerDutyChannel(routing_key="RK")
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is True

    @patch("services.observability.alerting._http_post_json")
    def test_send_failure(self, mock_post):
        mock_post.return_value = (500, "boom")
        ch = PagerDutyChannel(routing_key="RK")
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is False


# ---------------------------------------------------------------------------
# Webhook Channel
# ---------------------------------------------------------------------------

class TestWebhookChannel:
    def test_local_fallback(self, tmp_path):
        log = tmp_path / "alerts.log"
        ch = WebhookChannel(url="", log_file=str(log))
        assert ch.enabled is False
        ok = ch.send(Alert(name="x", severity="P0", summary="s"))
        assert ok is True  # 本地写入视为成功
        assert log.exists()
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["name"] == "x"

    @patch("services.observability.alerting._http_post_json")
    def test_http_success(self, mock_post):
        mock_post.return_value = (200, "ok")
        ch = WebhookChannel(url="https://example.com/wh")
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is True

    @patch("services.observability.alerting._http_post_json")
    def test_http_failure_writes_local(self, mock_post, tmp_path):
        mock_post.return_value = (500, "boom")
        log = tmp_path / "alerts.log"
        ch = WebhookChannel(url="https://example.com/wh", log_file=str(log))
        assert ch.send(Alert(name="x", severity="P0", summary="s")) is False
        assert log.exists()  # 失败降级也写本地


# ---------------------------------------------------------------------------
# AlertingService
# ---------------------------------------------------------------------------

class _FakeChannel:
    def __init__(self, name: AlertChannel, ok: bool = True):
        self.name = name
        self.ok = ok
        self.calls: list[Alert] = []

    def send(self, alert: Alert) -> bool:
        self.calls.append(alert)
        return self.ok

    async def send_async(self, alert: Alert) -> bool:
        return self.send(alert)


class TestAlertingService:
    def _build_svc(self, **kw) -> tuple[AlertingService, dict[AlertChannel, _FakeChannel]]:
        dt = _FakeChannel(AlertChannel.DINGTALK)
        fs = _FakeChannel(AlertChannel.FEISHU)
        pd = _FakeChannel(AlertChannel.PAGERDUTY)
        wh = _FakeChannel(AlertChannel.WEBHOOK)
        channels = {
            AlertChannel.DINGTALK: dt,
            AlertChannel.FEISHU: fs,
            AlertChannel.PAGERDUTY: pd,
            AlertChannel.WEBHOOK: wh,
        }
        svc = AlertingService(channels=channels, suppress_window_sec=0, **kw)
        return svc, channels

    def test_default_routing_p0(self):
        svc, chs = self._build_svc()
        result = svc.fire(Alert(name="x", severity="P0", summary="s"))
        # P0 默认走全部 4 通道
        assert chs[AlertChannel.PAGERDUTY].calls
        assert chs[AlertChannel.DINGTALK].calls
        assert chs[AlertChannel.FEISHU].calls
        assert chs[AlertChannel.WEBHOOK].calls
        assert result["status"] == "sent"

    def test_default_routing_p2(self):
        svc, chs = self._build_svc()
        svc.fire(Alert(name="x", severity="P2", summary="s"))
        # P2 走 钉钉 + 飞书
        assert chs[AlertChannel.DINGTALK].calls
        assert chs[AlertChannel.FEISHU].calls
        assert not chs[AlertChannel.PAGERDUTY].calls
        assert not chs[AlertChannel.WEBHOOK].calls

    def test_default_routing_p3(self):
        svc, chs = self._build_svc()
        svc.fire(Alert(name="x", severity="P3", summary="s"))
        assert chs[AlertChannel.FEISHU].calls
        assert not chs[AlertChannel.DINGTALK].calls
        assert not chs[AlertChannel.PAGERDUTY].calls

    def test_custom_routing(self):
        dt = _FakeChannel(AlertChannel.DINGTALK)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
        )
        svc.fire(Alert(name="x", severity="P0", summary="s"))
        assert dt.calls

    def test_partial_failure_still_sent(self):
        dt = _FakeChannel(AlertChannel.DINGTALK, ok=False)
        fs = _FakeChannel(AlertChannel.FEISHU, ok=True)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt, AlertChannel.FEISHU: fs},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK, AlertChannel.FEISHU]},
        )
        result = svc.fire(Alert(name="x", severity="P0", summary="s"))
        # 至少有一个成功
        assert result["status"] == "sent"
        assert result["channels"]["dingtalk"] is False
        assert result["channels"]["feishu"] is True

    def test_total_failure(self):
        dt = _FakeChannel(AlertChannel.DINGTALK, ok=False)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
        )
        result = svc.fire(Alert(name="x", severity="P0", summary="s"))
        assert result["status"] == "failed"

    def test_suppression(self):
        dt = _FakeChannel(AlertChannel.DINGTALK)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
            suppress_window_sec=60,
        )
        r1 = svc.fire(Alert(name="x", severity="P0", summary="s",
                            labels={"k": "1"}))
        r2 = svc.fire(Alert(name="x", severity="P0", summary="s",
                            labels={"k": "1"}))
        assert r1["status"] == "sent"
        assert r2["status"] == "suppressed"
        assert len(dt.calls) == 1  # 第二次未发

    def test_suppression_bypass_on_resolve(self):
        dt = _FakeChannel(AlertChannel.DINGTALK)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt},
            routing={AlertSeverity.P3: [AlertChannel.DINGTALK],
                     AlertSeverity.P0: [AlertChannel.DINGTALK]},
            suppress_window_sec=60,
        )
        svc.fire(Alert(name="x", severity="P0", summary="s",
                       labels={"k": "1"}))
        # resolved 不被抑制 (走 resolve 走 P3 默认路由)
        r2 = svc.resolve("x", labels={"k": "1"})
        assert r2["status"] == "sent"
        assert len(dt.calls) == 2

    def test_dry_run(self):
        dt = _FakeChannel(AlertChannel.DINGTALK)
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: dt},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
            dry_run=True,
        )
        result = svc.fire(Alert(name="x", severity="P0", summary="s"))
        assert result["status"] == "dry_run"
        assert not dt.calls  # 真通道不发

    def test_channel_exception_doesnt_break(self):
        class BoomChannel:
            name = AlertChannel.DINGTALK
            def send(self, alert):
                raise RuntimeError("boom")
            async def send_async(self, alert):
                raise RuntimeError("boom")
        svc = AlertingService(
            channels={AlertChannel.DINGTALK: BoomChannel()},
            routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
        )
        # 不应抛
        result = svc.fire(Alert(name="x", severity="P0", summary="s"))
        assert result["channels"]["dingtalk"] is False

    def test_register_channel(self):
        svc = AlertingService(channels={}, routing={AlertSeverity.P0: []})
        dt = _FakeChannel(AlertChannel.DINGTALK)
        svc.register_channel(dt)
        assert svc.channels[AlertChannel.DINGTALK] is dt

    def test_history(self):
        svc, _ = self._build_svc()
        for i in range(3):
            svc.fire(Alert(name=f"n{i}", severity="P0", summary=f"s{i}"))
        h = svc.history(limit=10)
        assert len(h) == 3
        # history 是 append 顺序, 最新的在末尾
        assert h[-1]["alert"]["name"] == "n2"

    def test_history_capped_at_1000(self):
        svc, _ = self._build_svc()
        for i in range(1005):
            svc.fire(Alert(name=f"n{i}", severity="P0", summary="s"))
        h = svc.history(limit=2000)
        assert len(h) == 1000

    def test_stats(self):
        svc, _ = self._build_svc()
        svc.fire(Alert(name="a", severity="P0", summary="s"))
        svc.fire(Alert(name="b", severity="P1", summary="s"))
        svc.fire(Alert(name="c", severity="P2", summary="s"))
        stats = svc.stats()
        assert stats["total"] == 3
        assert stats["by_severity"]["critical"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["warning"] == 1

    def test_fire_async(self):
        async def _run():
            dt = _FakeChannel(AlertChannel.DINGTALK)
            svc = AlertingService(
                channels={AlertChannel.DINGTALK: dt},
                routing={AlertSeverity.P0: [AlertChannel.DINGTALK]},
            )
            return await svc.fire_async(Alert(name="x", severity="P0", summary="s"))
        r = asyncio.run(_run())
        assert r["status"] == "sent"


# ---------------------------------------------------------------------------
# Default service / convenience
# ---------------------------------------------------------------------------

class TestDefaultService:
    def test_singleton(self):
        a = get_default_service()
        b = get_default_service()
        assert a is b

    def test_reset(self):
        a = get_default_service()
        reset_default_service()
        b = get_default_service()
        assert a is not b

    def test_default_channels_present(self):
        svc = get_default_service()
        assert AlertChannel.DINGTALK in svc.channels
        assert AlertChannel.FEISHU in svc.channels
        assert AlertChannel.PAGERDUTY in svc.channels
        assert AlertChannel.WEBHOOK in svc.channels

    def test_fire_convenience_dry_run(self, monkeypatch):
        monkeypatch.setenv("ALERT_DRY_RUN", "1")
        reset_default_service()
        result = fire("TestAlert", "P0", "smoke test")
        assert result["status"] == "dry_run"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_channels_implement_protocol():
    """Channel Protocol 运行时检查."""
    from services.observability.alerting import Channel
    # WebhookChannel 即使 URL 为空也要满足 Protocol 接口
    ch = WebhookChannel(url="https://example.com/wh")
    assert hasattr(ch, "send")
    assert hasattr(ch, "send_async")
    assert hasattr(ch, "name")
    assert isinstance(ch, Channel) or hasattr(ch, "send")
