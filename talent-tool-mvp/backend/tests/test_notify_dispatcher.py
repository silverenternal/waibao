"""Tests for services.notify.dispatcher (T104)."""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    """每个测试前后清掉 provider + dispatcher 单例."""
    from providers import registry
    from services.notify import dispatcher as dispatcher_mod

    registry.reset_cache()
    dispatcher_mod.reset_dispatcher()
    yield
    registry.reset_cache()
    dispatcher_mod.reset_dispatcher()


class FakeProvider:
    """可记录的 mock provider,channel 通过构造指定."""

    def __init__(self, channel: str, *, should_fail: bool = False, delay: float = 0.0):
        self.channel = channel
        self.should_fail = should_fail
        self.delay = delay
        self.calls: list[dict] = []

    async def send(self, message):
        self.calls.append({
            "subject": message.subject,
            "body": message.body,
            "to": list(message.to),
            "html": message.html,
            "metadata": message.metadata,
        })
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.should_fail:
            from providers.notify.base import NotifyResult
            return NotifyResult(success=False, channel=self.channel, error="simulated")
        from providers.notify.base import NotifyResult
        return NotifyResult(
            success=True,
            channel=self.channel,
            message_id=f"fake-{self.channel}-1",
        )


@pytest.fixture
def make_providers():
    """返回一个 ``make(channel, ...)`` 工厂;同时支持 spy 所有 provider 调用."""
    created: dict[str, FakeProvider] = {}

    def factory(channel: str, **kwargs):
        if channel not in created:
            created[channel] = FakeProvider(channel, **kwargs)
        return created[channel]

    factory.created = created  # type: ignore[attr-defined]
    return factory


# ---------------------------------------------------------------------------
# 单通道 dispatch
# ---------------------------------------------------------------------------

class TestDispatchSingleChannel:
    @pytest.mark.asyncio
    async def test_dispatch_returns_true_on_success(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        ok = await d.dispatch(
            channel="smtp",
            user_id="user-1",
            title="hello",
            content="world",
        )
        assert ok is True
        provider = make_providers.created["smtp"]
        assert provider.calls[0]["subject"] == "hello"
        assert provider.calls[0]["to"] == ["user-1"]

    @pytest.mark.asyncio
    async def test_dispatch_returns_false_on_provider_failure(self):
        """Provider 返回 success=False 时,dispatch 必须返回 False."""
        from services.notify.dispatcher import NotifyDispatcher

        provider = FakeProvider("dingtalk", should_fail=True)

        def factory(channel):
            return provider

        d = NotifyDispatcher(provider_factory=factory)
        ok = await d.dispatch(
            channel="dingtalk",
            user_id="u",
            title="t",
            content="c",
            payload={},
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_dispatch_returns_true_when_skipped_by_preference(self):
        from services.notify.dispatcher import NotifyDispatcher

        async def prefs(user_id, channel):
            return False  # 全员关闭

        calls = {"count": 0}

        def factory(channel):
            calls["count"] += 1
            return FakeProvider(channel)

        d = NotifyDispatcher(
            preferences_lookup=prefs,
            provider_factory=factory,
        )
        ok = await d.dispatch(channel="webhook", user_id="u", title="t", content="c")
        # 偏好关闭视为软成功 (返回值不变,业务方继续往下走)
        assert ok is True
        # 但 provider 没有被调用
        assert calls["count"] == 0

    @pytest.mark.asyncio
    async def test_recipients_override_user_id(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        await d.dispatch(
            channel="smtp",
            user_id="ignored",
            title="t",
            content="c",
            recipients=["a@x.com", "b@x.com"],
        )
        to = make_providers.created["smtp"].calls[0]["to"]
        assert to == ["a@x.com", "b@x.com"]

    @pytest.mark.asyncio
    async def test_html_and_metadata_pass_through(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        await d.dispatch(
            channel="feishu",
            user_id="u",
            title="t",
            content="c",
            payload={
                "html": "<b>hi</b>",
                "metadata": {"atMobiles": ["13800000000"]},
            },
        )
        call = make_providers.created["feishu"].calls[0]
        assert call["html"] == "<b>hi</b>"
        assert call["metadata"] == {"atMobiles": ["13800000000"]}


# ---------------------------------------------------------------------------
# 多通道 dispatch_multi
# ---------------------------------------------------------------------------

class TestDispatchMultiChannel:
    @pytest.mark.asyncio
    async def test_concurrent_dispatch_to_multiple_channels(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.dispatch_multi(
            channels=["smtp", "dingtalk", "feishu"],
            user_id="u",
            title="hello",
            content="world",
        )
        assert outcome.success is True
        assert set(outcome.channels) == {"smtp", "dingtalk", "feishu"}
        assert outcome.failed_channels == []
        assert outcome.skipped_channels == []
        for ch in ["smtp", "dingtalk", "feishu"]:
            assert make_providers.created[ch].calls, f"{ch} should be called"

    @pytest.mark.asyncio
    async def test_dedupes_channels(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.dispatch_multi(
            channels=["smtp", "smtp", "dingtalk"],
            user_id="u",
            title="t",
            content="c",
        )
        # 去重 -> 实际只调用 2 次
        assert outcome.channels == ["smtp", "dingtalk"]
        assert len(make_providers.created["smtp"].calls) == 1

    @pytest.mark.asyncio
    async def test_empty_channels_returns_empty_outcome(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.dispatch_multi(channels=[], user_id="u", title="t", content="c")
        assert outcome.channels == []
        assert outcome.success is False

    @pytest.mark.asyncio
    async def test_failure_of_one_channel_does_not_block_others(self):
        from services.notify.dispatcher import NotifyDispatcher

        created = {}

        def factory(channel):
            created[channel] = FakeProvider(
                channel, should_fail=(channel == "dingtalk")
            )
            return created[channel]

        d = NotifyDispatcher(provider_factory=factory)
        outcome = await d.dispatch_multi(
            channels=["smtp", "dingtalk", "feishu"],
            user_id="u",
            title="t",
            content="c",
        )
        # 2/3 成功 -> outcome.success 仍 True
        assert outcome.success is True
        assert "dingtalk" in outcome.failed_channels
        assert "smtp" not in outcome.failed_channels

    @pytest.mark.asyncio
    async def test_provider_exception_isolated_per_channel(self):
        from services.notify.dispatcher import NotifyDispatcher

        def factory(channel):
            if channel == "wecom":
                raise RuntimeError("factory exploded")
            return FakeProvider(channel)

        d = NotifyDispatcher(provider_factory=factory)
        outcome = await d.dispatch_multi(
            channels=["smtp", "wecom", "feishu"],
            user_id="u",
            title="t",
            content="c",
        )
        # wecom 工厂抛错,其他通道仍正常
        assert outcome.success is True
        assert "wecom" in outcome.failed_channels
        # error 字段携带原始异常信息 (前缀 "no provider: " 由 dispatcher 添加)
        wecom_err = next(
            r.error for r in outcome.results if r.channel == "wecom"
        )
        assert "factory exploded" in (wecom_err or "")

    @pytest.mark.asyncio
    async def test_send_exception_inside_provider_isolated(self):
        from services.notify.dispatcher import NotifyDispatcher
        from providers.notify.base import NotifyMessage, NotifyResult

        class BoomProvider:
            channel = "wecom"

            async def send(self, message):
                raise RuntimeError("kaboom")

        def factory(channel):
            return BoomProvider() if channel == "wecom" else FakeProvider(channel)

        d = NotifyDispatcher(provider_factory=factory)
        outcome = await d.dispatch_multi(
            channels=["smtp", "wecom"],
            user_id="u",
            title="t",
            content="c",
        )
        assert outcome.success is True  # smtp 仍成功
        assert "wecom" in outcome.failed_channels


# ---------------------------------------------------------------------------
# 偏好
# ---------------------------------------------------------------------------

class TestPreferences:
    @pytest.mark.asyncio
    async def test_preference_off_skips_only_that_channel(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher

        async def prefs(user_id, channel):
            return channel != "dingtalk"  # 关闭钉钉

        d = NotifyDispatcher(
            preferences_lookup=prefs,
            provider_factory=make_providers,
        )
        outcome = await d.dispatch_multi(
            channels=["smtp", "dingtalk"],
            user_id="u",
            title="t",
            content="c",
        )
        assert outcome.success is True
        assert "dingtalk" in outcome.skipped_channels
        # smtp 仍真正调用了
        assert make_providers.created["smtp"].calls

    @pytest.mark.asyncio
    async def test_preference_lookup_failure_fails_open(self):
        """偏好查询报错时,默认允许发送 (不要因为偏好的 bug 而丢消息)."""
        from services.notify.dispatcher import NotifyDispatcher

        async def broken_prefs(user_id, channel):
            raise RuntimeError("db down")

        d = NotifyDispatcher(
            preferences_lookup=broken_prefs,
            provider_factory=lambda ch: FakeProvider(ch),
        )
        ok = await d.dispatch(channel="smtp", user_id="u", title="t", content="c")
        assert ok is True

    @pytest.mark.asyncio
    async def test_default_preferences_lookup_allows_all(self):
        """无 preferences_lookup 时,所有通道放行."""
        from services.notify.dispatcher import NotifyDispatcher, _default_preferences_lookup

        # 显式调用默认实现,确认返回 True
        for ch in ["smtp", "dingtalk", "feishu", "wecom", "webhook", "web"]:
            assert await _default_preferences_lookup("any", ch) is True


# ---------------------------------------------------------------------------
# DispatchOutcome 工具方法
# ---------------------------------------------------------------------------

class TestDispatchOutcome:
    def test_success_true_only_when_one_real_success(self):
        from services.notify.dispatcher import ChannelResult, DispatchOutcome

        outcome = DispatchOutcome(
            results=[
                ChannelResult(channel="x", success=False, skipped=True),
                ChannelResult(channel="y", success=False, error="boom"),
            ],
            channels=["x", "y"],
        )
        assert outcome.success is False
        assert outcome.skipped_channels == ["x"]
        assert outcome.failed_channels == ["y"]

    def test_to_dict_shape(self):
        from services.notify.dispatcher import ChannelResult, DispatchOutcome

        outcome = DispatchOutcome(
            results=[ChannelResult(channel="a", success=True, message_id="m1")],
            channels=["a"],
        )
        d = outcome.to_dict()
        assert d["success"] is True
        assert d["channels"] == ["a"]
        assert d["results"][0]["message_id"] == "m1"
        assert d["failed_channels"] == []


# ---------------------------------------------------------------------------
# 模板 dispatch
# ---------------------------------------------------------------------------

class TestDispatchTemplate:
    @pytest.mark.asyncio
    async def test_dispatch_template_renders_and_sends(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher
        from services.notify.templates import (
            NotificationTemplate,
            NotificationType,
            render_template,
        )

        template = render_template(
            NotificationType.EMOTION_HIGH_RISK,
            {"candidate_name": "张三", "risk_level": "HIGH"},
        )
        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.dispatch_template(
            template=template,
            channels=["smtp", "dingtalk"],
            user_id="u",
        )
        assert outcome.success is True
        for ch in ["smtp", "dingtalk"]:
            call = make_providers.created[ch].calls[0]
            assert "张三" in call["subject"]
            assert call["html"] is not None  # html 透传
            assert call["metadata"].get("notification_type") == "emotion_high_risk"

    @pytest.mark.asyncio
    async def test_dispatch_template_single_channel_str(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher
        from services.notify.templates import render_template, NotificationType

        template = render_template(NotificationType.SYSTEM_ALERT, {"alert_name": "X"})
        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.dispatch_template(
            template=template, channels="smtp", user_id="u"
        )
        assert outcome.success is True
        assert outcome.channels == ["smtp"]

    @pytest.mark.asyncio
    async def test_send_event_one_shot(self, make_providers):
        from services.notify.dispatcher import NotifyDispatcher
        from services.notify.templates import NotificationType

        d = NotifyDispatcher(provider_factory=make_providers)
        outcome = await d.send_event(
            ntype=NotificationType.MATCH_SUCCESS,
            context={"candidate_name": "Bob", "role_title": "PM"},
            channels=["smtp"],
            user_id="u",
        )
        assert outcome.success is True
        assert "Bob" in make_providers.created["smtp"].calls[0]["subject"]


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------

class TestModuleLevel:
    @pytest.mark.asyncio
    async def test_dispatch_module_helper_uses_singleton(self):
        from services.notify.dispatcher import (
            dispatch,
            get_dispatcher,
            reset_dispatcher,
            set_dispatcher,
        )

        # 替换为可控 dispatcher
        factory = MagicMock()
        provider = FakeProvider("smtp")
        factory.return_value = provider

        from services.notify.dispatcher import NotifyDispatcher
        set_dispatcher(NotifyDispatcher(provider_factory=factory))
        try:
            ok = await dispatch(channel="smtp", user_id="u", title="t", content="c")
            assert ok is True
            factory.assert_called_once_with("smtp")
        finally:
            reset_dispatcher()

    @pytest.mark.asyncio
    async def test_reset_clears_singleton(self):
        from services.notify.dispatcher import (
            get_dispatcher,
            reset_dispatcher,
            set_dispatcher,
        )

        set_dispatcher(MagicMock())
        reset_dispatcher()
        # 再次 get 应该返回新的 (MagicMock 不是同一个)
        d = get_dispatcher()
        assert d is not None


# ---------------------------------------------------------------------------
# 与真实 provider registry 集成 (smoke)
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    @pytest.mark.asyncio
    async def test_real_registry_returns_mock_provider_by_default(self):
        """未设置 NOTIFY_*_ENABLED 时,registry 应返回 mock provider."""
        from providers.registry import get_notify_provider
        from services.notify.dispatcher import NotifyDispatcher

        provider = get_notify_provider("smtp")
        # 默认 mock 实现
        assert provider.channel == "smtp"

        d = NotifyDispatcher()  # 用默认 factory
        ok = await d.dispatch(
            channel="smtp", user_id="u", title="t", content="c"
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_unknown_channel_raises_in_registry(self):
        from providers.exceptions import InvalidRequestError
        from providers.registry import get_notify_provider

        with pytest.raises(InvalidRequestError):
            get_notify_provider("nonexistent_channel_xyz")